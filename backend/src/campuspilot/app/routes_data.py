"""Read-only catalogue, knowledge, place, teacher and map configuration endpoints."""

from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field, JsonValue

from campuspilot.app.state import NOTICE, WebState
from campuspilot.knowledge import KnowledgeQuery, campus_today
from campuspilot.places_discovery import DiscoveryQuery, PlaceDiscovery
from campuspilot.presentation import place_card, service_card


def register(app: FastAPI, state: WebState) -> None:
    @app.get("/api/catalog")
    def catalog() -> dict[str, JsonValue]:
        # Explicit public catalogue. No model-selected operations or invented facts.
        records = state.repository.services()
        return {
            "services": [service_card(state.repository, r) for r in records],
            "sources": [s.model_dump(mode="json") for s in state.repository.evidence_for(records)],
            "notice": NOTICE,
        }

    @app.post("/api/knowledge/search")
    def search_knowledge(body: KnowledgeQuery, request: Request) -> JSONResponse:
        state.session_for(request)
        return JSONResponse(
            {
                **state.knowledge.response(body, campus_today()),
                "request_id": request.state.request_id,
            }
        )

    @app.get("/api/places")
    def places(
        q: Annotated[str, Field(max_length=120)] = "", category: str | None = None
    ) -> dict[str, JsonValue]:
        records = state.repository.search_place(q, category)
        return {
            "places": [place_card(p) for p in records],
            "sources": [s.model_dump(mode="json") for s in state.repository.evidence_for(records)],
            "notice": NOTICE,
        }

    @app.get("/api/teachers")
    def teachers(q: Annotated[str, Field(max_length=120)] = "") -> dict[str, JsonValue]:
        records = state.repository.search_teacher(q)
        return {
            "teachers": [t.model_dump(mode="json") for t in records],
            "sources": [s.model_dump(mode="json") for s in state.repository.evidence_for(records)],
            "notice": NOTICE,
        }

    @app.post("/api/places/search")
    def discover_places(body: DiscoveryQuery, request: Request) -> JSONResponse:
        state.session_for(request)
        discovery = state.place_discovery or PlaceDiscovery(state.repository)
        return JSONResponse(
            {
                **discovery.search(body.query, body.category),
                "request_id": request.state.request_id,
            }
        )

    @app.get("/api/map-config")
    def map_config() -> dict[str, JsonValue]:
        return {
            "configured": bool(state.amap_key and state.amap_security_code),
            "key": state.amap_key if state.amap_security_code else "",
            "service_host": "/_AMapService",
            "provider": "amap",
            "notice": "仅定位已有依据的地点；导航由高德提供。",
        }
