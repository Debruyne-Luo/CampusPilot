"""Request validation for the browser boundary and the AMap SDK proxy."""

import math
import re
from typing import Annotated

from fastapi import HTTPException
from pydantic import Field

from campuspilot.contracts import Contract


class ChatInput(Contract):
    message: Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


def validate_route_params(path: str, params: dict[str, str]) -> None:
    """Bound the SDK's two added capabilities without reflecting private origins."""
    fields = {
        "v3/direction/walking": {"origin", "destination", "multipath"},
        "v3/assistant/coordinate/convert": {"locations", "coordsys"},
    }
    if path not in fields:
        return
    metadata = {
        "platform",
        "s",
        "logversion",
        "key",
        "sdkversion",
        "appname",
        "csid",
        "jscode",
        "callback",
        "jsonp",
        "cb",
    }
    if set(params) - metadata - fields[path]:
        raise HTTPException(422)
    names = ("origin", "destination") if path.endswith("walking") else ("locations",)
    for name in names:
        try:
            lng, lat = (float(part) for part in params.get(name, "").split(","))
            if not (
                math.isfinite(lng) and math.isfinite(lat) and abs(lng) <= 180 and abs(lat) <= 90
            ):
                raise ValueError
        except ValueError:
            raise HTTPException(422) from None
    if path.endswith("convert") and params.get("coordsys") != "gps":
        raise HTTPException(422)
    if path.endswith("walking") and params.get("multipath", "0") not in {"0", "1"}:
        raise HTTPException(422)


def validate_place_params(path: str, params: dict[str, str]) -> None:
    """Allow only the two observed PlaceSearch operations, near the pilot campus."""
    if path not in {"v3/place/around", "v3/place/detail"}:
        return
    metadata = {
        "platform",
        "s",
        "logversion",
        "key",
        "sdkversion",
        "appname",
        "csid",
        "jscode",
        "callback",
        "jsonp",
        "cb",
        "antiCrab",
        "language",
        "extensions",
    }
    fields = (
        {"id", "children", "type_"}
        if path.endswith("detail")
        else {
            "city",
            "page",
            "offset",
            "location",
            "radius",
            "children",
            "type_",
            "keywords",
            "citylimit",
            "sortrule",
        }
    )
    if set(params) - metadata - fields or params.get("extensions", "base") != "base":
        raise HTTPException(422)
    if path.endswith("detail"):
        if not re.fullmatch(r"[A-Za-z0-9]{8,32}", params.get("id", "")):
            raise HTTPException(422)
        return
    try:
        lng, lat = (float(part) for part in params.get("location", "").split(","))
        radius = int(params.get("radius", "0"))
        at_center = abs(lng - 104.147531) < 0.000001 and abs(lat - 30.675012) < 0.000001
        # A tapped base-map label: a small radius around a point on or next to campus
        # (about 2.5 km box).
        tap_lookup = (
            abs(lng - 104.147531) <= 0.026 and abs(lat - 30.675012) <= 0.023 and radius <= 100
        )
        valid = (
            (at_center or tap_lookup)
            and 1 <= radius <= 2000
            and 1 <= int(params.get("offset", "10")) <= 10
            and 1 <= int(params.get("page", "1")) <= 5
        )
    except ValueError:
        valid = False
    keyword = params.get("keywords", "")
    if not valid or not keyword.strip() or len(keyword) > 120 or any(ord(c) < 32 for c in keyword):
        raise HTTPException(422)
