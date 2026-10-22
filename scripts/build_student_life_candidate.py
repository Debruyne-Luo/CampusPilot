"""Correct and archive DeepSeek's unpublished increment; never change a release pointer.

Input is a local CampusPilot checkout containing the 2026-10-20 pending package and
public collection files. Existing historical source aliases are preserved in the base.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from campuspilot.knowledge_release import read_candidate, write_candidate
from campuspilot.rag import KnowledgeSnapshot, RagChunk, RagSource, canonical, digest, make_snapshot

ROOT = Path(__file__).resolve().parents[1]
NAME = 'student-life-integrated-20261021-v2'
RAW_PREFIXES = ['21-', '24-', '25-', '33-', '35-', '41-', '51-', '65-', '82-', '83-']


def build(source_root: Path, output_root: Path = ROOT) -> dict[str, Any]:
    source_package = source_root / 'data/cdut/rag/packages/pending-20261020'
    collected = source_root / 'output/kb-expansion-20261020/raw'
    package = output_root / 'data/cdut/rag/packages' / NAME
    candidate = output_root / 'data/cdut/rag/candidates' / NAME
    rag_root = output_root / 'data/cdut/rag'
    pointer = json.loads((rag_root / 'current.json').read_bytes())
    version = pointer.get('version', '')
    if pointer.get('kind', 'published') != 'published' or not re.fullmatch(r'kb-[a-f0-9]{16}',
                                                                       version):
        raise ValueError('Explicit published base required')
    base_root = rag_root / 'versions' / version
    if not base_root.resolve().is_relative_to(rag_root.resolve()):
        raise ValueError('Unsafe base directory')
    if (digest((base_root / 'snapshot.json').read_bytes()) != pointer['sha256']
            or digest((base_root / 'manifest.json').read_bytes()) != pointer['manifest_sha256']):
        raise ValueError('Base knowledge pointer checksum mismatch')
    base = read_candidate(base_root, check_index=False)
    if base.pending or base.version != version:
        raise ValueError('Base knowledge must already be adopted')
    base_manifest = json.loads((base_root / 'manifest.json').read_bytes())
    inherited_raw = {name.removeprefix('raw/'): (base_root / name).read_bytes()
                     for name in base_manifest['files_sha256'] if name.startswith('raw/')}
    sources = json.loads((source_package / 'sources.json').read_bytes())
    chunks = [json.loads(line) for line in (source_package / 'chunks.jsonl').read_text(
        encoding='utf-8').splitlines() if line.strip()]
    files = [next(collected.glob(prefix + '*')) for prefix in RAW_PREFIXES]
    files.extend(collected / n for n in ('card2024.pdf', 'card2024.txt'))
    raw = {'raw/' + p.name: p.read_bytes() for p in files}
    url_to_id = {s.url: s.source_id for s in base.sources}
    remap = {s['source_id']: url_to_id.get(s['url'], s['source_id']) for s in sources}
    for source in sources:
        source['source_id'] = remap[source['source_id']]
        source['content_scope'] = 'curated_paraphrase_with_archived_provider_extract'
        if source['source_id'].endswith('scholarship-mee-2026'):
            source['temporal_status'] = 'unknown'
            source['notes'] += ' 评审公告的发布日期不代表当前仍可申请；适用学年分片标注。'
    fresh_source = next(s for s in base.sources if '/xscjwd.htm' in s.url)
    sources.append({**fresh_source.model_dump(mode='json'), 'verification_status': 'pending',
                    'reviewer': '', 'verified_at': None})
    by_id = {c['chunk_id']: c for c in chunks}
    for chunk in chunks:
        chunk['source_id'] = remap[chunk['source_id']]
        if ':expand-cet:' in chunk['chunk_id']:
            chunk.update(academic_year='2026-2027', valid_from='2026-09-10',
                         valid_until='2026-12-12')
        if ':expand-scholarship:' in chunk['chunk_id']:
            # This notice assesses two different academic years. A single global year
            # would wrongly exclude one award from retrieval; preserve both in the text.
            chunk['academic_year'] = None
            chunk['text'] = (
                '2026年机电工程学院评审：国家奖学金、国家励志奖学金参评2025—2026学年，'
                '国家助学金对应2026—2027学年。' + chunk['text']
            )
        if ':expand-card:' in chunk['chunk_id']:
            chunk['stale'] = True
    by_id['cdut:chunk:expand-scholarship:01']['text'] += (
        ' 同一学年国家奖学金与国家励志奖学金不能同时获得，符合困难认定条件者可与国家助学金兼得。'
    )
    by_id['cdut:chunk:expand-scholarship:02']['text'] += (
        ' 共同基本条件还包括具有中华人民共和国国籍、热爱祖国并拥护中国共产党的领导，'
        '遵守法律及校规，参评学年未受到纪律处分且不在处分期内，诚实守信、品德优良，努力学习、积极向上。'
        '国家奖学金另要求社会实践、创新能力、综合素质等方面特别突出，'
        '并满足学习年限、学习成绩、学籍状态等条件。国家励志奖学金的困难认定库对应2025—2026学年；'
        '国家助学金还要求学习态度端正、勤奋学习、积极上进。'
    )
    by_id['cdut:chunk:expand-card:02']['text'] += (
        ' 原文未列材料不表示无需身份证或其他材料，应按设备及学校官方说明准备。'
    )
    by_id['cdut:chunk:expand-lib:05']['stale'] = True
    by_id['cdut:chunk:expand-lib:05']['text'] += (
        ' 本FAQ未注明日期，学生上网账号写作一卡通号；网信中心2023年FAQ写作学生学号。'
        '两处账号表述不同，不据此确认当前登录凭据；请以学校当前登录页面为准。'
    )
    schedule = by_id['cdut:chunk:expand-schedule:01']
    schedule['text'] = schedule['text'].replace('；熄灯就寝22:30', '')
    schedule['text'] += ' 本片段仅说明教学作息，不能用于确认学生公寓门禁或实际熄灯安排。'
    schedule['aliases'] = '上课时间 下课时间 午休 课程表 教学时间表'
    repair = by_id['cdut:chunk:expand-repair:01']
    repair['title'] = '南苑北苑等家属区报修与市政电话'
    repair['aliases'] = '南苑家属区 北苑家属区 家属区报修 市政维修 校园110'
    repair['text'] += ' 该电话服务范围为家属区，学生公寓报修应使用楼寓服务中心渠道。'
    library = by_id['cdut:chunk:expand-lib:01']
    library['source_id'] = fresh_source.source_id
    library['locator'] = '新生常见问答/我能借几本书？借期多长？'
    scholarship = by_id['cdut:chunk:expand-scholarship:02']
    scholarship['text'] += (
        ' 国家励志奖学金还要求参评学年（2025—2026学年）无不及格科目；'
        '享受乡村振兴急需紧缺专业本科生定向培养等学费全免政策的特殊学生，不再获得国家励志奖学金，'
        '也不再同时获得国家助学金。全日制在校退役士兵学生资助标准为3700元/人·年，'
        '无需个人申请，不占用学院分配助学金名额；特别困难需申请4900元/人·年资助的，'
        '学院应提前与学校资助管理中心沟通。'
    )
    by_id['cdut:chunk:expand-scholarship:03']['text'] += (
        ' 上述个人在线申请不适用于原文明确无需个人申请的退役士兵学生。'
        '本文为2026年学院评审通知，所列公示安排不代表当前仍在申请或申诉期。'
    )
    index = []
    for source in sources:
        url = source['url']
        matches = [p for p in files if p.suffix == '.txt'
                   and url in p.read_text(encoding='utf-8')[:400]]
        if 'card-guide' in url or url.endswith('.pdf'):
            matches = [collected / 'card2024.pdf', collected / 'card2024.txt']
        if not matches:
            raise ValueError('Missing raw capture for ' + source['source_id'])
        for p in matches:
            index.append({'source_id': source['source_id'], 'url': url, 'file': 'raw/' + p.name,
                          'sha256': digest(p.read_bytes()),
                          'method': 'direct_download' if p.suffix == '.pdf'
                          else 'deepseek_archived_public_text_extract',
                          'collected_on': '2026-10-20'})
    raw['raw/evidence-index.json'] = canonical(index)
    raw['sources.json'] = canonical(sources)
    legacy = json.loads((source_root / 'data/cdut/knowledge.json').read_bytes())
    legacy = [r for r in legacy if r['collected_on'] == '2026-10-20']
    for record in legacy:
        if record['record_id'].endswith('academic-schedule'):
            record['summary'] = '教学作息与职工办公时间；页面无发布日期，不用于判断学生公寓熄灯。'
            record['details'] = [d.replace('；熄灯就寝22:30', '') for d in record['details']]
            record['keywords'] = [k for k in record['keywords'] if k != '熄灯']
        elif record['record_id'].endswith('repair-service'):
            record['title'] = '南苑北苑等家属区维修与市政服务电话'
            record['keywords'] = ['南苑家属区', '北苑家属区', '家属区报修', '市政维修']
            record['audience_text'] = '南苑、北苑等家属区；不作为学生公寓报修渠道'
        elif record['record_id'].endswith('library-borrowing-current'):
            record['details'][0] = '本科生40本，研究生、教职工50本，借期两个月，逾期前可续借。'
        elif record['record_id'].endswith('scholarship-mee-2026'):
            record['summary'] = (
                '2026年机电工程学院评审；国家奖学金、国家励志奖学金参评2025—2026学年，'
                '国家助学金对应2026—2027学年，不代表当前仍可申请。')
            record['details'][1] += (
                ' 同一学年国家奖学金与国家励志奖学金不能兼得，符合条件可与国家助学金兼得。')
            record['details'][2] = scholarship['text']
            record['details'][3] += (
                ' 退役士兵学生无需个人申请。所列日期为2026年评审安排，不代表当前仍可申请。')
    raw['knowledge-records.json'] = canonical(legacy)
    for c in chunks:
        c['text_sha256'] = digest(c['text'].encode())
    raw['chunks.jsonl'] = b'\n'.join(canonical(c) for c in chunks) + b'\n'
    raw['REVIEW.md'] = (
        '# 学生生活资料修正候选\n\npending；未生成新向量、未发布。\n\n'
        '保留原始采集日期、提取方式和原件哈希；文本提取不是学校原始HTTP响应。\n'
        '修正：奖助学金例外、家属区与宿舍范围、教学作息与门禁、时效、图书馆续借来源。\n'
        '图书馆/校园卡复用已有来源；历史基线重复别名保留，本轮不再新增重复来源。\n'
        '2026年度评审学年限制不表示当前仍可申请；未写明的截止日期不推测。\n'
        '奖学金/励志奖学金参评2025—2026学年，助学金对应2026—2027；不以单一学年概括整页。\n'
        '图书馆FAQ与网信中心FAQ的学生上网账号表述不同，保留原文并标记待复核。\n'
        '熄灯冲突没有宣布任何原文失效；教学表中的22:30不用于公寓回答。\n'
        '新生资料采集使用单独的freshman-candidate-20261021包。\n'
    ).encode()
    merged_sources = {s.source_id: s for s in base.sources}
    for s in sources:
        if s['source_id'] not in merged_sources:
            merged_sources[s['source_id']] = RagSource.model_validate_json(canonical({
                k: v for k, v in s.items() if k in RagSource.model_fields
            }))
    merged_chunks = {c.chunk_id: c for c in base.chunks}
    merged_chunks.update(
        (c['chunk_id'], RagChunk.model_validate_json(canonical(c))) for c in chunks
    )
    package_hash = digest(canonical({n: digest(b) for n, b in sorted(raw.items())}))
    snapshot = make_snapshot(tuple(merged_sources.values()), tuple(merged_chunks.values()),
                             package_hash)
    if candidate.exists():
        previous = KnowledgeSnapshot.model_validate_json((candidate / 'snapshot.json').read_bytes())
        if previous.version != snapshot.version:
            raise ValueError('Existing candidate differs; choose a new versioned name')
    for name, content in raw.items():
        target = package / name
        if target.exists() and target.read_bytes() != content:
            raise ValueError('Existing package differs; choose a new versioned name')
    package.mkdir(parents=True, exist_ok=True)
    for name, content in raw.items():
        p = package / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    if not candidate.exists():
        write_candidate(candidate, snapshot, {
            **inherited_raw, **{'student-life/' + n: b for n, b in raw.items()},
        })
    return {'version': snapshot.version, 'sources': len(snapshot.sources),
            'chunks': len(snapshot.chunks), 'pending': snapshot.pending,
            'raw_files': len(index), 'candidate': str(candidate), 'base_version': base.version,
            'inherited_raw_files': len(inherited_raw)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source_root), ensure_ascii=False, indent=2))
