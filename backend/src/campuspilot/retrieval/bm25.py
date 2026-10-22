"""BM25 over Chinese 2/3-gram and ASCII word terms, with a weighted title field.

Hard filters (enabled, validity window, historical, audience, academic year) are applied in
`eligible()`, shared by every retriever so fusion only ever sees admissible chunks.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, RetrievalFilters, RetrievalHit
from campuspilot.retrieval.applicability import campus_value

GENERIC = ("请问", "如何", "怎么", "什么", "哪里", "你好", "谢谢", "是否")
# Colloquial -> official wording appended to the query (never replaces it). Built only from
# failures on the dev set (evaluation/dev-colloquial-20261011), never from the test set.
SYNONYMS: tuple[tuple[str, str], ...] = (
    ("饭卡", "校园卡"),
    ("一卡通", "校园卡"),
    ("寝室", "宿舍 公寓"),
    ("宿舍", "公寓"),
    ("挂科", "不及格 补考 重修"),
    ("四六级", "四、六级 大学英语"),
    ("四级", "大学英语四、六级"),
    ("六级", "大学英语四、六级"),
    ("cet", "大学英语四、六级"),
    ("国励", "国家励志奖学金"),
    ("国奖", "国家奖学金"),
    ("勤工俭学", "勤工助学"),
    ("助管", "勤工助学 研究生助管"),
    ("医保", "医疗保险 参保"),
    ("报销", "报销比例 医疗保险"),
    ("看病", "校医院 门诊"),
    ("心理", "心理咨询"),
    ("体测", "体质健康"),
    ("毕业证", "学历证书 学位证书"),
    ("没电", "购电 欠费断电"),
    ("电费", "购电 欠费断电"),
    ("断电", "购电"),
    ("报到", "报到时间 新生"),
    ("火车北站", "公交 地铁 路线"),
    ("东客站", "公交 地铁 路线"),
    ("机场", "公交 地铁 路线"),
    ("户口", "户口迁移证 户籍"),
    ("团员", "团组织关系 团员档案"),
    ("档案", "档案 寄送 地址"),
    ("军训服", "军训服装费"),
    ("知网", "数据库 校外 WebVPN"),
    ("在家", "校外"),
    ("当兵", "服兵役"),
    ("退役", "服兵役 退役士兵"),
    ("贫困", "家庭经济困难"),
    ("困难认定", "家庭经济困难学生认定"),
    ("贷款", "助学贷款"),
    ("考研", "继续升学"),
    ("缓交", "学费缓交"),
    ("几台", "设备数量"),
    ("outlook", "客户端 POP3"),
    ("收信", "客户端 POP3"),
    ("关门", "开馆时间"),
    ("几点开", "开放时间"),
    ("续借", "续借 到期"),
)
TITLE_WEIGHT = 3.4
K1 = 1.2
B = 0.75


def terms(text: str) -> Counter[str]:
    text = text.casefold()
    result: Counter[str] = Counter(re.findall(r"[a-z0-9]+", text))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for width in (2, 3):
            result.update(run[i : i + width] for i in range(len(run) - width + 1))
    return result


def expand(query: str) -> str:
    folded = query.casefold()
    extra = [official for colloquial, official in SYNONYMS if colloquial in folded]
    return query if not extra else query + " " + " ".join(extra)


def query_terms(query: str) -> Counter[str]:
    tokens = terms(expand(query))
    for generic in GENERIC:
        for token in terms(generic):
            tokens.pop(token, None)
    return tokens


def eligible(chunk: RagChunk, source: RagSource, filters: RetrievalFilters) -> bool:
    if not chunk.enabled:
        return False
    expired = bool(chunk.valid_until and chunk.valid_until < filters.today)
    # A reviewed chunk flagged `stale` (factual content whose source is only marked historical
    # because its notice date passed) stays a candidate and is down-weighted at ranking time
    # instead of being dropped. Historical/deprecated chunks, superseded sources and chunks past
    # `valid_until` remain hard-filtered.
    stale_fact = chunk.stale and chunk.kind not in {"historical", "deprecated"}
    historical = (
        chunk.kind in {"historical", "deprecated"}
        or source.temporal_status == "superseded"
        or (source.temporal_status == "historical" and not stale_fact)
        or expired
    )
    if historical and not filters.historical:
        return False
    if chunk.valid_from and chunk.valid_from > filters.today:
        return False
    if filters.current_only and (historical or source.temporal_status != "current"):
        return False
    if filters.audience != "all" and "all" not in chunk.audiences:
        if filters.audience not in chunk.audiences and "unknown" not in chunk.audiences:
            return False
    campuses = {campus_value(c) for c in chunk.campuses}
    if filters.campus not in {"all", "unknown"} and not campuses & {
        campus_value(filters.campus), "all", "unknown"
    }:
        return False
    if filters.academic_year and chunk.academic_year not in (None, filters.academic_year):
        return False
    return True


def eligible_chunks(
    snapshot: KnowledgeSnapshot, sources: dict[str, RagSource], filters: RetrievalFilters
) -> list[RagChunk]:
    # Public teacher records have their own structured tool. Exclude before either
    # channel's top-k, while keeping them in the version-bound, complete vector index.
    return [c for c in snapshot.chunks
            if c.topic_id != "teacher_lookup" and eligible(c, sources[c.source_id], filters)]


class BM25Retriever:
    """Okapi BM25 with a title-weighted term frequency (BM25F-style single field)."""

    def __init__(self, snapshot: KnowledgeSnapshot) -> None:
        self.snapshot = snapshot
        self.sources = {s.source_id: s for s in snapshot.sources}
        self.fields = {
            c.chunk_id: (terms(c.title + " " + c.aliases), terms(c.text)) for c in snapshot.chunks
        }
        self.df: Counter[str] = Counter()
        self.lengths: dict[str, float] = {}
        for chunk_id, (title, body) in self.fields.items():
            self.df.update(title.keys() | body.keys())
            self.lengths[chunk_id] = TITLE_WEIGHT * sum(title.values()) + sum(body.values())
        self.avg_length = (sum(self.lengths.values()) / len(self.lengths)) if self.lengths else 1.0

    def idf(self, term: str) -> float:
        n = len(self.fields)
        return math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))

    def score(self, chunk_id: str, tokens: Counter[str]) -> float:
        title, body = self.fields[chunk_id]
        norm = K1 * (1 - B + B * self.lengths[chunk_id] / (self.avg_length or 1.0))
        total = 0.0
        for term, qf in tokens.items():
            tf = TITLE_WEIGHT * title[term] + body[term]
            if tf:
                total += self.idf(term) * min(qf, 2) * tf * (K1 + 1) / (tf + norm)
        return total

    def search(
        self, query: str, filters: RetrievalFilters, top_k: int = 12
    ) -> tuple[RetrievalHit, ...]:
        if not 1 <= top_k <= 100:
            raise ValueError("Invalid candidate limit")
        tokens = query_terms(query)
        found: list[RetrievalHit] = []
        for chunk in eligible_chunks(self.snapshot, self.sources, filters):
            score = self.score(chunk.chunk_id, tokens)
            # Require useful overlap; a single generic character never triggers retrieval.
            if score > 0.5:
                found.append(
                    RetrievalHit(
                        knowledge_version=self.snapshot.version,
                        chunk=chunk,
                        source=self.sources[chunk.source_id],
                        score=score,
                    )
                )
        return tuple(sorted(found, key=lambda h: (-h.score, h.chunk.chunk_id))[:top_k])
