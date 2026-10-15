"""Dedicated image-reader selection: images use the reader model, text keeps the main one."""

import asyncio
from typing import Any

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ImageInput
from campuspilot.tools import agent_registry
from test_agent_loop import DATA, REPO, FakeLLM, understood


def empty_runner(model: FakeLLM | None) -> AgentRunner:
    registry = agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"))
    return AgentRunner(registry, REPO, model)


def run_with_images(agent: AgentRunner, question: str, images: tuple[ImageInput, ...]) -> Any:
    return asyncio.run(agent.run(question, ConversationContext(), images=images))


def reader_runner(main: FakeLLM, reader: FakeLLM) -> AgentRunner:
    agent = empty_runner(main)
    agent.reader = reader
    return agent


def schedule_image() -> ImageInput:
    return ImageInput(attachment_id="img-1", mime_type="image/png", data=b"img")


def test_reader_defaults_to_the_main_model() -> None:
    main = FakeLLM(understood("办事"))
    assert empty_runner(main).reader is main
    assert empty_runner(None).reader is None


def test_reading_turns_use_the_reader_model() -> None:
    main = FakeLLM(understood("办事"))
    reading = FakeLLM(
        understood("办事", image_observation="SYNTHETIC via reader"),
    )
    agent = reader_runner(main, reading)
    run_with_images(agent, "帮我读一下这张课表", images=(schedule_image(),))
    # reader handles understanding + the explicit reading request; the main model never sees images.
    assert len(reading.calls) == 2
    assert not main.calls, "the main model must not see the uploaded image"


def test_text_turns_still_use_the_main_model() -> None:
    main = FakeLLM(understood("办事"))
    reading = FakeLLM(understood("办事", image_observation="must not appear"))
    agent = reader_runner(main, reading)
    run_with_images(agent, "这张课表周几有课？", images=(schedule_image(),))
    # The question names no reading action, so understanding goes to the reader model…
    assert len(reading.calls) == 1
    # …and the grounded campus answer still goes to the main model.
    assert len(main.calls) == 1
