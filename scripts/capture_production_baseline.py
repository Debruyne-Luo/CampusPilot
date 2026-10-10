"""Read live source bytes over existing SSH; secrets stay out of the source archive."""

import argparse
import base64
import json
import subprocess
from pathlib import Path

from campuspilot.rag import canonical, digest

REMOTE = r"""
import base64,hashlib,io,json,subprocess
from datetime import datetime,timezone
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path('/opt/campuspilot/current').resolve()
if not root.is_relative_to(Path('/opt/campuspilot/releases')):
    raise RuntimeError('unexpected_live_path')
def read_sources():
    rows={}
    for folder in ('backend/src','data/cdut'):
        for f in sorted((root/folder).rglob('*')):
            public=f.suffix in {'.py','.js','.css','.html','.json','.jsonl','.csv','.txt','.md'}
            if f.is_file() and '__pycache__' not in f.parts and public:
                rows[f.relative_to(root).as_posix()]=f.read_bytes()
    if sum(map(len,rows.values()))>30_000_000:
        raise RuntimeError('oversized_live_snapshot')
    return rows
env=Path('/etc/campuspilot/campuspilot.env')
env_hash=hashlib.sha256(env.read_bytes()).hexdigest()
unit=subprocess.check_output(['systemctl','cat','campuspilot.service'])
first=read_sources()
archive=io.BytesIO()
with ZipFile(archive,'w',compression=ZIP_DEFLATED) as z:
    for name,body in first.items(): z.writestr(name,body)
if (first!=read_sources() or env_hash!=hashlib.sha256(env.read_bytes()).hexdigest()
        or unit!=subprocess.check_output(['systemctl','cat','campuspilot.service'])):
    raise RuntimeError('production_drift_during_capture')
print(json.dumps({'schema_version':1,'verified_live_bytes':True,
    'captured_at':datetime.now(timezone.utc).isoformat(),'resolved_release':str(root),
    'files_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in first.items()},
    'environment_sha256':env_hash,'service_unit_sha256':hashlib.sha256(unit).hexdigest(),
    'source_zip':base64.b64encode(archive.getvalue()).decode()}))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Capture exists")
        response = subprocess.run(
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
            input=REMOTE,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=40,
            check=True,
        )
        result = json.loads(response.stdout)
        archive = base64.b64decode(result.pop("source_zip"), validate=True)
        result["source_archive_sha256"] = digest(archive)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "production-source.zip").write_bytes(archive)
        (args.output / "production-manifest.json").write_bytes(canonical(result))
        print(
            f"Live baseline captured: {len(result['files_sha256'])} source files; "
            "private configuration represented only by hashes."
        )
    except OSError, ValueError, KeyError, subprocess.SubprocessError:
        parser.exit(2, "Read-only production capture failed; no live baseline claimed.\n")


if __name__ == "__main__":
    main()
