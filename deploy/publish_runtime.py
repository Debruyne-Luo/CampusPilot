"""Prepare a fixed migration artifact; publish only with bound independent release evidence."""

import argparse
import ast
import base64
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from campuspilot.migration_config import generation_model
from campuspilot.rag import canonical, digest
from campuspilot.release_gate import approved_rules, runtime_hashes

ROOT = Path(__file__).resolve().parents[1]

VERIFY = r"""
def verify_runtime(client):
    headers={'Origin':'https://campuspilot.38-244-61-184.sslip.io','X-CampusPilot-Request':'1'}
    base='http://127.0.0.1:8766'
    response=client.post(base+'/api/session',headers=headers)
    if (response.status_code!=200 or response.json().get('runtime_mode')!=settings['mode']
            or not response.json().get('model_configured')):
        raise RuntimeError('runtime_capabilities_failed')
    headers['Cookie']='campuspilot_session='+response.cookies['campuspilot_session']
    answer=client.post(base+'/api/chat',headers=headers,json={'message':'香樟食堂在哪？'})
    if (answer.status_code!=200 or not answer.json().get('places')
            or not answer.json().get('request_id')):
        raise RuntimeError('runtime_local_probe_failed')
"""

TRANSACTION = r"""
env_path=Path('/etc/campuspilot/campuspilot.env')
previous_env=env_path.read_bytes()
env_metadata=env_path.stat()
if hashlib.sha256(previous_env).hexdigest()!=expected_env_hash:
    raise RuntimeError('runtime_environment_drift')
entries={'CAMPUSPILOT_RUNTIME_MODE':settings['mode'],
    'CAMPUSPILOT_MODEL_BASE_URL':settings['base_url'], 'CAMPUSPILOT_MODEL':settings['model'],
    'CAMPUSPILOT_MODEL_API_KEY':settings['api_key'], 'CAMPUSPILOT_MODEL_KEY_FILE':'',
    'CAMPUSPILOT_DIRECT_RULES_REPORT':str((Path('/opt/campuspilot/current')/'runtime-release-report.json').resolve())}
if any('\n' in value or '\r' in value or '\x00' in value for value in entries.values()):
    raise RuntimeError('invalid_runtime_environment')
lines=[line for line in previous_env.decode().splitlines() if line.split('=',1)[0] not in entries]
lines.extend(name+'='+json.dumps(value,ensure_ascii=False) for name,value in entries.items())
next_env=('\n'.join(lines)+'\n').encode()
original_apply=ns['apply']
def apply_runtime(target,records,backups,verify):
    updated=False
    restored_env=False
    # Save private configuration before changing runtime files, so backup failure is safe.
    private_backup=backups/('environment-'+ns['uuid4']().hex)
    private_backup.mkdir(parents=True, mode=0o700)
    ns['write_atomic'](private_backup/'environment.before',previous_env,env_metadata)
    ns['os'].chmod(private_backup/'environment.before',0o600)
    def verify_transaction(restored=False):
        nonlocal updated,restored_env
        if restored and updated:
            ns['write_atomic'](env_path,previous_env,env_metadata)
            restored_env=True
        elif not updated:
            if not restored:
                if hashlib.sha256(env_path.read_bytes()).hexdigest()!=expected_env_hash:
                    raise RuntimeError('runtime_environment_drift')
                ns['write_atomic'](env_path,next_env,env_metadata)
                updated=True
        return verify(restored=restored)
    try:
        return original_apply(target,records,backups,verify_transaction)
    except Exception:
        if updated and not restored_env:
            ns['write_atomic'](env_path,previous_env,env_metadata)
            verify(restored=True)
        raise
ns['apply']=apply_runtime
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("phase1", "phase2"), required=True)
    parser.add_argument("--production-baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New public source artifact zip")
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Default prepares locally and makes no remote changes",
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Artifact already exists")
        baseline = json.loads(args.production_baseline.read_bytes())
        if baseline.get("verified_live_bytes") is not True:
            raise ValueError("Actual deployed baseline required")
        hashes = runtime_hashes(ROOT)
        payload = {}
        fixed_bytes = {}
        for name, checksum in hashes.items():
            data = (ROOT / name).read_bytes()
            if digest(data) != checksum:
                raise ValueError("Workspace changed while packaging")
            if len(data) > 200_000:
                raise ValueError("Release file exceeds existing updater limit")
            if name.endswith(".py"):
                ast.parse(data.decode(), feature_version=(3, 12))
            payload[name] = {
                "before": baseline["files_sha256"].get(name),
                "sha256": checksum,
                "data": base64.b64encode(data).decode(),
            }
            fixed_bytes[name] = data
        report = json.loads(args.report.read_bytes()) if args.report else None
        if args.publish:
            if not report or report.get("stage") != args.stage:
                raise ValueError("Independent stage report required")
            approved_rules(args.report, ROOT)
            payload["runtime-release-report.json"] = {
                "before": baseline["files_sha256"].get("runtime-release-report.json"),
                "sha256": digest(canonical(report)),
                "data": base64.b64encode(canonical(report)).decode(),
            }
            fixed_bytes["runtime-release-report.json"] = canonical(report)
        manifest = {
            "schema_version": 1,
            "stage": args.stage,
            "files_sha256": hashes,
            "production_baseline_sha256": digest(args.production_baseline.read_bytes()),
            "release_gate": report.get("release_gate", "NOT_EVALUATED")
            if report
            else "NOT_EVALUATED",
            "notice": (
                "Fixed public bytes; this artifact is not deployment or independent "
                "acceptance evidence."
            ),
        }
        if runtime_hashes(ROOT) != hashes:
            raise ValueError("Workspace changed while freezing the release")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(args.output, "x", compression=ZIP_DEFLATED) as archive:
            for name, data in fixed_bytes.items():
                archive.writestr(name, data)
            archive.writestr("runtime-manifest.json", canonical(manifest))
        if not args.publish:
            print(
                f"LOCAL ARTIFACT READY: {len(hashes)} fixed files; Python 3.12 syntax checked; "
                "release gate NOT_EVALUATED."
            )
            print("sha256=" + digest(args.output.read_bytes()))
            return
        model = generation_model()
        if model is None or report.get("model_configuration") != {
            "base_url": model.base_url,
            "model": model.model,
        }:
            raise ValueError("Model configuration differs from independently tested model")
        settings = {
            "mode": args.stage,
            "base_url": model.base_url,
            "model": model.model,
            "api_key": model.api_key,
        }
        engine = (ROOT / "deploy/update_routes.py").read_bytes()
        program = (
            "import base64,io,json,hashlib\nfrom pathlib import Path\n"
            "ns={'__name__':'campuspilot_runtime_update'}\n"
            f"exec(compile(base64.b64decode({base64.b64encode(engine).decode()!r}),'updater','exec'),ns)\n"
            f"ns['FILES']={tuple(payload)!r}\nns['BACKUP_DIRECTORY']='runtime-backups'\n"
            "ns['SUCCESS_LABEL']='RUNTIME UPDATED'\n"
            f"settings={settings!r}\nexpected_env_hash={baseline['environment_sha256']!r}\n"
            f"import sys\nsys.stdin=io.StringIO({canonical(payload).decode()!r})\n"
            + TRANSACTION
            + VERIFY
            + "\nns['main'](verify_extra=verify_runtime)\n"
        )
        ast.parse(program, feature_version=(3, 12))
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "ConnectTimeout=12",
                "campuspilot-vps",
                "/opt/campuspilot/current/.venv/bin/python -",
            ],
            input=program,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=180,
            check=False,
        )
        if result.returncode:
            parser.exit(
                2,
                "Runtime publish failed; inspect protected backup and rollback health. "
                "Provider output was suppressed.\n",
            )
        for line in result.stdout.splitlines():
            outcome = json.loads(line)
            if outcome.get("status") == "RUNTIME UPDATED":
                print(json.dumps(outcome))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        parser.exit(
            2, "Runtime package or release gate validation failed; no deployment success claimed.\n"
        )


if __name__ == "__main__":
    main()
