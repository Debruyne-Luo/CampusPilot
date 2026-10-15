"""Real Amap contract smoke: public campus queries, no map account or deployment changes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from campuspilot.app.factory import create_web_app
from fastapi.testclient import TestClient


def read_web_key(path: Path) -> str:
    if not path.is_absolute() or path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("Use a private environment file outside the checkout")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "AMAP_WEB_SERVICE_KEY":
            credential = value.strip().strip("\"'")
            if credential and not any(c.isspace() for c in credential):
                return credential
    raise ValueError("The environment file has no AMAP_WEB_SERVICE_KEY")


def run(path: Path) -> None:
    app = create_web_app(
        data_dir=Path(__file__).resolve().parents[1] / "data" / "cdut",
        runtime_mode="phase2",
        agent_loop=True,
        amap_discovery=True,
        amap_web_service_key=read_web_key(path),
    )
    headers = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
    with TestClient(app, headers=headers) as client:
        client.post("/api/session").raise_for_status()
        mapped = client.post("/api/places/search", json={"query": "商学院"})
        mapped.raise_for_status()
        map_result = mapped.json()
        chatted = client.post("/api/chat", json={"message": "我想去商学院"})
        chatted.raise_for_status()
        chat_result = chatted.json()
        streamed = client.post("/api/chat/stream", json={"message": "我想去商学院"})
        streamed.raise_for_status()
        finals = [
            json.loads(line[6:])
            for event in streamed.text.split("\n\n")
            if "event: final" in event
            for line in event.splitlines()
            if line.startswith("data: ")
        ]
        cards = map_result.get("places", [])
        same_cards = cards == chat_result.get("places")
        same_stream = bool(finals) and cards == finals[-1].get("places")
        print(json.dumps({
            "query": "商学院",
            "provider_status": map_result.get("provider_status"),
            "resolution": map_result.get("resolution"),
            "map_chat_consistent": same_cards,
            "stream_consistent": same_stream,
            "chat_status": chat_result.get("result_status"),
            "pass": map_result.get("provider_status") == "success"
            and map_result.get("resolution") == "exact" and same_cards and same_stream,
            "places": cards,
            "chat_answer": chat_result.get("answer"),
            "map_actions": chat_result.get("map_actions"),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--amap-env", type=Path, required=True)
    run(parser.parse_args().amap_env)
