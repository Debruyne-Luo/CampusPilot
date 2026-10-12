"""Adopt prepared official-source records; validate and atomically update a local snapshot.

No network crawling, credentials or user approval prompts. Input may contain an official
site record or an attributed official WeChat article transcribed from a readable source.
"""

import argparse
import hashlib
import os
import tempfile
from pathlib import Path

from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeRecord, KnowledgeStore, dump_records
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[1]


def merge_snapshot(source: Path, target: Path, data_dir: Path, *, check_only: bool) -> int:
    if not source.is_file() or source.stat().st_size > 4_000_000:
        raise ValueError("Expected a bounded input file")
    incoming = TypeAdapter(tuple[KnowledgeRecord, ...]).validate_json(source.read_bytes())
    if not incoming:
        raise ValueError("Input must contain at least one official-source record")
    if len({r.record_id for r in incoming}) != len(incoming):
        raise ValueError("Duplicate input record")
    existing = KnowledgeStore.load(target)
    records = {r.record_id: r for r in existing.records}
    for record in incoming:
        previous = records.get(record.record_id)
        if previous and record.collected_on < previous.collected_on:
            raise ValueError("Refusing an older collection snapshot")
        if previous and record.source_url != previous.source_url:
            raise ValueError("Use a new record ID and supersedes when replacing a source")
        records[record.record_id] = record
    merged = KnowledgeStore(tuple(records[k] for k in sorted(records)))
    repository = DirectoryRepository.load(data_dir)
    if any(repository.find_place(i) is None for r in merged.records for i in r.place_ids):
        raise ValueError("Unknown campus place reference")
    output = dump_records(merged.records).encode("utf-8")
    if check_only:
        return len(incoming)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        old = target.read_bytes()
        if old == output:
            return len(incoming)
        backup = target.parent / ".knowledge-history" / (hashlib.sha256(old).hexdigest() + ".json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.write_bytes(old)
    fd, temporary = tempfile.mkstemp(prefix=".knowledge-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(incoming)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--target", type=Path, default=ROOT / "data/cdut/knowledge.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data/cdut")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    count = merge_snapshot(args.input, args.target, args.data_dir, check_only=args.check_only)
    print(f"Official-source records {'validated' if args.check_only else 'adopted'}: {count}")


if __name__ == "__main__":
    main()
