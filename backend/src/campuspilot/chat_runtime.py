"""One bounded backend router; Jev and Dify management are outside this module."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, cast

from pydantic import JsonValue

from campuspilot.agent.verify import missing_premise, unsafe_text, unsupported_numbers
from campuspilot.chat_model import ChatTurn, ProductionModel
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.assist import AssistInput, AssistResponse, assist
from campuspilot.directory.lookup import ServiceKey
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeQuery, KnowledgeStore, campus_today
from campuspilot.presentation import AnswerEnvelope, guide_answer, resolve_cards, service_summary
from campuspilot.rag import RetrievalFilters, RetrievalHit, SnapshotStore
from campuspilot.retrieval import campus_answer
from campuspilot.retrieval.applicability import (
    conditional_text,
    evidence_metadata,
    query_filters,
    scope_notes,
)
from campuspilot.retrieval.bm25 import terms
from campuspilot.retrieval.context import (
    CONTEXT_BUDGET_NOTICE,
    CONTEXT_BUDGET_REASON,
    context_complete,
    section_context,
)

Mode = Literal["legacy", "phase1", "phase2"]
EMPTY_CARDS: dict[str, JsonValue] = {"services": [], "teachers": [], "places": []}
TOPIC_WORDS = (
    ("校园卡", "补卡", "挂失", "解挂"),
    ("在读证明", "学籍证明"),
    ("票据", "学费发票", "学杂费电子"),
    ("邮箱",),
    ("校园网", "VPN"),
    ("图书馆",),
    ("维修",),
    ("银行卡", "银行账户"),
)


@dataclass
class ImageTask:
    """A user-requested image task, never an inferred campus fact or authority."""

    objective: str = ""
    kind: Literal["reading", "campus"] = "reading"


@dataclass
class ConversationContext:
    service_focus: str | None = None
    history: tuple[ChatTurn, ...] = ()
    focus: str = ""
    topic: str = ""
    audience: str = "unknown"
    academic_year: str | None = None
    campus: str = "chengdu"
    knowledge_titles: tuple[str, ...] = ()
    destination_candidates: list[dict[str, JsonValue]] = field(default_factory=list)
    image_task: ImageTask | None = None
    image_attachment_ids: tuple[str, ...] = ()

    def remember(self, question: str, answer: str) -> None:
        self.history = (
            *self.history,
            ChatTurn(role="user", content=question[:2000]),
            ChatTurn(role="assistant", content=answer[:8000]),
        )[-16:]


@dataclass(frozen=True)
class PreparedQuery:
    query: str
    route: str
    response: dict[str, JsonValue] | None = None
    evidence: str = ""
    allowed_sources: frozenset[str] = frozenset()
    hits: tuple[RetrievalHit, ...] = ()
    model_needed: bool = False


def filters_for(question: str, context: ConversationContext) -> RetrievalFilters:
    return query_filters(
        question, campus_today(), audience=context.audience,
        academic_year=context.academic_year, campus=context.campus,
    )


def public_input(question: str) -> bool:
    # Coordinates and credentials cannot leak through a later turn's context window.
    return not re.search(
        r"[-+]?\d{1,3}\.\d{4,}\s*[,，]\s*[-+]?\d{1,2}\.\d{4,}|"
        r"\b\d{1,3}\.\d{4,}\b|"
        r"(?:我的|本人).{0,4}(?:密码|账号|学号|身份证号)\s*(?:是|为|：|:)?\s*[A-Za-z0-9_-]{3,}|"
        r"(?:密码|口令|密钥|身份证号|学号)[是为：:]\s*\S+|\b(?:sk-|app-)[A-Za-z0-9]{12,}",
        question,
    )


class ChatRuntime:
    def __init__(
        self,
        repository: DirectoryRepository,
        knowledge: KnowledgeStore,
        snapshots: SnapshotStore,
        *,
        mode: Mode,
        model: ProductionModel | None = None,
        approved_direct_rules: frozenset[str] = frozenset(),
    ) -> None:
        self.repository = repository
        self.knowledge = knowledge
        self.snapshots = snapshots
        self.mode = mode
        self.model = model
        self.approved_direct_rules = approved_direct_rules
        pinned = snapshots.acquire() if approved_direct_rules and mode == "phase2" else None
        self._rule_knowledge_version = pinned.snapshot.version if pinned else None

    def embedding_question(self, question: str, context: ConversationContext) -> str:
        """Resolve the same follow-up text before warming the query-vector cache."""
        original = question
        people = self.repository.search_teacher()
        named = {t.teacher_id for t in people if any(n in original for n in (t.name, *t.aliases))}
        focused = {
            t.teacher_id for t in people if any(n in context.focus for n in (t.name, *t.aliases))
        }
        teacher_reference = any(
            text in original for text in ("这位老师", "那位老师", "该老师", "这位教授", "那位教授")
        )
        was_teacher = context.topic == "teacher"
        # Inherit only on explicit continuation, and never use past model prose as authority.
        continuation = bool(
            re.match(
                r"^(那|这个|这位|这条|它|上一条|第一条|还需要|我是本科|我是研究生|要准备|"
                r"准备哪些|需要哪些|多久|多少钱|要带什么|材料呢|电话呢|具体在哪)",
                question,
            )
        )
        old_topics = {
            i for i, words in enumerate(TOPIC_WORDS) if any(w in context.focus for w in words)
        }
        new_topics = {i for i, words in enumerate(TOPIC_WORDS) if any(w in question for w in words)}
        if new_topics and new_topics <= old_topics:
            continuation = True
        if new_topics - old_topics:
            continuation = False
        if named and named != focused:
            continuation = False
        if (
            was_teacher
            and any(word in original for word in ("老师", "教授"))
            and not named
            and not teacher_reference
        ):
            continuation = False
        if continuation and context.focus:
            previous = context.focus
            if any(word in original for word in ("本科", "研究生", "教职工")):
                previous = re.sub(r"本科生?|研究生|教职工", "", previous)
            if any(word in original for word in ("成都", "宜宾", "峨眉")):
                previous = re.sub(r"(?:成都|宜宾|峨眉)(?:校区)?", "", previous)
            if re.search(r"20\d{2}\s*[-—–至]\s*20\d{2}", original):
                previous = re.sub(r"20\d{2}\s*[-—–至]\s*20\d{2}(?:学年)?", "", previous)
            question = previous + "；" + question

        return question

    def prepare(
        self, question: str, context: ConversationContext, request_id: str
    ) -> PreparedQuery:
        if not public_input(question):
            return self._local(
                question,
                "private_input",
                "请移除个人位置、账号或密码，再询问公开资料。",
                "needs_clarification",
            )
        original = question
        people = self.repository.search_teacher()
        named = {t.teacher_id for t in people if any(n in original for n in (t.name, *t.aliases))}
        teacher_reference = any(
            text in original for text in ("这位老师", "那位老师", "该老师", "这位教授", "那位教授")
        )
        was_teacher = context.topic == "teacher"
        # Inherit only on explicit continuation, and never use past model prose as authority.
        resolved = self.embedding_question(question, context)
        if resolved != question:
            question = resolved
        else:
            context.audience = "unknown"
            context.academic_year = None
            context.campus = "chengdu"
            context.history = ()
            context.knowledge_titles = ()
        if "本科" in original:
            context.audience = "undergraduate"
        elif "研究生" in original:
            context.audience = "graduate"
        elif "教职工" in original:
            context.audience = "staff"
        year = re.search(r"(20\d{2})\s*[-—–至]\s*(20\d{2})", original)
        if year:
            context.academic_year = f"{year[1]}-{year[2]}"
        context.campus = filters_for(original, context).campus
        local = campus_answer(self.repository, question)
        if local is not None:
            context.focus = question[:200]
            context.topic = "campus"
            context.knowledge_titles = ()
            return PreparedQuery(query=question, route="campus", response=local)
        if "银行卡" in original and "校园卡" not in original:
            context.focus = ""
            context.topic = ""
            return self._local(
                question,
                "outside_campus_card",
                "目前资料覆盖校园卡事务。银行卡问题需向发卡行核实。",
                "needs_clarification",
            )
        if (
            not named
            and not (was_teacher and teacher_reference)
            and any(word in original for word in ("老师", "教授"))
            and (
                was_teacher
                or any(word in original for word in ("办公室", "联系", "电话", "主页", "研究方向"))
            )
        ):
            context.focus = ""
            context.topic = "teacher"
            return self._local(
                question,
                "unknown_teacher",
                "请补充教师全名和学院，当前目录无法确认这位教师。",
                "needs_clarification",
            )
        if "综合科" in question and not any(name in question for name in ("教务处", "学生处")):
            return self._local(
                question,
                "ambiguous_department",
                "请说明是教务处综合科还是学生处综合科。",
                "needs_clarification",
            )
        # A single request pins one immutable version, including service evidence.
        try:
            retriever = self.snapshots.acquire() if self.mode == "phase2" else None
        except (OSError, ValueError, KeyError, TypeError):
            retriever = None
        directory = self._directory(question, context, request_id)
        if directory is not None:
            body, rule = directory
            context.focus = question[:200]
            context.topic = rule
            context.knowledge_titles = ()
            response = self._directory_response(body, question)
            evidence_rows = [
                e.model_dump(mode="json")
                for e in body.evidence
                if e.source_authority != "map_provider"
            ]
            hits = (
                retriever.search(question, filters_for(question, context))
                if retriever and rule == "service"
                else ()
            )
            card_query = any(word in question for word in ("校园卡", "补卡", "挂失", "解挂"))
            hits = tuple(h for h in hits if card_query and h.chunk.topic_id == "card")[:4]
            filters = filters_for(question, context)
            expanded = section_context(retriever.snapshot, hits, filters) if retriever else ()
            supplement_complete = not retriever or context_complete(
                retriever.snapshot, hits, expanded, filters
            )
            evidence_hits = (*hits, *expanded) if supplement_complete else ()
            if not supplement_complete:
                response["answer"] = str(response["answer"]) + "\n" + CONTEXT_BUDGET_NOTICE
                response["degraded_reason"] = CONTEXT_BUDGET_REASON
            supplements = [
                {
                    "source_id": h.source.source_id,
                    "chunk_id": h.chunk.chunk_id,
                    "title": h.chunk.title,
                    "text": h.chunk.text,
                    **evidence_metadata(h.chunk, filters),
                    "kind": h.chunk.kind,
                    "applicability": h.source.applicability,
                    "temporal_status": h.source.temporal_status,
                }
                for h in evidence_hits
            ]
            evidence = json.dumps(
                {
                    "directory_answer": response["answer"],
                    "services": [s.model_dump(mode="json") for s in body.services],
                    "teachers": [t.model_dump(mode="json") for t in body.teachers],
                    "sources": [{**e, "source_id": e["evidence_id"]} for e in evidence_rows],
                    "same_topic_supplements": supplements,
                },
                ensure_ascii=False,
            )
            certified = rule in self.approved_direct_rules and (
                self.mode != "phase2"
                or retriever is not None
                and retriever.snapshot.version == self._rule_knowledge_version
            )
            direct = body.status != "success" or certified
            if evidence_hits:
                response["knowledge_version"] = evidence_hits[0].knowledge_version
                existing = response.get("excerpts", [])
                assert isinstance(existing, list)
                response["excerpts"] = cast(
                    list[JsonValue],
                    [
                        *existing,
                        *[
                            {
                                "document": h.chunk.title,
                                "content": h.chunk.text,
                                "source_id": h.source.source_id,
                                "chunk_id": h.chunk.chunk_id,
                                "source_url": h.source.url,
                                **evidence_metadata(h.chunk, filters),
                                "kind": h.chunk.kind,
                                "temporal_status": h.source.temporal_status,
                            }
                            for h in evidence_hits
                        ],
                    ],
                )
            return PreparedQuery(
                query=question,
                route=rule,
                response=response,
                evidence=evidence,
                allowed_sources=frozenset(
                    e.evidence_id for e in body.evidence if e.source_authority != "map_provider"
                )
                | frozenset(h.source.source_id for h in evidence_hits),
                hits=hits,
                model_needed=not direct,
            )
        # Pin one version through routing, retrieval and generation.
        hits = retriever.search(question, filters_for(question, context)) if retriever else ()
        query = self.knowledge.for_chat(question)
        if context.knowledge_titles and any(x in original for x in ("这条", "上一条", "第一条")):
            if len(context.knowledge_titles) == 1 or "第一条" in original:
                query = KnowledgeQuery(query=context.knowledge_titles[0])
        if query is not None:
            records = self.knowledge.search(query, campus_today())
            # Empty topic searches may have a match in the newer, separate corpus.
            precise_new_match = (
                bool(hits)
                and len(
                    terms(question).keys()
                    & terms(hits[0].chunk.title + " " + hits[0].chunk.aliases).keys()
                )
                >= 2
            )
            specific_old_match = any(
                word.casefold() in question.casefold()
                for record in records
                for word in record.keywords
                if word not in {"学生", "本科", "研究生", "教职工", "校园", "学校"}
            )
            explicit_listing = any(
                word in question for word in ("通知", "公告", "活动", "讲座", "比赛")
            )
            if (records and specific_old_match and not precise_new_match) or explicit_listing:
                notice_response = self.knowledge.response(query, campus_today())
                self.knowledge.focus_answer(notice_response, original)
                context.knowledge_titles = tuple(r.title for r in records)
                context.focus = records[0].title if len(records) == 1 else ""
                context.topic = "notices"
                return PreparedQuery(
                    query=question,
                    route="notices",
                    response=cast(dict[str, JsonValue], notice_response),
                )
        context.knowledge_titles = ()
        if self.mode == "phase1":
            context.focus = question[:200]
            return PreparedQuery(query=question, route="legacy_knowledge")
        if retriever is None:
            return self._local(
                question, "empty", "尚无匹配的已发布资料，请补充事项或查看官方入口。"
            )
        if not hits:
            context.focus = ""
            context.topic = ""
            return self._local(
                question, "empty", "已发布资料中没有足够依据回答，请补充事项或查看官方资料。"
            )
        context.focus = hits[0].chunk.title
        context.topic = hits[0].chunk.topic_id
        selected = hits[:4]
        filters = filters_for(question, context)
        expanded = section_context(retriever.snapshot, selected, filters)
        if not context_complete(retriever.snapshot, selected, expanded, filters):
            return PreparedQuery(query=question, route="rag", response={
                **EMPTY_CARDS, "answer": CONTEXT_BUDGET_NOTICE,
                "result_status": "empty", "answer_mode": "backend_rag",
                "degraded_reason": CONTEXT_BUDGET_REASON,
                "knowledge_version": retriever.snapshot.version,
                "source_ids": [], "excerpts": [],
            })
        selected = (*selected, *expanded)
        evidence = json.dumps(
            [
                {
                    "source_id": h.source.source_id,
                    "chunk_id": h.chunk.chunk_id,
                    "title": h.chunk.title,
                    "text": h.chunk.text,
                    **evidence_metadata(h.chunk, filters),
                    "campuses": list(h.chunk.campuses),
                    "audiences": list(h.chunk.audiences),
                    "academic_year": h.chunk.academic_year,
                    "kind": h.chunk.kind,
                    "applicability": h.source.applicability,
                    "temporal_status": h.source.temporal_status,
                    "locator": h.chunk.locator,
                    "content_scope": h.source.content_scope,
                }
                for h in selected
            ],
            ensure_ascii=False,
        )
        rag_response: dict[str, JsonValue] = {
            **EMPTY_CARDS,
            "answer": "已收录的资料摘要如下，请注意来源适用范围。\n"
            + "\n".join(f"{h.chunk.title}：{conditional_text(h.chunk, filters)}" for h in selected),
            "result_status": "limited",
            "answer_mode": "backend_rag",
            "knowledge_version": selected[0].knowledge_version,
            "excerpts": [
                {
                    "document": h.chunk.title,
                    "content": h.chunk.text,
                    "source_id": h.source.source_id,
                    "chunk_id": h.chunk.chunk_id,
                    "source_url": h.source.url,
                    "kind": h.chunk.kind,
                    "locator": h.chunk.locator,
                    "temporal_status": h.source.temporal_status,
                    "document_id": h.chunk.document_id,
                    "revision_id": h.chunk.revision_id,
                    "text_sha256": h.chunk.text_sha256,
                    "scope_notes": list(scope_notes(h.chunk, filters)),
                    "table_headers": list(h.chunk.table_headers),
                    "footnotes": list(h.chunk.footnotes),
                }
                for h in selected
            ],
        }
        return PreparedQuery(
            query=question,
            route="rag",
            response=rag_response,
            evidence=evidence,
            hits=hits,
            allowed_sources=frozenset(h.source.source_id for h in selected),
            model_needed=True,
        )

    def _directory(
        self, question: str, context: ConversationContext, request_id: str
    ) -> tuple[AssistResponse, str] | None:
        teachers = tuple(
            t
            for t in self.repository.search_teacher()
            if any(n in question for n in (t.name, *t.aliases))
        )
        if teachers and (
            context.topic == "teacher"
            or any(
                x in question
                for x in (
                    "老师",
                    "教师",
                    "办公室",
                    "联系",
                    "在哪",
                    "哪里",
                    "电话",
                    "邮箱",
                    "主页",
                    "研究方向",
                )
            )
        ):
            query = teachers[0].name if len(teachers) == 1 else ""
            if not query:
                return AssistResponse(
                    request_id=request_id,
                    status="needs_clarification",
                    message="请一次指定一位教师，或补充学院与校区。",
                ), "teacher"
            return assist(
                self.repository, AssistInput(kind="teacher", query=query), request_id
            ), "teacher"
        key: ServiceKey = "unknown"
        if "挂失" in question and any(x in question for x in ("卡", "校园")):
            key = "campus_card_loss"
        elif any(x in question for x in ("补卡", "校园卡补办")):
            key = "campus_card_replacement"
        elif any(x in question for x in ("在读证明", "学籍证明")):
            key = "enrollment_proof"
        elif any(x in question for x in ("票据", "学费发票", "学杂费电子")):
            key = "tuition_receipt"
        if key == "unknown":
            return None
        if "本科" in question:
            context.audience = "undergraduate"
        elif "研究生" in question:
            context.audience = "graduate"
        elif "教职工" in question:
            context.audience = "staff"
        year = re.search(r"(20\d{2})\s*[-—–至]\s*(20\d{2})", question)
        if year:
            context.academic_year = f"{year[1]}-{year[2]}"
        if key == "enrollment_proof" and context.audience == "undergraduate":
            # New corpus has an index entry, not the graduate procedure.
            return None
        body = AssistInput.model_validate_json(
            json.dumps(
                {
                    "kind": "service",
                    "service_key": key,
                    "audience": context.audience,
                    "academic_year": context.academic_year,
                }
            )
        )
        return assist(self.repository, body, request_id), "service"

    def _directory_response(self, result: AssistResponse, question: str) -> dict[str, JsonValue]:
        success = result.status in {"success", "needs_clarification"}
        envelope = AnswerEnvelope(
            schema_version=1,
            status=result.status,
            answer=result.message,
            service_ids=tuple(s.service_id for s in result.services) if success else (),
            teacher_ids=tuple(t.teacher_id for t in result.teachers) if success else (),
            place_ids=tuple(p.place_id for p in result.places) if success else (),
        )
        answer = guide_answer(self.repository, envelope, question)
        if result.status == "success" and result.services and answer == result.message:
            service = result.services[0]
            answer = service_summary(service)
        if result.status == "success" and result.teachers and answer == result.message:
            t = result.teachers[0]
            answer = f"{t.name}，{t.department}；办公室：{t.office or '未收录'}。"
            if any(x in question for x in ("电话", "邮箱", "联系")):
                answer += "教师个人联系方式未收录，请查看公开教师主页。"
        return {
            **resolve_cards(self.repository, envelope),
            "answer": answer,
            "result_status": result.status,
            "answer_mode": "backend_directory",
            "excerpts": [
                {
                    "document": e.source_reference,
                    "content": e.locator,
                    "source_id": e.evidence_id,
                    "source_url": str(e.source_url) if e.source_url else None,
                }
                for e in result.evidence
            ],
        }

    @staticmethod
    def _local(query: str, route: str, answer: str, status: str = "empty") -> PreparedQuery:
        return PreparedQuery(
            query=query,
            route=route,
            response={
                **EMPTY_CARDS,
                "answer": answer,
                "excerpts": [],
                "result_status": status,
                "answer_mode": "backend_local",
            },
        )

    async def generate(
        self, prepared: PreparedQuery, history: tuple[ChatTurn, ...]
    ) -> dict[str, JsonValue]:
        if self.model is None or not prepared.model_needed:
            return (
                self.limited(prepared, "model_not_configured")
                if prepared.model_needed
                else (prepared.response or {})
            )
        reply = await self.model.generate(prepared.query, prepared.evidence, history)
        result = reply.result
        if set(result.source_ids) - prepared.allowed_sources or (
            result.status == "success" and not result.source_ids
        ):
            raise ChatUnavailable("invalid_response")
        if unsafe_text(result.answer) or unsupported_numbers(result.answer, prepared.evidence):
            raise ChatUnavailable("invalid_response")
        # A short generated service answer must retain this source's critical prerequisite.
        local_answer = str((prepared.response or {}).get("answer", ""))
        if prepared.route == "service" and missing_premise(result.answer, local_answer):
            raise ChatUnavailable("required_premise_missing")
        evidence_rows = json.loads(prepared.evidence) if prepared.evidence else []
        if isinstance(evidence_rows, dict):
            evidence_rows = evidence_rows.get("same_topic_supplements", [])
        notes = [str(row.get("title")) + "：" + "；".join(row["scope_notes"])
                 for row in evidence_rows if isinstance(row, dict) and row.get("scope_notes")
                 and row.get("source_id") in result.source_ids] \
            if isinstance(evidence_rows, list) else []
        answer = ("适用限制：\n" + "\n".join(dict.fromkeys(notes)) + "\n\n" if notes else "")
        context_notice = "\n" + CONTEXT_BUDGET_NOTICE if (prepared.response or {}).get(
            "degraded_reason"
        ) == CONTEXT_BUDGET_REASON else ""
        return {
            **(prepared.response or EMPTY_CARDS),
            "answer": answer + result.answer + context_notice,
            "source_ids": list(result.source_ids),
            "result_status": result.status,
            "answer_mode": "backend_rag" if prepared.route == "rag" else "backend_generated",
        }

    @staticmethod
    def limited(prepared: PreparedQuery, reason: str) -> dict[str, JsonValue]:
        response = {
            **(prepared.response or EMPTY_CARDS),
            "result_status": "limited",
            "degraded_reason": reason,
        }
        answer = response.get("answer")
        if isinstance(answer, str):
            response["answer"] = "暂时只能提供已收录的资料摘要：\n" + answer
        return response
