"""Publish the task-answer increment using the established backup/rollback engine."""

import importlib.util
from pathlib import Path

FILES = (
    "backend/src/campuspilot/web_assets/app.js",
    "backend/src/campuspilot/web_assets/index.html",
    "data/cdut/services.json",
)

VERIFY = r'''
def verify_assistant(client):
    base = "http://127.0.0.1:8766"
    catalogue = client.get(base + "/api/catalog").json()
    replacement = next(
        s for s in catalogue["services"]
        if s["service_id"] == "cdut:service:campus-card-replacement"
    )
    if not all(
        word in replacement.get("summary", "")
        for word in ("珙桐", "香樟", "财务处", "大于20元", "不是补卡费")
    ):
        raise RuntimeError("assistant_guide_failed")
    if not replacement.get("source_links") or not replacement.get("contacts"):
        raise RuntimeError("assistant_actions_failed")
    headers = {"Origin":"https://campuspilot.38-244-61-184.sslip.io", "X-CampusPilot-Request":"1"}
    start = client.post(base + "/api/session", headers=headers)
    if start.status_code != 200 or not start.json().get("configured"):
        raise RuntimeError("assistant_session_failed")
    headers["Cookie"] = "campuspilot_session=" + start.cookies["campuspilot_session"]
    answer = client.post(
        base + "/api/chat", json={"message":"校园卡在哪补办，怎么做？"},
        headers=headers, timeout=100,
    )
    if answer.status_code != 200:
        raise RuntimeError("assistant_live_chat_failed")
    result = answer.json()
    if not all(
        word in result["answer"]
        for word in ("珙桐", "香樟", "财务处", "自助补卡", "大于20元", "不是补卡费")
    ):
        raise RuntimeError("assistant_live_guide_failed")
    expected = {
        "cdut:place:gongtong-dining", "cdut:place:camphor-dining", "cdut:place:finance",
        "cdut:place:ginkgo-dining",
    }
    if {p["place_id"] for p in result["places"]} != expected:
        raise RuntimeError("assistant_live_places_failed")
'''


def main():
    spec = importlib.util.spec_from_file_location(
        "assistant_publisher", Path(__file__).with_name("publish_knowledge.py")
    )
    if not spec or not spec.loader:
        raise RuntimeError("publisher_unavailable")
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    publisher.__dict__.update(
        FILES=FILES,
        VERIFY=VERIFY,
        VERIFY_FUNCTION="verify_assistant",
        BACKUP_DIRECTORY="assistant-backups",
        SUCCESS_LABEL="ASSISTANT UPDATED",
        RELEASE_LABEL="Assistant",
    )
    publisher.main()


if __name__ == "__main__":
    main()
