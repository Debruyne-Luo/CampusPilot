"""Offline complete API timing, cold and warm; cannot satisfy production latency gates."""

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import cast

import httpx
from campuspilot.chat_runtime import Mode
from campuspilot.knowledge_release import atomic_write
from campuspilot.migration_eval import percentile95
from campuspilot.rag import canonical
from campuspilot.web import create_web_app

ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    "campus_control": "香樟食堂在哪？",
    "simple": "王洪辉老师办公室在哪？",
    "rag": "学生邮箱怎样激活？",
}
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


async def measure(stage: Mode, samples: int) -> dict[str, object]:
    paths: dict[str, object] = {}
    for path, question in QUERIES.items():
        temperatures: dict[str, object] = {}
        for temperature in ("warm", "cold"):
            results: list[dict[str, object]] = []

            async def worker(
                count: int, question: str, temperature: str, results: list[dict[str, object]]
            ) -> None:
                warm_app = create_web_app(data_dir=ROOT / "data/cdut", runtime_mode=stage)
                warm = httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=warm_app),
                    base_url="http://testserver",
                    headers=HEADERS,
                )
                try:
                    if temperature == "warm":
                        await warm.post("/api/session")
                        await warm.post("/api/chat", json={"message": question})
                    for i in range(count):
                        started = time.perf_counter()
                        client = warm
                        if temperature == "cold":
                            app = create_web_app(data_dir=ROOT / "data/cdut", runtime_mode=stage)
                            client = httpx.AsyncClient(
                                transport=httpx.ASGITransport(app=app),
                                base_url="http://testserver",
                                headers=HEADERS,
                            )
                            await client.post("/api/session")
                        elif i % 25 == 0:
                            await client.post("/api/session/reset")
                        response = await client.post("/api/chat", json={"message": question})
                        body = response.json()
                        elapsed = (time.perf_counter() - started) * 1000
                        results.append(
                            {
                                "elapsed_ms": elapsed,
                                "valid": response.status_code == 200
                                and body.get("result_status") == "success",
                                "status": body.get("result_status"),
                                "route": body.get("answer_mode"),
                                "request_id": body.get("request_id"),
                            }
                        )
                        if temperature == "cold":
                            await client.aclose()
                finally:
                    await warm.aclose()

            await asyncio.gather(
                worker(samples // 2, question, temperature, results),
                worker(samples - samples // 2, question, temperature, results),
            )
            valid = [float(str(r["elapsed_ms"])) for r in results if r["valid"]]
            temperatures[temperature] = {
                "valid_samples": len(valid),
                "total_samples": len(results),
                "p95_ms": percentile95(valid),
                "all_results_p95_ms": percentile95([float(str(r["elapsed_ms"])) for r in results]),
                "samples": results,
            }
        paths[path] = temperatures
    return {
        "schema_version": 1,
        "stage": stage,
        "scope": "offline_complete_API",
        "concurrency": 2,
        "same_deployment_environment": False,
        "cold_start_verified": False,
        "cache": "no_response_cache; cold rebuilds application and retriever in-process",
        "model": "not_configured",
        "external_inference_calls": 0,
        "paths": paths,
        "release_gate": "NOT_EVALUATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("phase1", "phase2"), required=True)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 100 or args.samples > 1000 or args.output.exists():
        parser.exit(2, "Use 100–1,000 samples and a new report path.\n")
    result = asyncio.run(measure(cast(Mode, args.stage), args.samples))
    atomic_write(args.output, canonical(result))
    print(
        json.dumps(
            {
                "scope": result["scope"],
                "external_inference_calls": 0,
                "release_gate": "NOT_EVALUATED",
            }
        )
    )


if __name__ == "__main__":
    main()
