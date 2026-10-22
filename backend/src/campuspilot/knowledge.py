"""Source-backed campus notices and guides; bounded local retrieval, no network or LLM."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, TypeAdapter, model_validator

from campuspilot.contracts import Contract

Audience = Literal["all", "undergraduate", "graduate", "staff", "alumni"]
Category = Literal["all", "guide", "notice", "event"]
Period = Literal["all", "current", "week", "registration", "history"]
CHINA = timezone(timedelta(hours=8))
_campus_date: ContextVar[date | None] = ContextVar("campuspilot_campus_date", default=None)


def campus_today() -> date:
    return _campus_date.get() or datetime.now(CHINA).date()


@contextmanager
def campus_clock(today: date) -> Iterator[None]:
    """Application-owned fixture clock; scoped to this async context and its workers."""
    token = _campus_date.set(today)
    try:
        yield
    finally:
        _campus_date.reset(token)


def official_url(value: str, *, wechat: bool = False) -> str:
    url = urlsplit(value)
    host = url.hostname or ""
    if (
        url.scheme != "https"
        or url.username
        or url.password
        or url.fragment
        or url.port not in (None, 443)
        or not (
            host == "cdut.edu.cn"
            or host.endswith(".cdut.edu.cn")
            or (wechat and host == "mp.weixin.qq.com" and url.path.startswith("/s"))
        )
    ):
        raise ValueError("Expected an official campus source URL")
    return value


class KnowledgeRecord(Contract):
    record_id: Annotated[str, Field(pattern=r"^cdut:knowledge:[a-z0-9-]+$")]
    title: Annotated[str, Field(min_length=2, max_length=160)]
    category: Literal["guide", "notice", "event"]
    publisher: Annotated[str, Field(min_length=2, max_length=160)]
    source_url: str
    source_kind: Literal["official_site", "official_wechat"] = "official_site"
    publisher_evidence_url: str | None = None
    adoption: Literal["official_document"] = "official_document"
    accessed_via: Literal["official_page", "official_search_index", "provided_document"]
    published_on: date | None
    collected_on: date
    summary: Annotated[str, Field(min_length=2, max_length=500)]
    details: Annotated[tuple[str, ...], Field(min_length=1, max_length=12)]
    keywords: Annotated[tuple[str, ...], Field(min_length=1, max_length=30)]
    audiences: Annotated[tuple[Audience, ...], Field(min_length=1)] = ("all",)
    audience_text: str
    locator: str
    valid_from: date | None = None
    valid_until: date | None = None
    registration_from: date | None = None
    registration_until: date | None = None
    event_from: date | None = None
    event_until: date | None = None
    place_ids: tuple[str, ...] = ()
    location_text: str | None = None
    action_url: str | None = None
    action_label: str | None = None
    supersedes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        official_url(self.source_url, wechat=self.source_kind == "official_wechat")
        if self.source_kind == "official_wechat":
            if urlsplit(self.source_url).hostname != "mp.weixin.qq.com":
                raise ValueError("WeChat record requires an article URL")
            if not self.publisher_evidence_url:
                raise ValueError("WeChat publisher needs official campus attribution")
        if self.publisher_evidence_url:
            official_url(self.publisher_evidence_url)
        if self.action_url:
            official_url(self.action_url)
        if bool(self.action_url) != bool(self.action_label):
            raise ValueError("Action link requires a label and URL")
        for start, end in (
            (self.valid_from, self.valid_until),
            (self.registration_from, self.registration_until),
            (self.event_from, self.event_until),
        ):
            if start and end and start > end:
                raise ValueError("Reversed date interval")
        if self.published_on and self.published_on > self.collected_on:
            raise ValueError("Publication is later than collection")
        if any(not x.strip() or len(x) > 1000 for x in self.details):
            raise ValueError("Invalid source details")
        if any(len(x.strip()) < 2 or len(x) > 60 for x in self.keywords):
            raise ValueError("Invalid retrieval keyword")
        return self

    def status(self, today: date) -> str:
        if self.valid_until and self.valid_until < today:
            return "ended"
        if self.valid_from and self.valid_from > today:
            return "upcoming"
        if self.category == "guide":
            return "reference"
        if self.valid_from and self.valid_until:
            return "current"
        return "undated"


class KnowledgeQuery(Contract):
    query: Annotated[str, Field(max_length=2000)] = ""
    category: Category = "all"
    audience: Audience = "all"
    period: Period = "all"


class KnowledgeStore:
    def __init__(self, records: tuple[KnowledgeRecord, ...]) -> None:
        if len(records) > 2000:
            raise ValueError("Knowledge snapshot too large")
        ids = {r.record_id for r in records}
        if len(ids) != len(records) or len({r.source_url for r in records}) != len(records):
            raise ValueError("Duplicate knowledge record or source URL")
        for r in records:
            if r.record_id in r.supersedes or any(x not in ids for x in r.supersedes):
                raise ValueError("Invalid supersession reference")
        graph = {r.record_id: r.supersedes for r in records}

        def visit(ident: str, path: frozenset[str]) -> None:
            if ident in path:
                raise ValueError("Cyclic supersession")
            for other in graph[ident]:
                visit(other, path | {ident})

        for ident in graph:
            visit(ident, frozenset())
        self.records = records

    @classmethod
    def load(cls, path: Path) -> KnowledgeStore:
        if not path.exists():
            return cls(())
        if path.stat().st_size > 4_000_000:
            raise ValueError("Knowledge file too large")
        records = TypeAdapter(tuple[KnowledgeRecord, ...]).validate_json(path.read_bytes())
        return cls(records)

    def search(self, query: KnowledgeQuery, today: date) -> tuple[KnowledgeRecord, ...]:
        text = query.query.casefold().strip()
        # Remove common question scaffolding; unknown topics still produce no matches.
        clean = re.sub(
            r"最近|近期|本周|这周|今天|现在|目前|还有|哪些|什么|有没有|可以|怎么|如何|"
            r"通知|公告|活动|资料|报名|截止|历史|以前|本科生|研究生|老师|教职工|校友|"
            r"查询|帮我|请问|查看|看看|校园|学校|成都理工大学|[\s，。？?！!：:的了吗呢和与]",
            "",
            text,
        )
        generic = not clean or clean in {"有", "全部", "所有", "信息", "指南", "办事", "办事指南"}
        tokens = set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2}", clean))
        replaced = {
            i
            for r in self.records
            if (not r.published_on or r.published_on <= today)
            and (not r.valid_from or r.valid_from <= today)
            for i in r.supersedes
        }
        found: list[tuple[int, KnowledgeRecord]] = []
        week_end = today + timedelta(days=6 - today.weekday())
        for r in self.records:
            if r.published_on and r.published_on > today:
                continue
            historical = r.status(today) == "ended" or r.record_id in replaced
            if query.period != "history" and r.record_id in replaced:
                continue
            if query.category != "all" and r.category != query.category:
                continue
            if (
                query.audience != "all"
                and "all" not in r.audiences
                and query.audience not in r.audiences
            ):
                continue
            if query.period == "history" and not historical:
                continue
            if query.period == "current" and r.status(today) != "current":
                continue
            if query.period == "registration" and not (
                r.registration_from
                and r.registration_until
                and r.registration_from <= today <= r.registration_until
                and not historical
            ):
                continue
            if (query.period == "week" or any(w in text for w in ("本周", "这周"))) and not (
                r.event_from
                and r.event_until
                and r.event_from <= week_end
                and r.event_until >= today
                and not historical
            ):
                continue
            corpus = " ".join((r.title, r.summary, *r.keywords, *r.details)).casefold()
            years = set(re.findall(r"20\d{2}", text))
            dated_corpus = corpus + " ".join(
                str(d)
                for d in (
                    r.published_on,
                    r.valid_from,
                    r.valid_until,
                    r.event_from,
                    r.registration_until,
                )
                if d
            )
            if years and not any(year in dated_corpus for year in years):
                continue
            exact = sum(len(k) for k in r.keywords if k.casefold() in text)
            score = exact * 10 + sum(1 for t in tokens if t in corpus)
            if not generic and not exact and (not tokens or score / len(tokens) < 0.6):
                continue
            found.append((score, r))
        found.sort(
            key=lambda x: (x[0], x[1].published_on or date.min, x[1].record_id), reverse=True
        )
        return tuple(r for _, r in found[:20])

    def for_chat(self, text: str) -> KnowledgeQuery | None:
        lower = text.casefold()
        explicit = any(x in lower for x in ("通知", "公告", "活动", "讲座", "比赛", "报名", "征集"))
        supported = any(k.casefold() in lower for r in self.records for k in r.keywords)
        # Existing structured service/faculty/place workflows remain authoritative.
        business = any(
            x in lower for x in ("老师", "办公室", "补卡", "补办", "挂失", "在读证明", "票据")
        )
        if not explicit and (not supported or business):
            return None
        period: Period = "all"
        if any(x in lower for x in ("历史", "以前", "往年", "已结束")):
            period = "history"
        elif any(x in lower for x in ("还能报名", "可以报名", "可报名", "没截止", "未截止")):
            period = "registration"
        elif "本周" in lower or "这周" in lower:
            period = "week"
        elif explicit and any(x in lower for x in ("最近", "近期", "今天", "现在", "目前")):
            period = "current"
        audience: Audience = "all"
        for word, value in (
            ("本科", "undergraduate"),
            ("研究生", "graduate"),
            ("教职工", "staff"),
            ("校友", "alumni"),
        ):
            if word in lower:
                audience = value  # type: ignore[assignment]
                break
        category: Category = "event" if any(x in lower for x in ("活动", "讲座", "比赛")) else "all"
        return KnowledgeQuery(query=text, period=period, audience=audience, category=category)

    def response(self, query: KnowledgeQuery, today: date) -> dict[str, object]:
        records = self.search(query, today)
        replaced = {
            i
            for r in self.records
            if (not r.published_on or r.published_on <= today)
            and (not r.valid_from or r.valid_from <= today)
            for i in r.supersedes
        }
        cards = [
            {
                **r.model_dump(mode="json"),
                "time_status": "superseded" if r.record_id in replaced else r.status(today),
                "registration_open": bool(
                    r.registration_from
                    and r.registration_until
                    and r.registration_from <= today <= r.registration_until
                    and r.status(today) != "ended"
                    and r.record_id not in replaced
                ),
            }
            for r in records
        ]
        if not records:
            answer = "已收录的官方资料中没有符合条件的结果，可调整关键词或查看学校官网。"
            if query.period != "all":
                answer = "已收录的官方资料中没有符合该时间条件的通知。这不代表学校没有相关安排。"
        elif len(records) == 1:
            r = records[0]
            prefix = "该通知适用时间已结束。" if r.status(today) == "ended" else ""
            if r.record_id in replaced:
                prefix = "该资料已有后续版本，以下为历史内容。"
            answer = prefix + r.summary
        else:
            answer = f"找到 {len(records)} 条相关官方资料，选择一条查看要求、时间和原文。"
        return {
            "answer": answer,
            "knowledge": cards,
            "result_status": "success" if records else "empty",
            "services": [],
            "teachers": [],
            "places": [],
            "excerpts": [],
            "as_of": today.isoformat(),
            "collected_on": max((r.collected_on.isoformat() for r in self.records), default=None),
            "answer_mode": "official_retrieval",
        }

    @staticmethod
    def focus_answer(response: dict[str, object], question: str) -> None:
        cards = response.get("knowledge")
        if not isinstance(cards, list) or len(cards) != 1:
            return
        card = cards[0]
        prefix = "该通知适用时间已结束。" if card["time_status"] == "ended" else ""
        if any(word in question for word in ("截止", "还能报名", "怎么报名")):
            deadline = card["registration_until"]
            response["answer"] = prefix + (
                f"原文报名/征集截止日期为 {deadline}；具体提交要求请查看原文。"
                if deadline
                else "这份资料未提供明确的报名截止日期，请查看原文中的适用要求。"
            )
        elif any(word in question for word in ("在哪里", "在哪", "地点")):
            response["answer"] = prefix + (card["location_text"] or "这份资料未收录明确地点。")
        elif any(word in question for word in ("适合", "面向", "参加条件", "适用", "能参加")):
            response["answer"] = prefix + "适用对象：" + card["audience_text"]
        elif "开放" in question or "几点" in question:
            response["answer"] = prefix + "这份资料未提供今天的开放安排，请查看发布部门的当期公告。"


def dump_records(records: tuple[KnowledgeRecord, ...]) -> str:
    return (
        json.dumps([r.model_dump(mode="json") for r in records], ensure_ascii=False, indent=2)
        + "\n"
    )
