"""Bounded campus place discovery shared by chat and the browser map.

Provider geometry is transient location evidence. It does not create directory records,
office associations, institutional facts, or a verification claim.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from typing import Annotated, Literal

import httpx
from pydantic import Field, JsonValue

from campuspilot.contracts import Contract
from campuspilot.directory.repository import DirectoryRepository, normalise_place_query
from campuspilot.domain import CampusPlace
from campuspilot.presentation import place_card

CAMPUS_CENTER = (104.147531, 30.675012)
SEARCH_RADIUS = 2000
# Same allowed viewport as map-frame.js; provider results are also radius checked.
AREA = (104.139965 - 0.0105, 104.154625 + 0.0105, 30.670203 - 0.009, 30.683981 + 0.009)
MAX_RESULTS = 10
_POI_ID = re.compile(r"^[A-Za-z0-9]{8,32}$")
_ROOM = re.compile(r"e\d+[a-z](?=\d|\b)")
_QUOTA_CODES = {"10003", "10004", "10010", "10019", "10020", "10021", "10044"}


class DiscoveryQuery(Contract):
    query: Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]
    category: Annotated[str, Field(max_length=40)] | None = None


class ProviderPosition(Contract):
    longitude: float
    latitude: float
    coordinate_system: Literal["GCJ02"] = "GCJ02"
    source_provider: Literal["amap"] = "amap"


class MapCandidate(Contract):
    """A separately typed temporary POI, never a CampusPlace."""

    place_id: str
    name: str
    address: str
    position: ProviderPosition
    source_provider: Literal["amap"] = "amap"
    source_label: Literal["高德地图"] = "高德地图"
    source_url: str
    evidence_scope: Literal["location_only"] = "location_only"
    transient: Literal[True] = True
    match_quality: Literal["exact", "candidate"] = "candidate"
    category: Literal["map_poi"] = "map_poi"
    aliases: tuple[str, ...] = ()


def place_target(query: str) -> str:
    """Remove only conversational wrappers, preserving the actual destination."""
    text = normalise_place_query(query).strip("，。！？?!.：:")
    text = re.sub(r"^(?:请)?(?:我想去|我要去|我想找|带我去|导航到|去|找)", "", text)
    text = re.sub(r"(?:在哪里|在哪儿|在哪|怎么走|的位置|位置)$", "", text)
    return text.strip("，。！？?!.：:")


def _name_key(label: str) -> str:
    text = normalise_place_query(label)
    return re.sub(
        r"^(?:成都理工大学|成都理工)(?:成都校区|二仙桥校区)?[—－:：]*", "", text
    )


def is_exact_place(place: CampusPlace, query: str) -> bool:
    target = _name_key(place_target(query))
    block = _ROOM.search(target)
    if block:
        target = block.group()
        return any(
            (code := _ROOM.search(normalise_place_query(n))) is not None and code.group() == target
            for n in (place.name, *place.aliases)
        )
    return bool(target) and any(_name_key(n) == target for n in (place.name, *place.aliases))


def _in_campus(lng: float, lat: float) -> bool:
    if not math.isfinite(lng) or not math.isfinite(lat):
        return False
    west, east, south, north = AREA
    if not (west <= lng <= east and south <= lat <= north):
        return False
    a, b = map(math.radians, (CAMPUS_CENTER[1], lat))
    dx = math.radians(lng - CAMPUS_CENTER[0])
    d = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dx / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(d), math.sqrt(max(0, 1 - d))) <= SEARCH_RADIUS


class PlaceDiscovery:
    def __init__(
        self,
        repository: DirectoryRepository,
        *,
        key: str = "",
        enabled: bool = False,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 5.0,
        acquire: Callable[[], bool] | None = None,
    ) -> None:
        self.repository = repository
        self._key = key
        self.enabled = enabled
        self._transport = transport
        self._timeout = timeout
        self._acquire = acquire
        self._quota_until = 0.0

    def search(self, query: str, category: str | None = None) -> dict[str, JsonValue]:
        query = DiscoveryQuery(query=query, category=category).query
        target = _name_key(place_target(query))
        local = self.repository.search_place(target, category)
        exact = tuple(p for p in local if is_exact_place(p, target))
        if exact:
            return self._result(exact, [], "local", exact=True)
        # Unknown classroom codes need clarification, not fuzzy nearby buildings.
        if _ROOM.search(target):
            return self._result((), [], "empty")
        if not self.enabled or not self._key:
            return self._result(local, [], "not_configured")
        if self._quota_until > time.monotonic():
            return self._result(local, [], "quota_exceeded")
        if self._acquire is not None and not self._acquire():
            return self._result(local, [], "quota_exceeded")
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "GET",
                    "https://restapi.amap.com/v3/place/around",
                    params={
                        "key": self._key,
                        "location": ",".join(map(str, CAMPUS_CENTER)),
                        "radius": SEARCH_RADIUS,
                        "keywords": target,
                        "offset": MAX_RESULTS,
                        "page": 1,
                        "sortrule": "weight",
                        "extensions": "base",
                        "output": "JSON",
                    },
                ) as response:
                    if response.status_code == 429:
                        self._quota_until = time.monotonic() + 60
                        return self._result(local, [], "quota_exceeded")
                    if response.status_code != 200:
                        return self._result(local, [], "unavailable")
                    body = bytearray()
                    deadline = time.monotonic() + self._timeout
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > 256_000:
                            return self._result(local, [], "unavailable")
                        if time.monotonic() > deadline:
                            return self._result(local, [], "timeout")
                        body.extend(chunk)
                    data = httpx.Response(200, content=bytes(body)).json()
        except httpx.TimeoutException:
            return self._result(local, [], "timeout")
        except httpx.HTTPError, ValueError:
            return self._result(local, [], "unavailable")
        if not isinstance(data, dict):
            return self._result(local, [], "unavailable")
        if str(data.get("status")) != "1":
            code = str(data.get("infocode", ""))
            if code in _QUOTA_CODES:
                self._quota_until = time.monotonic() + 60
                return self._result(local, [], "quota_exceeded")
            return self._result(local, [], "unavailable")
        raw_pois = data.get("pois")
        if not isinstance(raw_pois, list):
            return self._result(local, [], "unavailable")
        candidates: list[MapCandidate] = []
        seen_ids: set[str] = set()
        seen_names: set[tuple[str, float, float]] = set()
        local_names = {_name_key(n) for p in local for n in (p.name, *p.aliases)}
        for raw in raw_pois[:MAX_RESULTS]:
            if not isinstance(raw, dict):
                continue
            poi_id, name, location = raw.get("id"), raw.get("name"), raw.get("location")
            if not isinstance(poi_id, str) or not _POI_ID.fullmatch(poi_id):
                continue
            if not isinstance(name, str) or not name.strip() or len(name) > 200:
                continue
            if not isinstance(location, str):
                continue
            try:
                lng, lat = map(float, location.split(","))
            except ValueError, TypeError:
                continue
            if not _in_campus(lng, lat):
                continue
            name_key = _name_key(name)
            dedup = (name_key, round(lng, 5), round(lat, 5))
            if poi_id in seen_ids or dedup in seen_names or name_key in local_names:
                continue
            # Scope protects against unrelated response rows. Prefix matches remain candidates.
            if target not in name_key and name_key not in target:
                continue
            seen_ids.add(poi_id)
            seen_names.add(dedup)
            address = raw.get("address")
            candidates.append(
                MapCandidate(
                    place_id=f"amap:poi:{poi_id}",
                    name=name.strip(),
                    address=address if isinstance(address, str) else "",
                    position=ProviderPosition(longitude=lng, latitude=lat),
                    source_url=f"https://ditu.amap.com/place/{poi_id}",
                    match_quality="exact" if name_key == target else "candidate",
                )
            )
        exact_pois = [p for p in candidates if p.match_quality == "exact"]
        if exact_pois:
            return self._result((), exact_pois, "success", exact=True)
        return self._result(local, candidates, "success" if candidates else "empty")

    def _result(
        self,
        local: tuple[CampusPlace, ...],
        pois: list[MapCandidate],
        provider_status: str,
        *,
        exact: bool = False,
    ) -> dict[str, JsonValue]:
        cards: list[JsonValue] = [place_card(p) for p in local]
        cards.extend(p.model_dump(mode="json") for p in pois)
        cards = cards[:MAX_RESULTS]
        status = (
            "success"
            if cards
            else "empty"
            if provider_status in {"empty", "local"}
            else "unavailable"
        )
        sources: list[JsonValue] = [
            s.model_dump(mode="json") for s in self.repository.evidence_for(local)
        ]
        sources.extend(
            {
                "id": p.place_id,
                "title": p.name,
                "url": p.source_url,
                "publisher": "高德地图",
                "authority": "map_provider",
                "evidence_scope": "location_only",
            }
            for p in pois
        )
        messages = {
            "empty": "地点搜索未找到匹配；可以在地图上选择地点。",
            "timeout": "地点搜索超时，可以稍后重试或在地图上选择。",
            "not_configured": "高德地点搜索尚未配置，可以在地图上选择地点。",
            "quota_exceeded": "地点搜索额度或调用频率暂不可用，可以在地图上选择地点。",
            "unavailable": "地点搜索服务暂不可用，可以在地图上选择地点。",
        }
        resolution = "exact" if exact and len(cards) == 1 else "candidates" if cards else "none"
        return {
            "kind": "place_discovery",
            "status": status,
            "provider_status": provider_status,
            "resolution": resolution,
            "places": cards,
            "sources": sources,
            "message": messages.get(provider_status, ""),
            "map_pick_available": not cards,
        }
