"""make_checklist: a tickable to-do list built only from one service record in services.json."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, JsonValue

from campuspilot.contracts import Contract
from campuspilot.directory.repository import DirectoryRepository


class ChecklistQuery(Contract):
    service_id: Annotated[str, Field(min_length=1, max_length=120, pattern=r"^cdut:service:")]
    audience: Literal["all", "undergraduate", "graduate", "staff"] = "all"


def _evidence_for(field_evidence: Any, prefix: str) -> list[str]:
    ids: list[str] = []
    for item in field_evidence:
        if item.field_path == prefix or item.field_path.startswith(prefix + "."):
            ids.extend(i for i in item.evidence_ids if i not in ids)
    return ids


class ChecklistTool:
    name = "make_checklist"
    description = "根据已收录的办事事项生成可勾选清单：要带的材料、需要的信息、注意限制、办理步骤。"
    params_model: type[BaseModel] = ChecklistQuery

    def __init__(self, repository: DirectoryRepository) -> None:
        self._repository = repository

    def run(self, params: Any) -> dict[str, JsonValue]:
        service = self._repository.find_service(params.service_id)
        if service is None:
            return {"status": "empty"}
        fe = service.field_evidence
        items: list[JsonValue] = []

        def add(kind: str, text: str, field: str, place_ids: tuple[str, ...] = ()) -> None:
            items.append(
                {
                    "id": f"{kind}-{len(items) + 1}",
                    "kind": kind,
                    "text": text,
                    "evidence_ids": list(_evidence_for(fe, field)),
                    "place_ids": list(place_ids),
                    "done": False,
                }
            )

        for text in service.required_materials or ():
            add("material", text, "required_materials")
        for text in service.required_inputs or ():
            add("input", text, "required_inputs")
        for text in service.limits or ():
            add("limit", text, "limits")
        for step in service.steps:
            add("step", step.instruction, "steps", step.place_ids or ())
        return {
            "status": "success",
            "service_id": service.service_id,
            "title": service.name + " 办理清单",
            "audience_note": service.audience,
            "items": items,
            "fees_note": [str(f) for f in service.fees or ()],
            "evidence_ids": [str(i) for i in sorted({i for item in fe for i in item.evidence_ids})],
        }
