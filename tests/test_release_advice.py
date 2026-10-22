"""Behavioral regressions for scoped procedures and invalid page-based guarantees."""

import asyncio
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.evidence import Evidence
from campuspilot.agent.executor import AgentRunner
from campuspilot.agent.plan import Plan
from campuspilot.agent.understand import Understanding
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.llm.chat_model import ChatTurn
from campuspilot.retrieval.applicability import query_filters
from campuspilot.tools.base import ToolRegistry
from test_agent_loop import FakeLLM

DATA = Path(__file__).resolve().parents[1] / "data/cdut"


def compose(question: str, history: tuple[str, ...] = ()) -> tuple[dict[str, Any], FakeLLM]:
    model = FakeLLM()
    runner = AgentRunner(ToolRegistry(()), DirectoryRepository.load(DATA), model, concise=True)
    text = "SYNTHETIC：2031届毕业生助学贷款毕业确认，各银行渠道不同。"
    evidence = Evidence(allowed={"SYNTHETIC:loan"}, hits=[{
        "source_id": "SYNTHETIC:loan", "title": "SYNTHETIC 2031届贷款毕业确认",
        "text": text, "stale": True,
    }], citations={"SYNTHETIC:loan": {
        "id": "SYNTHETIC:loan", "title": "SYNTHETIC 2031届贷款毕业确认",
        "url": "https://www.cdut.edu.cn/SYNTHETIC-loan",
    }})
    context = ConversationContext(history=tuple(ChatTurn(role="user", content=t) for t in history))
    result = asyncio.run(runner._compose(question, Understanding(intent="政策问答"),
                                         context, evidence, Plan(), []))
    return result, model


@pytest.mark.parametrize("question", [
    "国开行贷款毕业确认，个人信息错误可以自己改吗？",
    "毕业后继续升学，贷款只做毕业确认够了吗？",
    "我的贷款银行不在通知里，能套用国开行的确认流程吗？",
])
def test_cohort_scoped_loan_procedure_requires_missing_user_conditions(question: str) -> None:
    body, model = compose(question)
    assert body["result_status"] == "needs_clarification"
    assert "毕业届次" in body["answer"]
    assert "2031届" in body["answer"]  # Derived from this synthetic source, never a fixed year.
    assert "回执" not in body["answer"] and not model.calls


def test_known_bank_is_retained_without_reasking_or_switching_it() -> None:
    body, model = compose("收到贷款毕业确认短信后应去哪个渠道？", ("我办的是中国银行贷款。",))
    assert "中国银行" in body["answer"] and "毕业届次" in body["answer"]
    assert "哪家银行" not in body["answer"] and "国开行" not in body["answer"]
    assert body["result_status"] == "needs_clarification" and not model.calls


@pytest.mark.parametrize("question", [
    "我是2031届，办的是国开行贷款，毕业确认信息怎么改？",
    "我2031年毕业，办的是中国银行贷款，毕业确认如何办理？",
    "请解释2031届贷款毕业确认旧通知的历史规定。",
    "新生国开行贷款回执如何提交？",
    "助学贷款毕业确认是不是要求毕业前立刻还清贷款？",
])
def test_resolved_scope_and_unrelated_tasks_keep_existing_answer_path(question: str) -> None:
    _, model = compose(question)
    assert model.calls


@pytest.mark.parametrize("question", [
    "心理咨询页面没写收费，可以保证所有项目永久免费吗？",
    "这个预约指南未列费用，能保证以后一直免费吗？",
])
def test_missing_price_is_not_a_permanent_free_service_guarantee(question: str) -> None:
    body, model = compose(question)
    assert "不能" in body["answer"] and "收费" in body["answer"]
    assert "后续" in body["answer"] and not model.calls


@pytest.mark.parametrize("question", [
    "重新抓到旧SYNTHETIC VPN页面，代表旧服务重新上线了吗？",
    "旧系统网页能打开，是不是服务恢复了？",
])
def test_page_access_is_distinct_from_operational_service_status(question: str) -> None:
    body, model = compose(question)
    assert "页面" in body["answer"] and "不能证明" in body["answer"]
    assert "现行" in body["answer"] and not model.calls
    assert query_filters(question, date(2031, 10, 1)).historical
    assert not query_filters("VPN现在怎么使用？", date(2031, 10, 1)).historical
