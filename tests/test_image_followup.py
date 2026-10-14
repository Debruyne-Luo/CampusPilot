"""Image task continuation is application state; prior images cannot replace campus evidence."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.agent.verify import verify_answer
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion, ImageInput
from campuspilot.places_discovery import PlaceDiscovery
from campuspilot.rag import SnapshotStore
from campuspilot.tools import agent_registry

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
REPO = DirectoryRepository.load(DATA)
IMAGE = ImageInput("SYNTHETIC-NOTICE", "image/png", b"synthetic-pixels")
NOTICE = "合成测试通知：截止2026-10-14 17:00，提交合成测试表，非真实校務信息。"


class ScriptModel:
    def __init__(self, *replies: dict[str, Any]) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict[str, object]]] = []

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> Completion:
        self.calls.append(messages)
        if not self.replies:
            raise AssertionError("Unplanned model call")
        return Completion(content=json.dumps(self.replies.pop(0), ensure_ascii=False))


def understanding(**changes: object) -> dict[str, object]:
    return {
        "intent": "政策问答",
        "missing": [],
        "image_observation": NOTICE,
        "image_visible_text": NOTICE,
        **changes,
    }


def answer(text: str) -> dict[str, object]:
    return {"answer": text, "source_ids": [], "status": "success"}


def agent(model: ScriptModel) -> AgentRunner:
    registry = agent_registry(
        REPO,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag"),
        discovery=PlaceDiscovery(REPO),
    )
    return AgentRunner(registry, REPO, model)


def run(
    runner: AgentRunner,
    question: str,
    context: ConversationContext,
    images: tuple[ImageInput, ...] = (IMAGE,),
) -> dict[str, Any]:
    return asyncio.run(runner.run(question, context, images=images))


def test_read_request_then_pure_image_continues_the_explicit_task() -> None:
    model = ScriptModel(understanding(), answer("图片要求提交合成测试表。"))
    runner, context = agent(model), ConversationContext()
    pending = run(runner, "请读这张通知，告诉我要交什么", context, images=())
    assert pending["result_status"] == "needs_clarification" and not model.calls
    assert context.image_task is not None
    output = run(runner, "", context)
    assert output["answer_mode"] == "agent_image" and output["result_status"] == "success"
    assert "合成测试表" in output["answer"]
    assert output["plan"] == [] and output["citations"] == []
    payload = model.calls[-1][-1]["content"]
    assert isinstance(payload, list)
    assert "告诉我要交什么" in str(payload[0])


def test_notification_followup_without_image_word_reads_current_image() -> None:
    model = ScriptModel(
        understanding(), answer("图片要求提交合成测试表。"),
        understanding(), answer("图片截止时间是2026年10月14日17:00。"),
    )
    runner, context = agent(model), ConversationContext()
    first = run(runner, "帮我读这张通知，要求交什么", context)
    assert first["result_status"] == "success"
    context.remember("帮我读这张通知，要求交什么", str(first["answer"]))
    output = run(runner, "什么时候截止", context)
    assert output["answer_mode"] == "agent_image" and output["result_status"] == "success"
    assert "2026年10月14日" in output["answer"]
    assert output["plan"] == [] and output["citations"] == []
    assert all(isinstance(messages[-1]["content"], list) for messages in model.calls)


def test_pure_image_with_no_task_then_short_followup() -> None:
    model = ScriptModel(
        understanding(), understanding(), answer("图片截止时间是2026-10-14 17:00。")
    )
    runner, context = agent(model), ConversationContext()
    first = run(runner, "", context)
    assert first["result_status"] == "needs_clarification"
    context.remember("[用户上传校园图片]", str(first["answer"]))
    followup = run(runner, "什么时候截止", context)
    assert followup["result_status"] == "success" and followup["answer_mode"] == "agent_image"


@pytest.mark.parametrize(
    "question", ["图书馆几点关门", "什么时候商学院关门", "帮我解释学校食堂收费标准"]
)
def test_unrelated_campus_question_excludes_old_images_from_both_model_calls(question: str) -> None:
    model = ScriptModel(
        understanding(), answer("图片要求提交合成测试表。"),
        {"intent": "政策问答", "missing": []},
        {"answer": "公开资料中尚未确认图书馆关门时间。", "source_ids": [], "status": "empty"},
        understanding(), answer("图片截止时间是2026-10-14 17:00。"),
    )
    runner, context = agent(model), ConversationContext()
    first = run(runner, "读这张通知，要求交什么", context)
    context.remember("读这张通知，要求交什么", str(first["answer"]))
    output = run(runner, question, context)
    assert output["answer_mode"] != "agent_image"
    assert output["plan"][0]["tool"] == "search_knowledge"
    assert context.image_task is None
    for messages in model.calls[2:4]:
        assert isinstance(messages[-1]["content"], str)
        assert "user_images" not in str(messages[-1]["content"])
    resumed = run(runner, "这张通知什么时候截止", context)
    assert resumed["answer_mode"] == "agent_image" and resumed["result_status"] == "success"


@pytest.mark.parametrize(
    "question",
    [
        "什么时候图书馆关门", "需要提交哪些材料补办校园卡", "什么时候商学院关门",
        "帮我解释学校食堂收费标准",
    ],
)
def test_new_campus_subject_is_not_an_image_followup(question: str) -> None:
    from campuspilot.chat_runtime import ImageTask

    context = ConversationContext(image_task=ImageTask("请读这张合成测试通知"))
    assert not AgentRunner._image_followup(question, context)


def test_general_image_understanding_can_continue_after_pure_image() -> None:
    model = ScriptModel(
        understanding(), understanding(), answer("图片是一份要求提交合成测试表的测试通知。")
    )
    runner, context = agent(model), ConversationContext()
    assert run(runner, "", context)["result_status"] == "needs_clarification"
    output = run(runner, "帮我解释一下", context)
    assert output["result_status"] == "success" and output["answer_mode"] == "agent_image"


def test_picture_authenticity_is_not_reading_even_with_analysis_verb() -> None:
    assert not AgentRunner._reads_image("分析这张通知是真的吗")


def test_old_classroom_image_cannot_redirect_an_unrelated_destination() -> None:
    classroom = understanding(
        image_observation="合成课表：E2A403。", image_visible_text="E2A403"
    )
    model = ScriptModel(
        classroom, answer("图片中的教室是E2A403。"),
        {"intent": "路线", "destination": "图书馆", "missing": [],
         "image_observation": "合成课表：E2A403。", "image_visible_text": "E2A403"},
    )
    runner, context = agent(model), ConversationContext()
    assert run(runner, "读这张课表，教室写的是什么", context)["result_status"] == "success"
    output = run(runner, "我想去图书馆", context)
    assert isinstance(model.calls[-1][-1]["content"], str)
    assert all(place["place_id"] != "cdut:place:east-e2a" for place in output["places"])


def test_new_session_and_unrelated_history_do_not_reuse_an_old_image_task() -> None:
    model = ScriptModel(understanding())
    context = ConversationContext()
    context.remember("图书馆几点关门", "没有足够官方依据。")
    output = run(agent(model), "", context)
    assert output["answer_mode"] == "agent_image"
    assert output["result_status"] == "needs_clarification" and output["plan"] == []
    assert "你希望我" in output["answer"]
    assert ConversationContext().image_task is None


@pytest.mark.parametrize("question", ["图书馆几点关门", "最新通知写了什么", "这是什么规定"])
def test_text_question_does_not_create_a_spurious_image_read_task(question: str) -> None:
    assert not AgentRunner._reads_image(question)


@pytest.mark.parametrize(
    ("evidence", "text"),
    [
        ("截止2026-10-14。", "截止2026年10月14日。"),
        ("截止2026年10月14日。", "截止2026/10/14。"),
        ("截止２０２６－１０－１４。", "截止2026年10月14日。"),
        ("截止2026-02-04。", "截止2026年2月4日。"),
    ],
)
def test_equivalent_full_dates_remain_valid(evidence: str, text: str) -> None:
    assert verify_answer(text, ["synthetic"], ["synthetic"], "success", evidence) is None


@pytest.mark.parametrize(
    "claim",
    ["截止2026年10月15日。", "截止2026年2月30日。", "电话20261014。", "收费2026元。"],
)
def test_date_normalization_does_not_allow_changed_days_phones_or_fees(claim: str) -> None:
    assert (
        verify_answer(claim, ["synthetic"], ["synthetic"], "success", "截止2026年10月14日。")
        == "invalid_response"
    )


@pytest.mark.parametrize(
    ("evidence", "claim"),
    [
        ("截止2026-10-14 17:00。", "截止10月14日17时。"),
        ("截止2026-10-14 17:00。", "截止10/14下午5点。"),
        ("截止2026-10-14 17:00。", "截止10月14日十七点。"),
        ("截止2026-10-14 17:30。", "截止10月14日下午5点半。"),
        ("截止2026-10-14 17:30。", "截止10月14日17时30分。"),
        ("截止2026年10月14日17时。", "截止10月14日17:00。"),
        ("截止2026-10-14 12:00。", "截止10月14日中午12点。"),
        ("截止2026-10-14 17:00。", "截止10月14日下午5点。"),
    ],
)
def test_month_day_and_clock_variants_preserve_exact_deadline(
    evidence: str, claim: str
) -> None:
    assert verify_answer(claim, ["synthetic"], ["synthetic"], "success", evidence) is None


@pytest.mark.parametrize(
    "claim",
    [
        "截止10月15日。", "截止11月14日。", "截止2月30日。", "截止10/15。",
        "截止2026年10月14日18:00。", "截止10月14日17:30。", "截止10月14日下午6点。",
        "截止10月14日十八点。", "截止10月14日25:61。",
    ],
)
def test_omitted_year_and_short_clock_cannot_change_the_deadline(claim: str) -> None:
    assert (
        verify_answer(claim, ["synthetic"], ["synthetic"], "success", "截止2026-10-14 17:00。")
        == "invalid_response"
    )


@pytest.mark.parametrize(
    ("evidence", "claim"),
    [
        ("截止2026-10-14 12:00。", "截止10月14日晚上12点。"),
        ("截止2026-10-14 01:00。", "截止10月14日中午1点。"),
        ("截止2026-10-14 00:00。", "截止10月14日晚上12点。"),
        ("截止2026-10-14 13:00。", "截止10月14日中午1点。"),
    ],
)
def test_ambiguous_noon_and_midnight_are_not_normalized_into_authority(
    evidence: str, claim: str
) -> None:
    assert (
        verify_answer(claim, ["synthetic"], ["synthetic"], "success", evidence)
        == "invalid_response"
    )


@pytest.mark.parametrize(
    "claim", ["图片通知截止10月15日。", "图片通知截止10月14日18:00。"]
)
def test_image_deadline_is_validated_against_visible_text_not_description(claim: str) -> None:
    model = ScriptModel(
        understanding(image_observation="描述猜测截止10月15日18:00，不能替代图片原文。"),
        answer(claim),
    )
    output = run(agent(model), "请读这张通知截止时间", ConversationContext())
    assert output["result_status"] == "needs_clarification"
    assert output["degraded_reason"] == "answer_validation"
    assert claim not in output["answer"]
