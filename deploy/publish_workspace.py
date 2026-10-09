"""Publish nine fixed map/mobile files with backup, real provider probes and rollback."""

import importlib.util
from pathlib import Path

FILES = (
    "backend/src/campuspilot/web.py",
    "backend/src/campuspilot/web_assets/index.html",
    "backend/src/campuspilot/web_assets/app.js",
    "backend/src/campuspilot/web_assets/journey.js",
    "backend/src/campuspilot/web_assets/map-frame.js",
    "backend/src/campuspilot/web_assets/map-frame.css",
    "backend/src/campuspilot/web_assets/workspace.css",
    "backend/src/campuspilot/web_assets/map-discovery.js",
    "backend/src/campuspilot/web_assets/guidance.js",
)

VERIFY = """
def verify_workspace(client):
    verify_knowledge(client)
    base = "http://127.0.0.1:8766"
    for name in ("workspace.css", "map-discovery.js", "guidance.js"):
        if client.get(base + "/assets/" + name).status_code != 200:
            raise RuntimeError("workspace_asset_failed")
    # Match the observed JS SDK protocol: this release uses a JavaScript Key,
    # and a bare Web Service request returns USERKEY_PLAT_NOMATCH.
    sdk = {"platform":"JS", "s":"rsv3", "logversion":"2.0", "sdkversion":"2.3.5.6",
           "appname":"https%3A%2F%2Fcampuspilot.38-244-61-184.sslip.io%2Fmap-view"}
    found = client.get(base + "/_AMapService/v3/place/around", params={
        "location":"104.147531,30.675012", "radius":"2000", "keywords":"攻坚楼",
        "offset":"10", "page":"1", "extensions":"base", "antiCrab":"true",
        "type_":"NEARBY", **sdk})
    value = found.json()
    if found.status_code != 200 or value.get("status") != "1" or not value.get("pois"):
        raise RuntimeError("workspace_provider_search_failed")
    poi = value["pois"][0]
    detail = client.get(base + "/_AMapService/v3/place/detail",
                        params={"id":poi["id"], "antiCrab":"true", "type_":"DETAIL", **sdk})
    if detail.status_code != 200 or detail.json().get("status") != "1":
        raise RuntimeError("workspace_provider_detail_failed")
    catalogue = client.get(base + "/api/places").json()["places"]
    origin = next(p["position"] for p in catalogue if p["place_id"] == "cdut:place:east-library")
    route = client.get(base + "/_AMapService/v3/direction/walking", params={
        "origin":str(origin["longitude"])+","+str(origin["latitude"]),
        "destination":poi["location"], "multipath":"0", **sdk})
    if (route.status_code != 200 or route.json().get("status") != "1"
            or not route.json().get("route",{}).get("paths")):
        raise RuntimeError("workspace_provider_route_failed")
"""


def main():
    spec = importlib.util.spec_from_file_location(
        "knowledge_publisher", Path(__file__).with_name("publish_knowledge.py")
    )
    if not spec or not spec.loader:
        raise RuntimeError("publisher_unavailable")
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    original_verify = publisher.VERIFY
    publisher.__dict__.update(
        FILES=FILES,
        VERIFY=original_verify + VERIFY,
        VERIFY_FUNCTION="verify_workspace",
        BACKUP_DIRECTORY="workspace-backups",
        SUCCESS_LABEL="WORKSPACE UPDATED",
        RELEASE_LABEL="Workspace",
    )
    publisher.main()


if __name__ == "__main__":
    main()
