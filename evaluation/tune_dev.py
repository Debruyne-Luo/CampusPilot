"""Grid search of hybrid parameters on the DEV set only (never the test set)."""

import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eval_colloquial as ev
from campuspilot.config import Settings
from campuspilot.rag import KnowledgeSnapshot
from campuspilot.retrieval import bm25
from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex

DEV = ev.ROOT / "evaluation/dev-colloquial-20261011/cases.jsonl"
s = Settings.from_env()
snap = KnowledgeSnapshot.model_validate_json((ev.DEFAULT_SNAPSHOT / "snapshot.json").read_bytes())
index = VectorIndex.load(ev.DEFAULT_SNAPSHOT / INDEX_NAME, snap, s.embedding_model)
cases = ev.load_cases(DEV)
vec = ev.embed_all([c["question"] for c in cases], s)
out = {}
syn = bm25.SYNONYMS
bm25.SYNONYMS = ()
out["stale_policy_only"] = ev.evaluate(cases, snap, index, vec, ev.MODES)[0]
bm25.SYNONYMS = syn
out["stale_policy+synonyms"] = ev.evaluate(cases, snap, index, vec, ev.MODES)[0]
grid = []
for k, wv, sw in itertools.product(
    (10, 20, 40, 60, 100), (0.5, 0.75, 1.0, 1.25), (0.5, 0.7, 0.85, 1.0)
):
    r = ev.evaluate(
        cases, snap, index, vec, ["hybrid"], {"rrf_k": k, "weights": (1.0, wv), "stale_weight": sw}
    )[0]["hybrid"]
    grid.append(({"rrf_k": k, "w_vec": wv, "stale_weight": sw}, r))
grid.sort(key=lambda x: (-x[1]["mrr@20"], -x[1]["recall@3"]))
out["grid_top10"] = grid[:10]
sims = []
for ms in (0.35, 0.40, 0.45, 0.50, 0.55):
    best = grid[0][0]
    r = ev.evaluate(
        cases,
        snap,
        index,
        vec,
        ["vector", "hybrid"],
        {
            "rrf_k": best["rrf_k"],
            "weights": (1.0, best["w_vec"]),
            "stale_weight": best["stale_weight"],
            "min_similarity": ms,
        },
    )[0]
    sims.append((ms, r))
out["min_similarity"] = sims
Path(ev.ROOT / "evaluation/reports/tune-dev.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1)
)
for k, v in out.items():
    print("##", k)
    if isinstance(v, dict):
        for m, r in v.items():
            print(" ", m, r)
    else:
        for x in v:
            print(" ", x)
