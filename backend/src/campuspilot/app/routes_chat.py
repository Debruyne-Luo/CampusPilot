"""POST /api/chat: backend runtime (phase1/phase2), local answers, then Dify."""

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from campuspilot.app.state import NOTICE, BrowserSession, WebState
from campuspilot.app.validation import ChatInput
from campuspilot.chat_runtime import PreparedQuery, public_input
from campuspilot.dify import ChatUnavailable
from campuspilot.knowledge import KnowledgeQuery, campus_today
from campuspilot.presentation import guide_answer, resolve_cards
from campuspilot.retrieval import campus_answer

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


def register(app: FastAPI, state: WebState) -> None:
    @app.post("/api/chat")
    async def chat(body: ChatInput, request: Request) -> JSONResponse:
        session = state.session_for(request)
        if session.busy:
            return state.problem(request, "busy", BUSY, 409)
        query_text = body.message.strip()
        if state.runtime_mode != "legacy":
            if state.embedder is not None and state.runtime_mode == "phase2":
                # Fill the query-vector cache off the sync path; failure means BM25-only.
                await state.embedder.prefetch(query_text)
            prepared = state.runtime.prepare(query_text, session.context, request.state.request_id)
            query_text = prepared.query
            if prepared.route != "legacy_knowledge":
                return await _runtime_turn(state, request, session, body, prepared)
        local = await _local_turn(state, request, session, body)
        if local is not None:
            return local
        return await _dify_turn(state, request, session, body, query_text)


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
