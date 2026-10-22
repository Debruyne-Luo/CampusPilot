"""Resolve workflow references against the local snapshot; never parse model coordinates."""

from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import Field, JsonValue, model_validator

from campuspilot.contracts import Contract
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.domain import CampusId, CampusPlace, CampusService


class AnswerEnvelope(Contract):
    schema_version: Literal[1]
    status: Literal["success", "needs_clarification", "out_of_scope", "empty", "unavailable"]
    answer: Annotated[str, Field(min_length=1, max_length=100_000, pattern=r"\S")]
    service_ids: tuple[CampusId, ...] = Field(default=(), max_length=8)
    teacher_ids: tuple[CampusId, ...] = Field(default=(), max_length=8)
    place_ids: tuple[CampusId, ...] = Field(default=(), max_length=25)

    @model_validator(mode="after")
    def reference_scope(self) -> AnswerEnvelope:
        for ids in (self.service_ids, self.teacher_ids, self.place_ids):
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate reference")
        if self.status not in {"success", "needs_clarification"} and (
            self.service_ids or self.teacher_ids or self.place_ids
        ):
            raise ValueError("Unsuccessful replies cannot link records")
        return self


def place_card(place: CampusPlace) -> dict[str, JsonValue]:
    data = place.model_dump(mode="json")
    data["navigation_url"] = None
    pos = place.position
    if pos and pos.coordinate_system == "GCJ02" and pos.verification_status == "confirmed":
        data["navigation_url"] = "https://uri.amap.com/navigation?" + urlencode(
            {
                "to": f"{pos.longitude},{pos.latitude},{place.name}",
                "mode": "walk",
                "src": "CampusPilot",
                "coordinate": "gaode",
                "callnative": "0",
            }
        )
    return data


def service_card(repository: DirectoryRepository, service: CampusService) -> dict[str, JsonValue]:
    """Expose source links with the guide, independently of generated answer text."""
    data = service.model_dump(mode="json")
    if service.information_level != "procedure":
        data["steps"] = []
    data["procedure_note"] = service.procedure_note
    links: list[JsonValue] = []
    seen: set[str] = set()
    for source in repository.evidence_for((service,)):
        if source.source_url is None or not source.source_authority.startswith("official_"):
            continue
        url = str(source.source_url)
        if url in seen:
            continue
        seen.add(url)
        links.append({"title": source.source_reference, "url": url})
    data["source_links"] = links
    office = repository.find_office(service.office_id) if service.office_id else None
    contacts = (*(service.contacts or ()), *((office.contacts or ()) if office else ()))
    data["contacts"] = list(
        {(c.label, c.value): c.model_dump(mode="json") for c in contacts}.values()
    )
    return data


def service_summary(service: CampusService) -> str:
    """Keep legacy facts readable without certifying legacy instructions as a procedure."""
    if service.information_level == "procedure":
        return service.summary or "\n".join(step.instruction for step in service.steps)
    known = service.summary or (
        f"{service.name}，负责部门：{service.department}；适用：{service.audience}。"
    )
    return known + "\n" + str(service.procedure_note)


def guide_answer(repository: DirectoryRepository, reply: AnswerEnvelope, question: str) -> str:
    """Use a complete adopted short guide for a general how/where question.

    The workflow still resolves intent and applicability. Specific questions retain its
    generated answer; their answer must not be replaced by an unrelated generic guide.
    """
    if reply.status != "success":
        return reply.answer
    if len(reply.teacher_ids) == 1 and not reply.service_ids:
        teacher = repository.find_teacher(reply.teacher_ids[0])
        specific = (
            "电话",
            "联系",
            "邮箱",
            "几点",
            "是否",
            "今天",
            "明天",
            "值班",
            "在不在",
            "在吗",
            "详细",
            "介绍",
            "方向",
            "楼层",
        )
        if (
            teacher
            and not any(word in question for word in specific)
            and any(word in question for word in ("在哪", "哪里", "办公室", "找"))
        ):
            return (
                f"{teacher.name}老师办公室：**{teacher.office}**。"
                if teacher.office
                else f"{teacher.name}老师办公室暂未收录。"
            )
    if len(reply.service_ids) != 1:
        return reply.answer
    service = repository.find_service(reply.service_ids[0])
    if service is None or not service.summary:
        return reply.answer
    specifics = (
        "多少钱",
        "费用",
        "收费",
        "工本",
        "余额",
        "领款",
        "冻结",
        "密码",
        "身份证",
        "开放",
        "几点",
        "营业",
        "周末",
        "星期",
        "今天",
        "明天",
        "多久",
        "几天",
        "几次",
        "次数",
        "支付宝",
        "微信缴费",
        "能不能",
        "是否",
        "不用",
        "不想",
        "详细",
    )
    if any(word in question for word in specifics):
        return reply.answer
    if any(
        word in question
        for word in ("在哪", "哪里", "去哪", "怎么办", "怎么", "流程", "步骤", "补办", "补卡")
    ):
        return service_summary(service)
    return reply.answer


def resolve_cards(repository: DirectoryRepository, reply: AnswerEnvelope) -> dict[str, JsonValue]:
    services = tuple(repository.find_service(key) for key in reply.service_ids)
    teachers = tuple(repository.find_teacher(key) for key in reply.teacher_ids)
    places = tuple(repository.find_place(key) for key in reply.place_ids)
    if any(x is None for x in (*services, *teachers, *places)):
        raise ValueError("Unknown workflow reference")
    related: set[str] = set()
    for service in services:
        if service:
            related.update(p.place_id for p in repository.service_places(service))
    for teacher in teachers:
        if teacher and teacher.place_id:
            related.add(teacher.place_id)
    if (services or teachers) and set(reply.place_ids) - related:
        raise ValueError("Unrelated workflow place reference")
    return {
        "services": [service_card(repository, s) for s in services if s],
        "teachers": [t.model_dump(mode="json") for t in teachers if t],
        "places": [place_card(p) for p in places if p],
    }
