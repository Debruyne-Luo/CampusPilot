"""Guides answer the task directly; specific follow-ups retain their grounded answer."""

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from campuspilot.dify import DifyClient
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.presentation import AnswerEnvelope, guide_answer, resolve_cards
from campuspilot.web import create_web_app
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
SERVICE = "cdut:service:campus-card-replacement"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def envelope() -> AnswerEnvelope:
    return AnswerEnvelope(
        schema_version=1,
        status="success",
        answer="SYNTHETIC short upstream answer",
        service_ids=(SERVICE,),
        place_ids=("cdut:place:gongtong-dining", "cdut:place:camphor-dining", "cdut:place:finance"),
    )


def test_adopted_guide_has_buildings_actions_and_separate_fee_evidence() -> None:
    repo = DirectoryRepository.load(DATA)
    cards = resolve_cards(repo, envelope())
    places = cards["places"]
    assert isinstance(places, list) and len(places) == 3
    answer = guide_answer(repo, envelope(), "校园卡需要补办，应该怎么做，去哪里？")
    assert all(word in answer for word in ("珙桐", "香樟", "财务处", "自助补卡", "身份证"))
    assert "地点未知" not in answer and "点击" not in answer
    assert "办理前" in answer and "大于20元" in answer and "不是补卡费" in answer
    service = repo.find_service(SERVICE)
    assert service and service.summary and len(service.summary) < 220
    assert service.fees and "2020年" in service.fees[0] and "25元" in service.fees[0]
    assert service.limits and "不是" in service.limits[0] and "20元" in service.limits[0]


@pytest.mark.parametrize(
    "question", ["补卡多少钱", "补卡后多久领余额", "香樟今天开放吗", "补卡需要密码吗"]
)
def test_specific_questions_are_not_replaced_with_generic_steps(question: str) -> None:
    reply = envelope()
    assert guide_answer(DirectoryRepository.load(DATA), reply, question) == reply.answer


@pytest.mark.parametrize("has_office", [True, False])
def test_office_short_answer_never_invents_an_unlinked_map(has_office: bool) -> None:
    repo = DirectoryRepository.load(DATA)
    records = json.loads((DATA / "teachers.json").read_text(encoding="utf-8"))
    teacher = next(t for t in records if bool(t["office"]) == has_office)
    reply = AnswerEnvelope(
        schema_version=1,
        status="success",
        answer="SYNTHETIC invented map invitation",
        teacher_ids=(teacher["teacher_id"],),
    )
    answer = guide_answer(repo, reply, teacher["name"] + "老师办公室在哪？")
    assert "map" not in answer and "地图" not in answer
    assert (teacher["office"] or "暂未收录") in answer
    assert guide_answer(repo, reply, teacher["name"] + "老师联系方式是什么？") == reply.answer


def test_web_reply_exposes_complete_guide_and_official_links_with_real_references() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "answer": envelope().model_dump_json(),
                "conversation_id": body["conversation_id"] or str(uuid4()),
            },
        )

    client = DifyClient(
        "synthetic-key", transport=httpx.MockTransport(handler), structured_answers=True
    )
    with TestClient(create_web_app(data_dir=DATA, dify=client)) as browser:
        browser.post("/api/session", headers=HEADERS)
        result = browser.post(
            "/api/chat", headers=HEADERS, json={"message": "校园卡在哪补办？"}
        ).json()
        assert "珙桐" in result["answer"] and "财务处" in result["answer"]
        assert "大于20元" in result["answer"] and "不是补卡费" in result["answer"]
        assert result["services"][0]["contacts"][0]["value"] == "028-84078750"
        urls = {link["url"] for link in result["services"][0]["source_links"]}
        assert "https://wxc.cdut.edu.cn/info/1006/3424.htm" in urls
        assert all(url.startswith("https://") and ".cdut.edu.cn/" in url for url in urls)
        assert len(result["places"]) == 4
