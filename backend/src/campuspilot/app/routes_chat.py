"""POST /api/chat: backend runtime (phase1/phase2), local answers, then Dify."""

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import JsonValue

from campuspilot.agent.executor import AgentRunner
from campuspilot.app.state import NOTICE, BrowserSession, WebState
from campuspilot.app.validation import ChatInput
from campuspilot.attachments import AttachmentError
from campuspilot.chat_runtime import PreparedQuery, public_input
from campuspilot.dify import ChatUnavailable
from campuspilot.knowledge import KnowledgeQuery, campus_today
from campuspilot.llm.chat_model import ImageInput
from campuspilot.observability import TurnObservation, turn_scope
from campuspilot.presentation import guide_answer, resolve_cards
from campuspilot.retrieval import campus_answer
from campuspilot.tools.base import ToolError

BUSY = "上一条问题正在处理，请等待回答。"
SESSION_LIMIT_LOCAL = "本次提问较多，请开启新对话。"
SESSION_LIMIT_DIFY = "已达到本次开发会话的提问上限。"
GLOBAL_LIMIT = "当前提问额度或并发已满，请稍后再试。"
UPSTREAM_MESSAGES = {
    "directory_unavailable": "业务工具查询失败，本次没有取得可用结果，请开启新对话。",
    "upstream_credentials": "AI 服务凭据不可用，请检查 Dify 应用配置。",
    "upstream_limit": "AI 服务当前额度不足或请求受限，请稍后再试。",
    "upstream_timeout": "AI 回答超时，远端可能仍在处理；请开启新对话，不自动重试。",
}
UPSTREAM_DEFAULT = "AI 服务暂不可用，请开启新对话后重试。"
STREAM_UNAVAILABLE = "流式回答未启用，请使用普通对话。"


def register(app: FastAPI, state: WebState) -> None:
    @app.post("/api/chat")
    async def chat(body: ChatInput, request: Request) -> JSONResponse:
        with turn_scope(request.state.request_id) as turn:
            response = await dispatch_chat(body, request)
            metadata = json.loads(bytes(response.body))
            turn.result(
                metadata.get("result_status"),
                metadata.get("degraded_reason") or metadata.get("error_code"),
                http_status=response.status_code,
            )
            return response

    async def dispatch_chat(body: ChatInput, request: Request) -> JSONResponse:
        session = state.session_for(request)
        if session.busy:
            return state.problem(request, "busy", BUSY, 409)
        if body.attachment_ids and (state.agent is None or state.runtime_mode != "phase2"):
            return state.problem(request, "images_unavailable", "图片理解需要启用 AI 对话。", 503)
        query_text = body.message.strip()
        if state.runtime_mode != "legacy":
            if (
                state.embedder is not None
                and state.agent is None
                and state.runtime_mode == "phase2"
                and query_text
                and public_input(query_text)
            ):
                # Fill the query-vector cache off the sync path; failure means BM25-only.
                await _prefetch_embedding(
                    state, state.runtime.embedding_question(query_text, session.context)
                )
            if state.agent is not None:
                return await _agent_turn(state, request, session, body, state.agent)
            prepared = state.runtime.prepare(query_text, session.context, request.state.request_id)
            query_text = prepared.query
            if prepared.route != "legacy_knowledge":
                return await _runtime_turn(state, request, session, body, prepared)
        local = await _local_turn(state, request, session, body)
        if local is not None:
            return local
        return await _dify_turn(state, request, session, body, query_text)

    @app.post("/api/chat/stream", response_model=None)
    async def chat_stream(body: ChatInput, request: Request) -> StreamingResponse | JSONResponse:
        """SSE agent turn: understanding, plan, tool_start/tool_end, composing, answer_delta,
        final. Same session, origin, busy and budget guards as /api/chat. Without the agent
        loop it answers 404 stream_unavailable and the browser falls back to /api/chat."""
        session = state.session_for(request)
        if session.busy:
            return state.problem(request, "busy", BUSY, 409)
        agent = state.agent
        if agent is None or state.runtime_mode != "phase2":
            return state.problem(request, "stream_unavailable", STREAM_UNAVAILABLE, 404)
        images = _images_for_turn(state, request, session, body, agent)
        if isinstance(images, JSONResponse):
            return images
        if session.turns_exhausted:
            return state.problem(request, "session_limit", SESSION_LIMIT_LOCAL, 429)
        use_model = agent.model is not None
        if use_model and not state.budget.try_acquire():
            return state.problem(request, "global_limit", GLOBAL_LIMIT, 429)
        session.attempts += 1
        session.busy = True
        if body.attachment_ids:
            session.current_image_ids = tuple(body.attachment_ids)
        queue: asyncio.Queue[tuple[str, JsonValue] | None] = asyncio.Queue()
        question = body.message.strip()
        request_id = request.state.request_id
        released = False
        started = False

        def release_claim() -> None:
            nonlocal released
            if released:
                return
            released = True
            session.busy = False
            if use_model:
                state.budget.release()

        async def emit(event: str, data: dict[str, JsonValue]) -> None:
            await queue.put((event, data))

        async def work() -> None:
            # StreamingResponse runs after this handler returns. Establish correlation in
            # the producer task, so tools and delayed Jev callbacks inherit this turn.
            nonlocal started
            started = True
            try:
                with turn_scope(request_id) as turn:
                    await dispatch_stream(turn)
            finally:
                release_claim()
                await queue.put(None)

        async def dispatch_stream(turn: TurnObservation) -> None:
            try:
                # Knowledge tools embed their actual query off-loop after authorization.
                async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                    if images:
                        response = await agent.run(question, session.context, emit, images=images)
                    else:
                        response = await agent.run(question, session.context, emit)
            except TimeoutError:
                response = timeout_response()
            except Exception:
                response = {**timeout_response(), "answer": UPSTREAM_DEFAULT}
                response["degraded_reason"] = "agent_error"
            finally:
                release_claim()
            turn.result(response.get("result_status"), response.get("degraded_reason"))
            answer_text = response.get("answer")
            if isinstance(answer_text, str):
                _remember_answer(session, body, answer_text)
                # Deltas are emitted only after verification; nothing unverified is shown.
                for i in range(0, len(answer_text), 24):
                    await queue.put(("answer_delta", {"text": answer_text[i : i + 24]}))
            await queue.put(("final", {**response, "request_id": request_id, "notice": NOTICE}))

        task = asyncio.create_task(work())

        async def events() -> AsyncIterator[str]:
            try:
                yield f"event: start\ndata: {json.dumps({'request_id': request_id})}\n\n"
                while (item := await queue.get()) is not None:
                    event, data = item
                    yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                await task
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                # Cancelling a task before its coroutine starts cannot run work's finally.
                release_claim()
                if not started:
                    with turn_scope(request_id) as turn:
                        turn.result("cancelled")

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )


