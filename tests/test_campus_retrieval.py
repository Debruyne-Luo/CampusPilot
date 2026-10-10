"""Public inventory regression and provider/user authority boundaries."""

from pathlib import Path

import pytest
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.retrieval import campus_answer
from campuspilot.web import create_web_app
from fastapi.testclient import TestClient
from pydantic import HttpUrl

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


@pytest.mark.parametrize("query", ["E2A101在哪", "ｅ２ａ１０１", "东教 E2A-101", "E2A"])
def test_classroom_code_resolves_only_its_wing(query: str) -> None:
    repo = DirectoryRepository.load(DATA)
    places = repo.match_places_in_question(query)
    assert [p.place_id for p in places] == ["cdut:place:east-e2a"]
    assert places[0].position is None  # Never reuse E1A as the destination of E2A.


def test_food_and_parcels_are_direct_grounded_queries_without_dify() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        client.post("/api/session", headers=HEADERS)
        for question, expected, kind in (
            ("芙蓉食堂有什么吃的", {"dominos-furong", "mcdonalds-furong", "subway-furong"}, "food"),
            ("珙桐有什么美食推荐", {"kfc-gongtong", "yoshinoya-gongtong"}, "food"),
            ("去哪里拿快递", {"cainiao-dongyuan", "jd-dongyuan", "sf-dongyuan"}, "parcel"),
        ):
            result = client.post("/api/chat", json={"message": question}, headers=HEADERS).json()
            assert result["answer_mode"] == "campus_retrieval"
            assert result["nearby_kind"] == kind
            assert {p["place_id"].removeprefix("cdut:place:") for p in result["places"]} == expected
            assert all(p["position"]["coordinate_system"] == "GCJ02" for p in result["places"])


def test_inside_food_and_multiple_canteens_keep_query_scope() -> None:
    repo = DirectoryRepository.load(DATA)
    for question in ("校内美食推荐", "芙蓉和珙桐有什么吃的"):
        result = campus_answer(repo, question)
        assert result
        places, answer = result["places"], result["answer"]
        assert isinstance(places, list) and len(places) == 5 and isinstance(answer, str)
        assert "达美乐" in answer and "吉野家" in answer
        assert all(
            isinstance(p, dict) and isinstance(p["tags"], list) and "dongyuan" not in p["tags"]
            for p in places
        )
    assert repo.search_place("网安楼在哪")[0].place_id == "cdut:place:network-security"
    assert repo.search_place("E1C101") == ()  # Unknown wing never recurses or borrows a point.


def test_replacement_keeps_preconditions_and_all_four_places() -> None:
    result = campus_answer(DirectoryRepository.load(DATA), "校园卡丢了去哪补办")
    assert result
    answer, places = result["answer"], result["places"]
    assert isinstance(answer, str) and isinstance(places, list)
    assert "银杏" in answer and "大于20元" in answer
    assert "不是补卡费" in answer and result["nearby_kind"] == "replacement"
    assert len(places) == 4


def test_specific_policy_questions_still_use_model_and_official_context() -> None:
    repo = DirectoryRepository.load(DATA)
    assert campus_answer(repo, "校园卡补办费用是多少") is None
    assert campus_answer(repo, "银行卡补卡去哪") is None
    assert campus_answer(repo, "王洪辉老师办公室在哪里") is None


def test_source_authority_cannot_be_silently_promoted() -> None:
    repo = DirectoryRepository.load(DATA)
    records = repo.search_place("菜鸟驿站")
    evidence = repo.evidence_for(records)
    provider = next(s for s in evidence if s.source_authority == "map_provider")
    assert provider.source_url and provider.source_url.host == "ditu.amap.com"
    bad = provider.model_copy(update={"source_authority": "official_department"})
    with pytest.raises(ValueError, match="official CDUT"):
        DirectoryRepository((), (), (bad,))
    bad = provider.model_copy(
        update={"source_url": HttpUrl("https://ditu.amap.com/?key=synthetic")}
    )
    with pytest.raises(ValueError, match="public POI"):
        DirectoryRepository((), (), (bad,))
    supplement = next(
        s
        for s in repo.evidence_for(repo.search_place("网安楼"))
        if s.source_authority == "user_supplement"
    )
    assert supplement.source_url is None and supplement.access_method == "user_message"


def test_life_payload_does_not_take_personal_coordinates() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        client.post("/api/session", headers=HEADERS)
        result = client.post(
            "/api/chat",
            headers=HEADERS,
            json={
                "message": "最近在哪补办校园卡",
                "longitude": 0.0,
                "latitude": 0.0,
            },
        )
        assert result.status_code == 422


def test_rag_replacement_chunk_keeps_where_and_preconditions_together() -> None:
    corpus = DATA.parents[1] / "integrations/dify/CampusPilot-submission-knowledge.txt"
    block = next(
        p.strip()
        for p in corpus.read_text(encoding="utf-8").split("\n\n")
        if p.strip().startswith("# 校园卡补办：地点、前提与简短流程")
    )
    assert len(block) < 1024
    assert all(word in block for word in ("银杏", "珙桐", "香樟", "身份证", "大于20元", "财务处"))
