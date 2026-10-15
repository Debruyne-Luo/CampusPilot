"""Local UI verification server with synthetic model responses; no external inference."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import campuspilot.app.factory as app_factory
import uvicorn
from campuspilot.app.factory import create_web_app
from campuspilot.llm.chat_model import Completion
from PIL import Image, ImageDraw


def read_amap_configuration(path: Path, root: Path) -> dict[str, str]:
    """Process-only credential loading from the explicitly supplied private file."""
    if not path.is_absolute() or path.resolve().is_relative_to(root):
        raise ValueError("Use a private environment file outside the checkout")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip().strip("\"'")
    return {
        "amap_key": values.get("AMAP_JS_KEY", ""),
        "amap_security_code": values.get("AMAP_SECURITY_JS_CODE", "")
        or values.get("AMAP_JS_SECURITY_CODE", "")
        or values.get("SECURITY_JS_CODE", "")
        or values.get("AMAP_SECURITY_CODE", ""),
        "amap_web_service_key": values.get("AMAP_WEB_SERVICE_KEY", ""),
    }


class SyntheticPreviewModel:
    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> Completion:
        if "意图识别器" in str(messages[0].get("content")):
            question = str(messages[-1].get("content", ""))
            return Completion(
                content=json.dumps(
                    {
                        "intent": "找地点",
                        "missing": [],
                        "destination": "商学院" if "商学院" in question else "E2A403",
                        "image_observation": "纯合成测试图片中可见 BLUE-731。"
                        if isinstance(messages[-1]["content"], list)
                        else "",
                    },
                    ensure_ascii=False,
                )
            )
        return Completion(
            content=json.dumps(
                {"answer": "合成预览模型不生成校园规则。", "source_ids": [], "status": "empty"}
            )
        )

    async def generate(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Synthetic preview only uses the agent loop")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8778)
    parser.add_argument("--assets", type=Path, default=None)
    parser.add_argument("--amap-env", type=Path, default=None)
    args = parser.parse_args()
    if args.assets is not None:
        asset_root = args.assets.resolve(strict=True)
        if not (asset_root / "v2/index.html").is_file():
            parser.error("--assets must point to a web_assets directory with v2/index.html")
        app_factory.ASSETS = asset_root
    output = root / "output/playwright"
    output.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (640, 300), "white")
    ImageDraw.Draw(image).text(
        (20, 90), "SYNTHETIC TEST ONLY: BLUE-731", fill="black", font_size=28
    )
    image.save(output / "synthetic-marker.png")
    amap_config = read_amap_configuration(args.amap_env, root) if args.amap_env else {}
    app = create_web_app(
        data_dir=root / "data/cdut",
        runtime_mode="phase2",
        agent_loop=True,
        images_enabled=True,
        amap_discovery=True,
        model=SyntheticPreviewModel(),
        retrieval_mode="lexical",
        knowledge_bundle="approved-20261011b",
        amap_key=amap_config.get("amap_key", ""),
        amap_security_code=amap_config.get("amap_security_code", ""),
        amap_web_service_key=amap_config.get("amap_web_service_key", ""),
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False))
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(server.serve())
    else:
        asyncio.run(server.serve())
