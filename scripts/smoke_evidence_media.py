"""Bounded real-provider checks using public queries and an unmistakably synthetic image.

Keys are loaded from explicit files outside the repository; output contains no credentials,
image data or user conversations. This script never deploys or modifies provider accounts.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import subprocess
import time
from decimal import Decimal
from pathlib import Path

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import OnlineBudget, TokenPrice
from campuspilot.jev_shadow import JevShadowClient
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ChatCompletionsModel, Completion, ImageInput, user_content
from campuspilot.rag import SnapshotStore, canonical
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import (
    DeepSeekSearchProvider,
    TurnEvidenceContext,
    WebEvidenceService,
)
from PIL import Image, ImageDraw


def key_file(path: Path) -> str:
    if not path.is_absolute() or path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("Use a credential file outside the checkout")
    value = path.read_text(encoding="utf-8-sig").strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError("Invalid credential file")
    return value


class BudgetedSmokeModel:
    """Charge image/agent smoke calls to the same conservative test ledger."""

    def __init__(self, model: ChatCompletionsModel, budget: OnlineBudget) -> None:
        self.model = model
        self.budget = budget
        self.price = TokenPrice(Decimal("0.3"), Decimal("1.2"))

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> Completion:
        # This fixture is only 640x300. A 32k input reservation also covers visual tokens.
        reservation = self.budget.reserve(
            self.price.cost(max(len(canonical(messages)) + 1024, 32_000), max_tokens or 500),
            "smoke:vision",
        )
        try:
            reply = await self.model.complete(
                messages, tools=tools, json_mode=json_mode, max_tokens=max_tokens
            )
        except BaseException:
            self.budget.settle(reservation, None)
            raise
        self.budget.settle(
            reservation, self.price.cost(reply.input_tokens, reply.output_tokens)
        )
        return reply


async def run(args: argparse.Namespace) -> None:
    credential = key_file(args.model_key) if args.model_key else vps_key(args.vps)
    model = ChatCompletionsModel(
        "https://api.deepseek.com", "deepseek-flash", credential, max_output_tokens=500
    )
    budget = OnlineBudget(args.budget_dir, Decimal("1"), 20, max_search_flows=3)
    budgeted_model = BudgetedSmokeModel(model, budget)
    results: dict[str, object] = {}
    picture = Image.new("RGB", (640, 300), "white")
    ImageDraw.Draw(picture).text(
        (20, 90), "SYNTHETIC TEST ONLY: BLUE-731", fill="black", font_size=28
    )
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    image = ImageInput("synthetic-smoke", "image/png", buffer.getvalue())
    started = time.monotonic()
    try:
        reply = await budgeted_model.complete(
            [
                {
                    "role": "user",
                    "content": user_content(
                        'Read the marker after TEST ONLY. Reply JSON {"marker":"..."}.', (image,)
                    ),
                }
            ],
            json_mode=True,
            max_tokens=100,
        )
        content = json.loads(reply.content or "{}")
        results["vision"] = {
            "pass": content.get("marker") == "BLUE-731",
            "latency_ms": round((time.monotonic() - started) * 1000),
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
        }
    except Exception as exc:
        results["vision"] = {
            "pass": False,
            "error_type": type(exc).__name__,
            "code": getattr(exc, "code", ""),
        }
    search = WebEvidenceService(
        budget,
        DeepSeekSearchProvider(
            api_key=model.api_key,
            price=TokenPrice(Decimal("0.3"), Decimal("1.2")),
            search_cost_per_use=Decimal("0"),
        ),
    )
    if args.agent:
        data_dir = Path(__file__).resolve().parents[1] / "data" / "cdut"
        repository = DirectoryRepository.load(data_dir)
        runner = AgentRunner(
            agent_registry(
                repository, KnowledgeStore.load(data_dir / "knowledge.json"),
                SnapshotStore(data_dir / "rag"),
            ),
            repository,
            budgeted_model,
        )
        started = time.monotonic()
        context = ConversationContext()
        result = await runner.run(
            "请读取这张图片中 TEST ONLY 后的标记。", context, images=(image,)
        )
        answer = result.get("answer", "")
        results["image_agent"] = {
            "pass": result.get("answer_mode") == "agent_image"
            and result.get("result_status") == "success"
            and isinstance(answer, str) and "BLUE-731" in answer,
            "latency_ms": round((time.monotonic() - started) * 1000),
            "status": result.get("result_status"),
            "degraded_reason": result.get("degraded_reason"),
            "official_citations": len(result.get("citations", [])),
        }
        if args.followup:
            started = time.monotonic()
            result = await runner.run("这张图标记最后的数字是什么？", context, images=(image,))
            answer = result.get("answer", "")
            results["image_followup"] = {
                "pass": result.get("answer_mode") == "agent_image"
                and result.get("result_status") == "success"
                and isinstance(answer, str) and "731" in answer,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "status": result.get("result_status"),
            }
            result = await runner.run("我想去E2A403", context, images=(image,))
            cards = result.get("places", [])
            results["unrelated_place"] = {
                "pass": isinstance(cards, list) and len(cards) == 1
                and isinstance(cards[0], dict)
                and cards[0].get("place_id") == "cdut:place:east-e2a"
                and result.get("answer_mode") != "agent_image",
            }
    if args.skip_search:
        results["search"] = {"status": "not_run"}
    elif args.diagnose_pages:
        budget.reserve_search_flow()
        deadline = time.monotonic() + 10
        native = await search.primary.search("成都理工大学 商学院 官网", budget, deadline)
        pages: list[dict[str, object]] = []
        for source in native.sources[:3]:
            item: dict[str, object] = {"url": source.url}
            try:
                page = await search.reader.read(source, deadline)
                item["text_length"] = len(page.text)
            except Exception as exc:
                item["error"] = type(exc).__name__
                item["reason"] = str(exc)[:200]
            pages.append(item)
        results["search"] = {"status": native.status, "reason": native.reason, "pages": pages}
    else:
        found = await search.search("成都理工大学 商学院 官网")
        results["search"] = {
            "status": found.status,
            "reason": found.reason,
            "attempts": found.attempts,
            "page_reads": found.page_reads,
            "latency_ms": round(found.latency_ms),
            "sources": [
                {"title": p.title, "url": p.url, "authority": p.source_authority}
                for p in found.pages
            ],
        }
    if args.jev_key:
        client = JevShadowClient(key_file(args.jev_key), TokenPrice(Decimal("0.042"), Decimal("0")))
        judged = await client.evaluate_evidence(
            "商学院的位置需要地图数据吗？",
            (),
            public_fixture=True,
            budget=budget,
            evidence_context=TurnEvidenceContext(task="校园找路", search_completed=False),
        )
        results["jev"] = {
            "status": judged.status,
            "reason": judged.reason,
            "search_needed": judged.search_needed,
            "latency_ms": round(judged.latency_ms),
        }
    report = budget.report()
    results["budget"] = {key: report.get(key) for key in ("charged_usd", "calls", "search_flows")}
    print(json.dumps(results, ensure_ascii=False, indent=2))


def vps_key(host: str) -> str:
    # SSH output is captured inside this process. Never echo configuration or the key.
    code = (
        "from pathlib import Path\n"
        "for line in Path('/etc/campuspilot/campuspilot.env').read_text().splitlines():\n"
        " k,sep,v=line.partition('=')\n"
        " if sep and k=='CAMPUSPILOT_MODEL_API_KEY': print(v.strip())\n"
    )
    result = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, "python3 -"],
        input=code,
        text=True,
        capture_output=True,
        check=False,
    )
    value = result.stdout.strip()
    if result.returncode or not value or any(c.isspace() for c in value):
        raise ValueError("Remote model credential unavailable")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    credential_options = parser.add_mutually_exclusive_group(required=True)
    credential_options.add_argument("--model-key", type=Path)
    credential_options.add_argument(
        "--vps", help="Read existing key over SSH, without changing the server"
    )
    parser.add_argument("--jev-key", type=Path)
    parser.add_argument("--budget-dir", type=Path, required=True)
    parser.add_argument("--diagnose-pages", action="store_true")
    parser.add_argument(
        "--skip-search", action="store_true", help="Keep existing flow limits intact"
    )
    parser.add_argument(
        "--agent", action="store_true", help="Also verify the real image Agent chain"
    )
    parser.add_argument(
        "--followup", action="store_true", help="Also verify image follow-up and task change"
    )
    asyncio.run(run(parser.parse_args()))
