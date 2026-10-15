"""SYNTHETIC regressions for observed reference and clock-format failures."""

import asyncio
import json
from typing import Any

import pytest
from campuspilot.agent.evidence import generation_evidence
from campuspilot.agent.executor import AgentRunner, Evidence
from campuspilot.agent.plan import Plan
from campuspilot.agent.understand import Understanding
from campuspilot.agent.verify import verify_answer
from campuspilot.chat_runtime import ConversationContext
from campuspilot.knowledge import KnowledgeStore
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import ProviderSearchResult, WebEvidenceService
from test_agent_loop import REPO, FakeLLM, answer
from test_service_links import row
from test_web_evidence import MemoryBudget


def compose(cited: list[str], text: str = "SYNTHETIC 请按下方指南办理。") -> dict[str, Any]:
    hit = row()
    hit.update({"title": "SYNTHETIC 办理指南", "text": "SYNTHETIC 按指南办理。"})
    evidence = Evidence(
        hits=[hit],
        allowed={"SYNTHETIC-source", "SYNTHETIC-chunk"},
        results=[{"tool": "search_knowledge", "result": {"hits": [hit]}}],
    )
    agent = AgentRunner(
        agent_registry(REPO, KnowledgeStore(())), REPO, FakeLLM(answer(text, cited))
    )
    return asyncio.run(
        agent._compose(
            "SYNTHETIC 办理步骤",
            Understanding(intent="政策问答"),
            ConversationContext(),
            evidence,
            Plan(),
            [],
        )
    )


@pytest.mark.parametrize("cited", [["SYNTHETIC-link"], ["SYNTHETIC-chunk", "SYNTHETIC-link"]])
def test_checked_entry_reference_resolves_to_its_retrieved_source(cited: list[str]) -> None:
    result = compose(cited)
    assert result["result_status"] == "success"
    assert "SYNTHETIC-source" in result["source_ids"]
    assert "SYNTHETIC-link" not in result["source_ids"]
    assert result["service_links"][0]["id"] == "SYNTHETIC-link"


@pytest.mark.parametrize(
    "cited", [["SYNTHETIC-made-up-link"], ["SYNTHETIC-source", "SYNTHETIC-made-up-link"]]
)
def test_unknown_entry_reference_is_not_removed_or_promoted(cited: list[str]) -> None:
    result = compose(cited)
    assert result["result_status"] != "success"
    assert result["degraded_reason"] == "answer_validation"


@pytest.mark.parametrize(
    "text",
    [
        "SYNTHETIC 请访问www.cdut.edu.cn。",
        "SYNTHETIC 请访问 www.cdut.edu.cn。",
        "SYNTHETIC 入口见https://www.cdut.edu.cn/SYNTHETIC-application。",
    ],
)
def test_entry_reference_cannot_enable_a_model_written_url(text: str) -> None:
    result = compose(["SYNTHETIC-link"], text)
    assert result["result_status"] != "success"
    assert result["degraded_reason"] == "answer_validation"


@pytest.mark.parametrize(
    "claim", ["派单下午2:30-6:00。", "派单下午2点半至6点。", "派单下午2：30～6：00。"]
)
def test_shared_afternoon_period_does_not_change_source_clock_range(claim: str) -> None:
    assert (
        verify_answer(
            claim, ["SYNTHETIC-source"], ["SYNTHETIC-source"], "success", "派单14:30-18:00。"
        )
        is None
    )


@pytest.mark.parametrize(
    "claim",
    ["派单下午2:30-7:00。", "派单下午2:30-5:00。", "派单下午2:30-25:00。", "派单晚上11点至1点。"],
)
def test_shared_period_never_permits_a_different_or_ambiguous_end_time(claim: str) -> None:
    assert (
        verify_answer(
            claim, ["SYNTHETIC-source"], ["SYNTHETIC-source"], "success", "派单14:30-18:00。"
        )
        == "invalid_response"
    )


def test_glued_numbered_clause_does_not_hide_the_sources_end_clock() -> None:
    assert (
        verify_answer(
            "派单下午2:30-6:00。",
            ["SYNTHETIC-source"],
            ["SYNTHETIC-source"],
            "success",
            "SYNTHETIC 派单下午2:30-6:002.电话应急24小时。",
        )
        is None
    )


def test_generation_gets_facts_and_references_while_the_ui_owns_urls() -> None:
    hit = row()
    hit["text"] = (
        "SYNTHETIC 派单14:30-18:00，入口https://www.cdut.edu.cn/SYNTHETIC-payment；不得代填密码。"
    )
    evidence = Evidence(
        hits=[hit],
        allowed={"SYNTHETIC-source"},
        results=[{"tool": "search_knowledge", "result": {"hits": [hit]}}],
    )

    def observe(messages: list[dict[str, object]]) -> Any:
        payload = json.loads(str(messages[-1]["content"]))
        sent = json.dumps(payload["tool_results"], ensure_ascii=False)
        assert "https://" not in sent and "www.cdut.edu.cn" not in sent
        assert "14:30-18:00" in sent and "不得代填密码" in sent
        assert "SYNTHETIC-source" in sent and "SYNTHETIC-link" in sent
        return answer("SYNTHETIC 派单14:30-18:00。", ["SYNTHETIC-source"])

    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, FakeLLM(observe))
    result = asyncio.run(
        agent._compose(
            "SYNTHETIC 派单时间",
            Understanding(intent="政策问答"),
            ConversationContext(),
            evidence,
            Plan(),
            [],
        )
    )
    assert result["result_status"] == "success"
    assert evidence.hits[0]["url"] == "https://www.cdut.edu.cn/SYNTHETIC-guide"
    links = result["service_links"]
    assert isinstance(links, list) and links
    link = links[0]
    assert isinstance(link, dict)
    assert link["url"] == "https://www.cdut.edu.cn/SYNTHETIC-application"


def test_web_query_contains_the_university_scope_and_original_question() -> None:
    queries: list[str] = []

    class Provider:
        name = "SYNTHETIC-search"
        available = True

        async def search(self, query: str, *args: Any, **kwargs: Any) -> ProviderSearchResult:
            queries.append(query)
            return ProviderSearchResult("empty")

    service = WebEvidenceService(MemoryBudget(), Provider())
    question = "学生邮箱的存储容量是多少GB？"
    assert asyncio.run(service.search(question)).status == "empty"
    assert len(queries) == 1
    assert "成都理工大学" in queries[0] and "site:cdut.edu.cn" in queries[0]
    assert question in queries[0]


def test_generation_address_mask_never_rewrites_reference_identifiers() -> None:
    identifiers = {
        "source_id": "SYNTHETIC-source:portal.cdut.edu.cn",
        "related_ids": ["SYNTHETIC-ref:https://www.cdut.edu.cn/locator"],
    }
    result = generation_evidence({**identifiers, "url": "https://www.cdut.edu.cn/guide"})
    assert result["source_id"] == identifiers["source_id"]
    assert result["related_ids"] == identifiers["related_ids"]
    assert "https://" not in result["url"]
