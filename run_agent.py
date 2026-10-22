"""Single local launcher for the submission Agent; no credentials are bundled."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_config(path: Path) -> dict[str, str]:
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(ROOT):
        raise ValueError("Keep the configured credential file outside the Agent package.")
    if resolved.stat().st_size > 65536:
        raise ValueError("Configuration file is too large.")
    values = json.loads(resolved.read_text(encoding="utf-8-sig"))
    allowed = set(json.loads((ROOT / "config.example.json").read_text(encoding="utf-8")))
    if not isinstance(values, dict) or set(values) - allowed:
        raise ValueError("Configuration contains unsupported keys; use config.example.json.")
    if any(not isinstance(v, str) or "\x00" in v for v in values.values()):
        raise ValueError("Configuration values must be strings without NUL characters.")
    return values


def settings_for_package(*, offline: bool = False):
    """Keep one application path, local binding, and the package's fixed knowledge."""
    from campuspilot.config import Settings
    from knowledge_bundle import prepare_knowledge

    if offline:
        for name in tuple(os.environ):
            if name.startswith(("CAMPUSPILOT_", "DIFY_", "AMAP_", "CF_", "TAVILY_")) or name in (
                "PUBLIC_ORIGIN",
                "TAVILY_FREE_PLAN_CONFIRMED",
            ):
                os.environ.pop(name)
    defaults = {
        "CAMPUSPILOT_RETRIEVAL_MODE": "lexical",
        "CAMPUSPILOT_AGENT_LOOP": "on",
        "CAMPUSPILOT_RUNTIME_MODE": "phase2",
        "CAMPUSPILOT_ASSET_VERSION": "auto",
    }
    for name, value in defaults.items():
        if not os.environ.get(name):
            os.environ[name] = value
    return replace(
        Settings.from_env(),
        data_dir=prepare_knowledge(ROOT),
        runtime_mode="phase2",
        agent_loop=True,
        harness_profile="",
        lab_records_dir="",
        knowledge_bundle="",
        direct_rules_report="",
        dify_api_key="",
        public_origin=None,
        api_token=None,
        asset_version="auto",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="理小龙 CDUTdino single Agent")
    parser.add_argument("--port", type=int, default=8766)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Disable all external services.")
    mode.add_argument("--config", type=Path, help="External JSON configuration file.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    os.chdir(ROOT)
    try:
        if args.config:
            os.environ.update(read_config(args.config))
        import uvicorn
        from campuspilot.app.main import build_app

        app = build_app(settings_for_package(offline=args.offline))
    except OSError, ValueError:
        parser.exit(
            2,
            "Configuration or knowledge invalid. Check the template and verify_agent.py; "
            "no key values are logged.\n",
        )
    print(f"CDUTdino Agent: http://127.0.0.1:{args.port}/", flush=True)
    if args.offline:
        print(
            "Offline mode: local catalogue and sourced guidance; "
            "AI, image reader, web and map services disabled.",
            flush=True,
        )
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False)
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(uvicorn.Server(config).serve())
    else:
        uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