async def _runtime_turn(
    state: WebState,
    request: Request,
    session: BrowserSession,
    body: ChatInput,
    prepared: PreparedQuery,
) -> JSONResponse:
    if session.turns_exhausted:
        return state.problem(request, "session_limit", SESSION_LIMIT_LOCAL, 429)
    use_model = prepared.model_needed and state.model is not None
    if use_model and not state.budget.try_acquire():
        return state.problem(request, "global_limit", GLOBAL_LIMIT, 429)
    session.attempts += 1
    session.busy = True
    try:
        response = await state.runtime.generate(prepared, session.context.history)
    except ChatUnavailable as exc:
        response = state.runtime.limited(prepared, exc.code)
    finally:
        session.busy = False
        if use_model:
            state.budget.release()
    answer_text = response.get("answer")
    if isinstance(answer_text, str) and public_input(body.message):
        session.context.remember(body.message, answer_text)
    return JSONResponse({**response, "request_id": request.state.request_id, "notice": NOTICE})


AGENT_TIMEOUT_SECONDS = 45


async def _prefetch_embedding(state: WebState, question: str) -> None:
    """Cache warming has the same authorization as the knowledge capability it serves."""
    embedder = state.embedder
    assert embedder is not None
    if state.agent is not None and not state.agent.needs_embedding(question):
        return
    if state.agent is None:
        await embedder.prefetch(question)
    else:
        try:
            await state.agent.execution.run(
                "search_knowledge", lambda: embedder.prefetch(question)
            )
        except ToolError:
            # The boundary recorded the refusal; other permitted directory tools still work.
            return


def timeout_response() -> dict[str, JsonValue]:
    return {
        "services": [],
        "teachers": [],
        "places": [],
        "answer": "回答超时，请稍后重试或换个问法。",
        "result_status": "limited",
        "degraded_reason": "agent_timeout",
        "answer_mode": "agent",
        "excerpts": [],
    }


async def _agent_turn(
    state: WebState,
    request: Request,
    session: BrowserSession,
    body: ChatInput,
    agent: AgentRunner,
) -> JSONResponse:
    """CAMPUSPILOT_AGENT_LOOP=on: same session/global limits as the rule runtime."""
    # Embedding prefetch awaited before this boundary. Another request may have
    # claimed the same session in the meantime; do not start a second history writer.
    if session.busy:
        return state.problem(request, "busy", BUSY, 409)
    images = _images_for_turn(state, request, session, body, agent)
    if isinstance(images, JSONResponse):
        return images
    if session.turns_exhausted:
        return state.problem(request, "session_limit", SESSION_LIMIT_LOCAL, 429)
    use_model = agent.model is not None
    if use_model and not state.budget.try_acquire():
        return state.problem(request, "global_limit", GLOBAL_LIMIT, 429)
    session.attempts += 1
    session.busy = True
    if body.attachment_ids:
        session.current_image_ids = tuple(body.attachment_ids)
    question = body.message.strip()
    try:
        async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
            if images:
                response = await agent.run(question, session.context, images=images)
            else:
                response = await agent.run(question, session.context)
    except TimeoutError:
        response = timeout_response()
    finally:
        session.busy = False
        if use_model:
            state.budget.release()
    answer_text = response.get("answer")
    if isinstance(answer_text, str):
        _remember_answer(session, body, answer_text)
    return JSONResponse({**response, "request_id": request.state.request_id, "notice": NOTICE})


