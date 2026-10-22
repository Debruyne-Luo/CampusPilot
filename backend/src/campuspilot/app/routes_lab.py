"""Public experiment viewing has no mutation or model-call endpoint."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from campuspilot.agent_lab import LabRecords
from campuspilot.app.state import ASSETS


def register(app: FastAPI, records_dir: Path | None, asset_version: str) -> None:
    records = LabRecords(records_dir)

    @app.get("/lab", response_class=HTMLResponse, include_in_schema=False)
    def lab_page() -> HTMLResponse:
        shell = (ASSETS / "v2" / "lab.html").read_text(encoding="utf-8")
        if asset_version:
            shell = shell.replace('"/assets/', f'"/assets/v-{asset_version}/')
        return HTMLResponse(shell, headers={"Cache-Control": "no-cache"})

    @app.get("/api/lab/experiments")
    def experiments() -> dict[str, object]:
        return {
            "experiments": [
                {"id": row.id, "title": row.title, "status": row.status, "kind": row.kind}
                for row in records.list()
            ]
        }

    @app.get("/api/lab/experiments/{ident}")
    def experiment(ident: str) -> dict[str, object]:
        try:
            return records.read(ident).model_dump(mode="json")
        except (OSError, ValueError):
            raise HTTPException(404, "Experiment unavailable") from None
