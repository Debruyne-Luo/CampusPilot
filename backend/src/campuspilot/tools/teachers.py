"""find_teacher: the approved teacher roster (name, title, office, research areas, public e-mail).

The roster comes from the reviewed knowledge package (data/cdut/teachers_roster.json); it never
holds phone numbers. Each match cites its knowledge source_id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field, JsonValue

from campuspilot.contracts import Contract

ROSTER_FIELDS = (
    "name",
    "title",
    "department",
    "office",
    "research_areas",
    "email",
    "email_source_page",
    "source_id",
    "chunk_id",
)


class TeacherQuery(Contract):
    query: Annotated[str, Field(min_length=1, max_length=40)]


class FindTeacherTool:
    name = "find_teacher"
    description = (
        "在计算机与网络安全学院教师名录中按姓名或研究方向查老师："
        "职称、办公地点、研究方向、公开邮箱。"
    )
    params_model: type[BaseModel] = TeacherQuery

    def __init__(self, roster: list[dict[str, Any]]) -> None:
        self.roster = [{k: str(r.get(k, "")) for k in ROSTER_FIELDS} for r in roster]

    @classmethod
    def load(cls, path: Path) -> FindTeacherTool | None:
        if not path.exists():
            return None
        return cls(json.loads(path.read_bytes()))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(r["name"] for r in self.roster)

    def run(self, params: Any) -> dict[str, JsonValue]:
        query = str(params.query).replace("老师", "").replace("教授", "").strip()
        by_name = [r for r in self.roster if r["name"] and r["name"] in params.query]
        matches = by_name or (
            [r for r in self.roster if query and query in r["research_areas"]][:5]
            if len(query) >= 2
            else []
        )
        if not matches:
            return {"status": "empty", "matches": []}
        rows: list[JsonValue] = [dict(m) for m in matches]
        ids: list[JsonValue] = [*sorted({m["source_id"] for m in matches if m["source_id"]})]
        return {"status": "success", "matches": rows, "evidence_ids": ids}