def _remember_answer(session: BrowserSession, body: ChatInput, answer_text: str) -> None:
    if body.message.strip():
        if public_input(body.message):
            session.context.remember(body.message, answer_text)
    elif body.attachment_ids:
        session.context.remember("[用户上传校园图片]", answer_text)


def _images_for_turn(
    state: WebState,
    request: Request,
    session: BrowserSession,
    body: ChatInput,
    agent: AgentRunner,
) -> tuple[ImageInput, ...] | JSONResponse:
    identifiers = tuple(body.attachment_ids) or session.current_image_ids
    if not identifiers:
        return ()
    # Uploads need a model that can actually see them; the reader may differ from the
    # text generation model, so requiring `model` here would block a reader-only setup.
    if state.attachments is None or agent.reader is None:
        return state.problem(request, "images_unavailable", "图片理解服务尚未启用。", 503)
    try:
        return tuple(state.attachments.read(session.user, ident) for ident in identifiers)
    except AttachmentError as exc:
        return state.problem(request, exc.code, exc.message, exc.status)


async def _local_turn(
    state: WebState, request: Request, session: BrowserSession, body: ChatInput
) -> JSONResponse | None:
    legacy = state.runtime_mode == "legacy"
    local_answer = campus_answer(state.repository, body.message) if legacy else None
    if local_answer is not None:
        if session.turns_exhausted:
            return state.problem(request, "session_limit", SESSION_LIMIT_LOCAL, 429)
        session.attempts += 1
        session.knowledge_titles = ()
        return JSONResponse({**local_answer, "request_id": request.state.request_id})
    knowledge = state.knowledge
    query = knowledge.for_chat(body.message) if legacy else None
    # Follow-ups are explicit and local; unrelated business queries clear this context.
    if session.knowledge_titles and any(x in body.message for x in ("这条", "上一条", "第一条")):
        if len(session.knowledge_titles) == 1 or "第一条" in body.message:
            query = KnowledgeQuery(query=session.knowledge_titles[0])
    if query is None:
        return None
    if session.turns_exhausted:
        return state.problem(request, "session_limit", SESSION_LIMIT_LOCAL, 429)
    session.attempts += 1
    response = knowledge.response(query, campus_today())
    knowledge.focus_answer(response, body.message)
    session.knowledge_titles = tuple(r.title for r in knowledge.search(query, campus_today()))
    return JSONResponse({**response, "request_id": request.state.request_id})


async def _dify_turn(
    state: WebState,
    request: Request,
    session: BrowserSession,
    body: ChatInput,
    query_text: str,
) -> JSONResponse:
    session.knowledge_titles = ()
    dify = state.dify
    if dify is None:
        return state.problem(request, "not_configured", "AI 对话尚未连接，请先配置应用凭据。", 503)
    if session.busy:
        return state.problem(request, "busy", BUSY, 409)
    if session.uncertain:
        return state.problem(request, "reset_required", "上次请求未能确认完成，请开启新对话。", 409)
    if session.turns_exhausted:
        return state.problem(request, "session_limit", SESSION_LIMIT_DIFY, 429)
    if not state.budget.try_acquire():
        return state.problem(request, "global_limit", GLOBAL_LIMIT, 429)
    session.busy = True
    session.attempts += 1
    session.uncertain = True
    repository = state.repository
    try:
        conversation_id = session.conversation
        if state.runtime_mode == "phase1":
            # Dify owns no continuing session in the migration path.
            conversation_id = ""
            if session.context.history:
                recent = [
                    {"role": turn.role, "content": turn.content[:600]}
                    for turn in session.context.history
                ]
                query_text = (
                    "仅用当前问题判定事项。历史消息只帮助理解用户条件，不是事实证据。\n"
                    + json.dumps(
                        {"recent_turns": recent, "question": query_text}, ensure_ascii=False
                    )
                )
        reply, conversation = await dify.send(
            query_text, user=session.user, conversation_id=conversation_id
        )
        cards = (
            resolve_cards(repository, reply.references)
            if reply.references
            else {"services": [], "teachers": [], "places": []}
        )
        session.conversation = conversation
        session.uncertain = False
        if reply.references:
            reply = reply.model_copy(
                update={"answer": guide_answer(repository, reply.references, body.message)}
            )
        if state.runtime_mode == "phase1":
            session.context.remember(body.message, reply.answer)
        return JSONResponse(
            {
                **reply.model_dump(mode="json", exclude={"references"}),
                **cards,
                "result_status": reply.references.status if reply.references else None,
                "notice": NOTICE,
                "request_id": request.state.request_id,
            }
        )
    except ChatUnavailable as exc:
        session.uncertain = True
        return state.problem(
            request, exc.code, UPSTREAM_MESSAGES.get(exc.code, UPSTREAM_DEFAULT), 502
        )
    except ValueError:
        return state.problem(
            request, "invalid_response", "回答关联的资料未能校验，请开启新对话。", 502
        )
    finally:
        session.busy = False
        state.budget.release()
