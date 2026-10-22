"""Source-backed regression checks for the corrected, unpublished life-guide candidate."""

import importlib
import json
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

import pytest
from campuspilot.knowledge_release import read_candidate
from campuspilot.rag import RetrievalFilters, digest
from campuspilot.retrieval.bm25 import BM25Retriever, eligible

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'data/cdut/rag/packages/student-life-integrated-20261021-v2'
CANDIDATE = ROOT / 'data/cdut/rag/candidates/student-life-integrated-20261021-v2'
# This candidate predates the final freshman release; verify its original immutable base.
CANDIDATE_BASE = ROOT / 'data/cdut/rag/versions/kb-229ee34eba99ef34'


def active_base() -> Path:
    pointer = json.loads((ROOT / 'data/cdut/rag/current.json').read_bytes())
    return ROOT / 'data/cdut/rag/versions' / str(pointer['version'])


def test_corrected_scope_and_important_exceptions() -> None:
    snapshot = read_candidate(CANDIDATE)
    assert snapshot.pending
    chunks = {c.chunk_id: c for c in snapshot.chunks}
    repair = chunks['cdut:chunk:expand-repair:01']
    assert '宿舍' not in repair.aliases and '家属区' in repair.text
    scholarship = '\n'.join(c.text for c in snapshot.chunks if ':expand-scholarship:' in c.chunk_id)
    assert '无需个人申请' in scholarship
    assert '国家励志奖学金' in scholarship and '无不及格' in scholarship
    assert '纪律处分' in scholarship and '2025—2026学年' in scholarship
    assert '不能同时获得' in scholarship and '困难认定库对应2025—2026学年' in scholarship
    assert chunks['cdut:chunk:expand-scholarship:02'].academic_year is None
    assert chunks['cdut:chunk:expand-lib:05'].stale
    assert '22:30' not in chunks['cdut:chunk:expand-schedule:01'].text
    for c in snapshot.chunks:
        if ':expand-cet:' in c.chunk_id or ':expand-scholarship:' in c.chunk_id:
            source = next(s for s in snapshot.sources if s.source_id == c.source_id)
            assert not eligible(c, source, RetrievalFilters(
                today=date(2027, 10, 21), academic_year='2027-2028', current_only=True,
            ))


def test_evidence_files_are_bound_and_source_urls_are_not_duplicated() -> None:
    snapshot = read_candidate(CANDIDATE)
    base = json.loads((CANDIDATE_BASE / 'snapshot.json').read_bytes())
    before = Counter(s['url'] for s in base['sources'])
    after = Counter(s.url for s in snapshot.sources)
    assert all(count <= max(1, before[url]) for url, count in after.items())
    evidence = json.loads((PACKAGE / 'raw/evidence-index.json').read_bytes())
    assert len(evidence) >= 11
    for entry in evidence:
        assert digest((PACKAGE / entry['file']).read_bytes()) == entry['sha256']
    lib = next(c for c in snapshot.chunks if c.chunk_id == 'cdut:chunk:expand-lib:01')
    source = next(s for s in snapshot.sources if s.source_id == lib.source_id)
    assert '/xscjwd.htm' in source.url


def test_new_repair_and_schedule_do_not_displace_dormitory_evidence() -> None:
    retriever = BM25Retriever(read_candidate(CANDIDATE))
    filters = RetrievalFilters(today=date(2026, 10, 21))
    for question, unwanted in [
        ('宿舍水管漏水怎么报修', 'cdut:chunk:expand-repair:01'),
        ('宿舍几点熄灯', 'cdut:chunk:expand-schedule:01'),
    ]:
        assert retriever.search(question, filters, 1)[0].chunk.chunk_id != unwanted


def test_candidate_retains_frozen_baseline_chunks_and_bound_entry_evidence() -> None:
    from campuspilot.service_links import load_link_catalog

    snapshot = read_candidate(CANDIDATE)
    base = read_candidate(CANDIDATE_BASE, check_index=False)
    chunks = {c.chunk_id: c for c in snapshot.chunks}
    sources = {s.source_id: s for s in snapshot.sources}
    assert all(chunks.get(c.chunk_id) == c for c in base.chunks)
    assert all(sources.get(s.source_id) == s for s in base.sources)
    prior = json.loads((CANDIDATE_BASE / 'manifest.json').read_bytes())
    current = json.loads((CANDIDATE / 'manifest.json').read_bytes())
    for name, expected in prior['files_sha256'].items():
        if name.startswith('raw/'):
            assert current['files_sha256'][name] == expected
    base_links = load_link_catalog(CANDIDATE_BASE, base, prior)
    integrated_links = load_link_catalog(CANDIDATE, snapshot, current)
    assert base_links and all(
        integrated_links.get(key) == value
        for key, value in base_links.items()
    )


def test_rebuild_cannot_overwrite_a_package_before_rejecting_a_changed_candidate(
    tmp_path: Path,
) -> None:
    builder = importlib.import_module('scripts.build_student_life_candidate')

    source = tmp_path / 'source'
    source_package = source / 'data/cdut/rag/packages/pending-20261020'
    source_package.mkdir(parents=True)
    for name in ['sources.json', 'chunks.jsonl']:
        shutil.copyfile(PACKAGE / name, source_package / name)
    shutil.copytree(PACKAGE / 'raw', source / 'output/kb-expansion-20261020/raw')
    shutil.copyfile(PACKAGE / 'knowledge-records.json', source / 'data/cdut/knowledge.json')
    output = tmp_path / 'output'
    rag = output / 'data/cdut/rag'
    shutil.copytree(active_base(), rag / 'versions' / active_base().name)
    shutil.copyfile(ROOT / 'data/cdut/rag/current.json', rag / 'current.json')
    target = rag / 'packages' / builder.NAME
    target.mkdir(parents=True)
    sentinel = target / 'REVIEW.md'
    sentinel.write_text('SYNTHETIC previous review must survive', encoding='utf-8')
    candidate = rag / 'candidates' / builder.NAME
    candidate.mkdir(parents=True)
    shutil.copyfile(CANDIDATE / 'snapshot.json', candidate / 'snapshot.json')
    with pytest.raises(ValueError, match='Existing candidate differs'):
        builder.build(source, output)
    assert sentinel.read_text(encoding='utf-8') == 'SYNTHETIC previous review must survive'
