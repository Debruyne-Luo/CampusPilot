# Targeted official-source review, 2026-10-17

This package is a candidate input, not a published knowledge release. It reuses
the immutable `kb-229ee34eba99ef34` baseline and does not change its files or the
active pointer. `official_document` denotes source adoption, not field verification.

Three documents have checked clauses:

- `portal-1266`: the saved original flow image now has a manually checked
  transcription bound to both the image and body hashes. The student condition
  that the household registration must be held by the university is retained.
- `portal-1042`: both computer and official enterprise WeChat branches in the
  original flow image have checked transcriptions. Neither appointment success
  nor a campus designation is inferred.
- `xjgl2019`: one direct public HTTP read saved the full 18-page PDF, SHA-256
  `d74ac91749e5d4eaac39033388e5463fadb7bd1abb93badaec95722d2a727b21`.
  Local pypdf extraction covers all 18 pages. Rendered pages 2 and 18 were visually
  checked. Only legacy clause `cdut:chunk:xjgl2019:16` (articles 56–58) is upserted.
  It retains the old source ID and unknown temporal status, with an explicit
  warning that this 2019 document was not established to be the latest policy.

Two Firecrawl WeChat captures remain `complete: false`: the original 20 and 12
article images were not retrieved or OCR checked in this review. Their provider
responses and plain text are retained without inheriting earlier OCR assertions.
They deliberately fail the existing `incomplete_document` adoption boundary and
leave the last successful source content untouched. No new Firecrawl calls were made.

The original portal capture date remains 2026-10-14; transcription review is dated
2026-10-17. Publication dates and campuses remain unknown. The Firecrawl display
times are preserved with their America/New_York metadata; they are not silently
converted into publication-date claims.

From the repository root, reproduce the local package and contract checks:

```powershell
.venv/Scripts/python.exe scripts/review_collected_sources.py --verify
.venv/Scripts/python.exe -m ruff check scripts/review_collected_sources.py
```

The machine-readable review and verification results are written to
`output/knowledge-rebuild-20261017/source-review.json`. The script makes no network
or model calls. It checks successful adoption, incomplete-document preservation,
stable PDF scope, unknown temporal status, idempotence, image/body hash corruption
rejection and preservation of last successful clauses. This is targeted review of
five documents; it does not establish full-corpus coverage.
