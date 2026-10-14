"""Same-origin AMap JS SDK proxy with a fixed upstream allow-list."""

import re
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.responses import Response

from campuspilot.app.state import WebState
from campuspilot.app.validation import validate_place_params, validate_route_params


def register(app: FastAPI, state: WebState) -> None:
    @app.get("/_AMapService/{path:path}", include_in_schema=False)
    async def amap_proxy(path: str, request: Request) -> Response:
        # SDK proxy only: no arbitrary URL, provider key, jscode or path from a caller.
        allowed = {
            "v3/log/init",  # JS SDK startup authentication; observed in the real map load.
            "v4/map/styles",
            "v4/map/tiles",
            "v3/config/district",
            "v4/map/district",
            "v3/direction/walking",
            "v3/assistant/coordinate/convert",
            "v3/place/around",  # Observed JS PlaceSearch.searchNearBy request.
            "v3/place/detail",  # PlaceSearch.getDetails for clicked base-map hotspots.
        }
        if not state.amap_key or not state.amap_security_code or path not in allowed:
            raise HTTPException(404)
        now = time.monotonic()
        if len(request.url.query) > 4096 or not state.map_window.try_record(now):
            raise HTTPException(429)
        params = dict(request.query_params)
        validate_route_params(path, params)
        validate_place_params(path, params)
        for key in ("callback", "jsonp", "cb"):
            if key in params and not re.fullmatch(
                r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", params[key]
            ):
                raise HTTPException(422)
        params["key"] = state.amap_key
        params["jscode"] = state.amap_security_code
        base = (
            "https://webapi.amap.com/" if path == "v4/map/styles" else "https://restapi.amap.com/"
        )
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                async with client.stream("GET", base + path, params=params) as upstream:
                    if upstream.status_code != 200:
                        raise HTTPException(502)
                    content = bytearray()
                    async for chunk in upstream.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 1_000_000:
                            raise HTTPException(502)
                    if state.amap_security_code.encode() in content:
                        raise HTTPException(502)
                    # SDK startup uses JSONP. Amap returns it as octet-stream;
                    # our nosniff boundary needs an explicit script MIME type.
                    media_type = (
                        "application/javascript"
                        if any(key in params for key in ("callback", "jsonp", "cb"))
                        else upstream.headers.get("content-type", "application/json")
                    )
                    return Response(
                        bytes(content),
                        media_type=media_type,
                    )
        except httpx.HTTPError:
            raise HTTPException(502) from None
