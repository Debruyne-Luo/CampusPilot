"""Import explicitly selected Amap building candidates; never approve navigation.

Input is a credential-free export of the official Amap GUI CLI, not a model reply.
The provider result for '网安楼' is deliberately excluded: it names the college,
and has not been established as the former affiliated middle school building.
"""

import argparse
import json
from pathlib import Path

from campuspilot.directory.repository import DirectoryRepository
from campuspilot.domain import CampusPlace, MapPosition

ROOT = Path(__file__).resolve().parents[1]
# Exact POI IDs and names were compared with the existing official campus-plan names.
# Names that refer to bus stops, businesses, renamed colleges, or sub-buildings are excluded.
SELECTED = {
    "east-library": ("B0FFGHMVYO", "成都理工大学二仙桥校区东区图书馆"),
    "administration": ("B0LRXC0YZY", "成都理工大学-行政楼"),
    "finance": ("B0FFFDK67D", "成都理工大学二仙桥校区计划财务处"),
    "hospital": ("B001C7YGLD", "成都理工大学二仙桥校区校医院"),
    "security": ("B0FFIHKIYO", "成都理工大学保卫处"),
    "furong-dining": ("B0L2DH8CAW", "成都理工大学芙蓉餐厅"),
    "ginkgo-dining": ("B001C8NOJU", "银杏餐厅(银杏路店)"),
    "gongtong-dining": ("B001C8NPMY", "成都理工大学二仙桥校区珙桐餐厅"),
    "camphor-dining": ("B0FFGYU5VQ", "香樟餐厅"),
    "sports-college": ("B001C8NVRI", "成都理工大学二仙桥校区体育学院"),
    "energy": ("B0LB2RLIG6", "成都理工大学二仙桥校区能源学院"),
    "environment-civil": ("B001C8NZ3J", "成都理工大学二仙桥校区环境与土木工程学院"),
    "foreign-languages": ("B0FFFCLM14", "成都理工大学二仙桥校区外国语学院"),
    "materials": ("B0FFGC3M64", "成都理工大学二仙桥校区材料与化学化工学院"),
}


def candidate_positions(report: dict) -> dict[str, dict]:
    if report.get("method") != "official_amap_gui_cli":
        raise ValueError("Expected an official Amap CLI export")
    candidates: dict[str, dict] = {}
    for group in report["queries"]:
        for poi in group["candidates"]:
            ident = poi["provider_id"]
            if ident in candidates and candidates[ident] != poi:
                raise ValueError("Conflicting provider records require review")
            candidates[ident] = poi
    positions = {}
    for key, (ident, name) in SELECTED.items():
        poi = candidates[ident]
        if (
            poi["name"] != name
            or poi["city"] != "成都市"
            or poi["district"] != "成华区"
            or poi["coordinate_system"] != "GCJ02"
            or poi["verification_status"] != "needs_review"
            or poi["source_url"] != f"https://ditu.amap.com/place/{ident}"
            or not 104.13 <= poi["longitude"] <= 104.16
            or not 30.66 <= poi["latitude"] <= 30.69
        ):
            raise ValueError("Selected POI identity or campus area changed; review required")
        position = MapPosition.model_validate_json(
            json.dumps(
                {
                    "longitude": poi["longitude"],
                    "latitude": poi["latitude"],
                    "coordinate_system": "GCJ02",
                    "source_kind": "map_provider",
                    "source_url": poi["source_url"],
                    "retrieved_at": poi["retrieved_at"],
                    "verification_status": "needs_review",
                    "note": (
                        f"高德建筑候选：{name}（{ident}）。"
                        "坐标对应建筑，不确认入口、补卡设备、办公室或当前接待位置；"
                        "尚待负责人核对，不提供导航。"
                    ),
                },
                ensure_ascii=False,
            )
        )
        positions[f"cdut:place:{key}"] = position.model_dump(mode="json")
    return positions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/cdut")
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    positions = candidate_positions(report)
    target = args.data_dir / "places.json"
    places = json.loads(target.read_text(encoding="utf-8"))
    matched = set()
    for place in places:
        if place["place_id"] not in positions:
            continue
        position = positions[place["place_id"]]
        if place.get("position") not in (None, position):
            raise ValueError("Existing coordinates were edited; no files changed")
        place["position"] = position
        place["notes"] = [note for note in place["notes"] if not note.startswith("未录入坐标，")]
        note = "已收录高德建筑坐标候选，位置待核验；不表示这里可办理补卡或是老师办公室。"
        if note not in place["notes"]:
            place["notes"].append(note)
        matched.add(place["place_id"])
    if matched != set(positions):
        raise ValueError("Selected campus records are missing; no files changed")
    # References are unchanged; validate the original complete snapshot and every
    # candidate record before replacing the local JSON.
    DirectoryRepository.load(args.data_dir)
    updated = tuple(
        CampusPlace.model_validate_json(json.dumps(raw, ensure_ascii=False)) for raw in places
    )
    updated_by_id = {place.place_id: place for place in updated}
    if set(updated_by_id) != {place["place_id"] for place in places}:
        raise ValueError("Inventory identity mismatch")
    target.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(matched)} unconfirmed building candidates; no navigation approved.")


if __name__ == "__main__":
    main()
