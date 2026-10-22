"""Process entry points: VPS app factory and local CLI, both driven by Settings."""

import argparse
import asyncio
import getpass
import sys
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI

from campuspilot.app.factory import create_web_app
from campuspilot.config import Settings
from campuspilot.dify import DifyClient
from campuspilot.llm.chat_model import ChatCompletionsModel
from campuspilot.llm.embedding import CloudflareEmbedder


def model_from_env() -> ChatCompletionsModel | None:
    from campuspilot.migration_config import generation_model

    return generation_model()


def reader_from_env() -> ChatCompletionsModel | None:
    from campuspilot.migration_config import reader_model

    return reader_model()


def direct_rules(settings: Settings) -> frozenset[str]:
    if not settings.direct_rules_report:
        return frozenset()
    from campuspilot.release_gate import approved_rules

    return approved_rules(Path(settings.direct_rules_report), Path(__file__).resolve().parents[4])


def build_app(settings: Settings) -> FastAPI:
    """The one assembly path shared by app_factory() and main()."""
    mode = settings.runtime_mode
    dify = (
        DifyClient(
            settings.dify_api_key,
            settings.dify_base_url,
            structured_answers=settings.dify_structured_answers,
        )
        if settings.dify_api_key and mode != "phase2"
        else None
    )
    return create_web_app(
        data_dir=settings.data_dir,
        dify=dify,
        api_token=settings.api_token,
        public_origin=settings.public_origin,
        amap_key=settings.amap_key,
        amap_security_code=settings.amap_security_code,
        amap_web_service_key=settings.amap_web_service_key,
        amap_discovery=settings.amap_discovery,
        images_enabled=settings.images_enabled,
        web_search=settings.web_search,
        web_search_provider=settings.web_search_provider,
        evidence_budget_dir=settings.evidence_budget_dir,
        evidence_daily_usd=settings.evidence_daily_usd,
        evidence_daily_flows=settings.evidence_daily_flows,
        search_input_price=settings.search_input_price,
        search_output_price=settings.search_output_price,
        tavily_api_key=settings.tavily_api_key,
        tavily_free_plan_confirmed=settings.tavily_free_plan_confirmed,
        daily_chat_limit=settings.daily_chat_limit,
        runtime_mode=mode,
        model=model_from_env() if mode != "legacy" else None,
        reader=reader_from_env() if mode != "legacy" else None,
        approved_direct_rules=direct_rules(settings),
        retrieval_mode=settings.retrieval_mode,
        embedder=embedder_from(settings) if mode == "phase2" else None,
        embedding_model=settings.embedding_model,
        agent_loop=settings.agent_loop,
        grounding=settings.grounding,
        jev=settings.jev,
        jev_routing=settings.jev_routing,
        harness_profile=settings.harness_profile,
        lab_records_dir=settings.lab_records_dir,
        jev_budget_dir=settings.jev_budget_dir,
        jev_daily_usd=settings.jev_daily_usd,
        jev_daily_calls=settings.jev_daily_calls,
        knowledge_bundle=settings.knowledge_bundle,
        asset_version=settings.asset_version,
    )


def embedder_from(settings: Settings) -> CloudflareEmbedder | None:
    if settings.retrieval_mode == "lexical" or not settings.embeddings_configured:
        return None
    return CloudflareEmbedder(
        settings.cf_account_id,
        settings.cf_api_token,
        model=settings.embedding_model,
        timeout=settings.embedding_timeout,
        retries=1,
    )


def app_factory() -> FastAPI:
    """Single-worker VPS entry point; credentials remain in the environment."""
    return build_app(Settings.from_env())


def main() -> None:
    parser = argparse.ArgumentParser(description="CampusPilot local web + Dify pilot")
    parser.add_argument("--data-dir", type=Path, default=Path("data/cdut"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--prompt-key", action="store_true")
    parser.add_argument("--runtime-mode", choices=("legacy", "phase1", "phase2"))
    args = parser.parse_args()
    try:
        settings = replace(Settings.from_env(), data_dir=args.data_dir)
        if args.runtime_mode:
            settings = replace(settings, runtime_mode=args.runtime_mode)
        if args.prompt_key:
            key = getpass.getpass("Dify application API key (hidden): ")
            settings = replace(settings, dify_api_key=key)
        app = build_app(settings)
    except (OSError, ValueError):
        parser.exit(2, "Web configuration or directory data invalid.\n")
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False)
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(uvicorn.Server(config).serve())
    else:
        uvicorn.Server(config).run()
