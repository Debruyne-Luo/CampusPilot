"""Publish the bounded campus map/life retrieval increment with rollback protection."""

import importlib.util
from pathlib import Path

FILES = (
    "backend/src/campuspilot/domain.py",
    "backend/src/campuspilot/evidence.py",
    "backend/src/campuspilot/directory/repository.py",
    "backend/src/campuspilot/presentation.py",
    "backend/src/campuspilot/web.py",
    "backend/src/campuspilot/retrieval.py",
    "backend/src/campuspilot/web_assets/app.js",
    "backend/src/campuspilot/web_assets/index.html",
    "backend/src/campuspilot/web_assets/style.css",
    "backend/src/campuspilot/web_assets/map-frame.js",
    "backend/src/campuspilot/web_assets/nearby.js",
    "data/cdut/places.json",
    "data/cdut/sources.json",
    "data/cdut/services.json",
    "data/cdut/teachers.json",
)

VERIFY = r"""
def verify_maplife(client):
    base = "http://127.0.0.1:8766"
    places = client.get(base + "/api/places").json()["places"]
    if len(places) != 40 or sum(p["position"] is not None for p in places) != 32:
        raise RuntimeError("maplife_inventory_failed")
    net = next(p for p in places if p["place_id"] == "cdut:place:network-security")
    if "生态环境学院" not in net["aliases"] or net["position"] is None:
        raise RuntimeError("maplife_building_failed")
    wing = client.get(base + "/api/places", params={"q":"E2A101"}).json()["places"]
    if len(wing) != 1 or wing[0]["place_id"] != "cdut:place:east-e2a":
        raise RuntimeError("maplife_classroom_failed")
    headers = {"Origin":"https://campuspilot.38-244-61-184.sslip.io", "X-CampusPilot-Request":"1"}
    start = client.post(base + "/api/session", headers=headers)
    if start.status_code != 200:
        raise RuntimeError("maplife_session_failed")
    headers["Cookie"] = "campuspilot_session=" + start.cookies["campuspilot_session"]
    for question, expected in (("校园卡在哪补办",4), ("珙桐有什么美食推荐",2), ("去哪里拿快递",3)):
        reply = client.post(base + "/api/chat", json={"message":question}, headers=headers)
        if reply.status_code != 200 or len(reply.json().get("places",[])) != expected:
            raise RuntimeError("maplife_chat_failed")
        if reply.json().get("answer_mode") != "campus_retrieval":
            raise RuntimeError("maplife_retrieval_failed")
        required = ("银杏", "大于20元", "不是补卡费")
        if expected == 4 and not all(x in reply.json()["answer"] for x in required):
            raise RuntimeError("maplife_preconditions_failed")
"""


def main():
    spec = importlib.util.spec_from_file_location(
        "maplife_publisher", Path(__file__).with_name("publish_knowledge.py")
    )
    if not spec or not spec.loader:
        raise RuntimeError("publisher_unavailable")
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    publisher.__dict__.update(
        FILES=FILES,
        VERIFY=VERIFY,
        VERIFY_FUNCTION="verify_maplife",
        BACKUP_DIRECTORY="maplife-backups",
        SUCCESS_LABEL="MAP LIFE UPDATED",
        RELEASE_LABEL="Map life",
    )
    publisher.main()


if __name__ == "__main__":
    main()
