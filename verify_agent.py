"""Offline, fail-closed acceptance of the complete standalone Agent package.

Run after uv sync. No model keys, external network or production service is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import shutil
import socket
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AgentPackageChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from campuspilot.directory.repository import DirectoryRepository
        from campuspilot.knowledge import KnowledgeStore
        from campuspilot.rag import SnapshotStore
        from campuspilot.tools import agent_registry
        from run_agent import settings_for_package

        cls.settings = settings_for_package(offline=True)
        cls.package = json.loads((ROOT / "PACKAGE.json").read_text(encoding="utf-8"))
        cls.store = SnapshotStore(cls.settings.data_dir / "rag", retrieval_mode="lexical")
        cls.reader = cls.store.acquire()
        cls.directory = cls.store.bind_directory(cls.settings.data_dir)
        cls.repository = DirectoryRepository.load(cls.directory)
        cls.knowledge = KnowledgeStore.load(cls.directory / "knowledge.json")
        cls.registry = agent_registry(
            cls.repository, cls.knowledge, cls.store, roster=cls.directory / "teachers_roster.json"
        )

    def test_01_complete_manifest(self):
        manifest = json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertGreater(len(manifest["files"]), 300)
        for name, expected in manifest["files"].items():
            target = (ROOT / name).resolve()
            self.assertTrue(target.is_relative_to(ROOT))
            self.assertEqual(digest(target), expected, name)

    def test_02_source_identity(self):
        from knowledge_bundle import _long_path

        self.assertEqual(self.package["source_commit"], "15c3b9e91c9f9bde74654c1756c3158b91e363c0")
        for name, expected in self.package["unchanged_source_files_sha256"].items():
            self.assertEqual(digest(_long_path(ROOT / name)), expected, name)
        for name, modification in self.package.get("source_modifications", {}).items():
            self.assertEqual(digest(ROOT / name), modification["packaged_sha256"], name)

    def test_03_runtime_imports(self):
        base = ROOT / "backend/src"
        for path in sorted((base / "campuspilot").rglob("*.py")):
            name = (
                path.relative_to(base)
                .with_suffix("")
                .as_posix()
                .replace("/", ".")
                .removesuffix(".__init__")
            )
            importlib.import_module(name)

    def test_04_knowledge_and_directory_binding(self):
        self.assertIsNotNone(self.reader)
        self.assertEqual(self.reader.snapshot.version, self.package["knowledge_version"])
        self.assertEqual(len(self.reader.snapshot.sources), 192)
        self.assertEqual(len(self.reader.snapshot.chunks), 402)
        self.assertEqual(len(self.repository.services()), 36)
        self.assertEqual(self.directory.parent.name, self.package["knowledge_version"])
        self.assertEqual(self.store.load_error, "")

    def test_05_frontend_and_resource_identity(self):
        from campuspilot.app.factory import asset_hash
        from campuspilot.app.state import ASSETS

        self.assertEqual(asset_hash(), self.package["frontend_fingerprint"])
        for name in (
            "v2/index.html",
            "map-frame.html",
            "dino3d.mjs",
            "models/graduate-dino.glb",
            "models/cdutdino-guide.glb",
            "vendor/THREE-LICENSE.md",
        ):
            self.assertTrue((ASSETS / name).is_file(), name)

    def test_06_tool_contracts_and_parameter_errors(self):
        from campuspilot.tools import ToolError

        for name in (
            "search_service",
            "make_checklist",
            "search_knowledge",
            "search_place",
            "find_teacher",
        ):
            self.assertIn(name, self.registry.names)
        with self.assertRaises(ToolError):
            self.registry.call("make_checklist", {"service_id": "../outside"})
        with self.assertRaises(ToolError):
            self.registry.call("submit_application", {})
        result = self.registry.call("search_service", {"query": "校园卡"})
        self.assertIn(result["status"], ("success", "partial"))

    def test_07_execution_permission_is_not_model_authority(self):
        from campuspilot.agent.execution import ExecutionBoundary
        from campuspilot.contracts import ExecutionContext
        from campuspilot.tools import ToolError

        ctx = ExecutionContext(
            session_id="verify", task_id="verify", run_id="verify", allowed_tools=frozenset()
        )
        boundary = ExecutionBoundary(ctx, audit=lambda *args: None)
        with self.assertRaises(ToolError) as caught:
            boundary.call_tool(self.registry, "search_service", {"query": "校园卡"})
        self.assertEqual(caught.exception.code, "permission_denied")

    def agent(self, model=None):
        from campuspilot.agent.executor import AgentRunner

        return AgentRunner(self.registry, self.repository, model, snapshots=self.store)

    def test_08_local_agent_has_real_sourced_checklist(self):
        from campuspilot.chat_runtime import ConversationContext

        result = asyncio.run(self.agent().run("校园卡补办需要什么材料", ConversationContext()))
        self.assertEqual(result["result_status"], "limited")
        self.assertEqual(result["degraded_reason"], "model_not_configured")
        self.assertEqual(result["checklist"]["service_id"], "cdut:service:campus-card-replacement")
        self.assertTrue(result["citations"])
        self.assertTrue(result["answer"])

    def test_09_scripted_model_runs_the_real_agent(self):
        from campuspilot.agent.understand import UNDERSTAND_SYSTEM
        from campuspilot.chat_runtime import ConversationContext
        from campuspilot.llm.chat_model import Completion

        service = self.repository.find_service("cdut:service:campus-card-replacement")
        ids = sorted({i for f in service.field_evidence for i in f.evidence_ids})

        class ScriptedModel:
            calls = 0

            async def complete(self, messages, tools=None, json_mode=False, max_tokens=None):
                self.calls += 1
                if messages[0]["content"] == UNDERSTAND_SYSTEM:
                    payload = {
                        "intent": "办事",
                        "identity": "unknown",
                        "service": "校园卡补办",
                        "missing": [],
                    }
                else:
                    payload = {
                        "answer": (
                            "自助补卡前确认卡内余额大于20元，带好本人身份证，"
                            "到珙桐或香樟食堂自助服务区办理。"
                        ),
                        "source_ids": ids,
                        "status": "success",
                    }
                return Completion(content=json.dumps(payload, ensure_ascii=False))

            async def generate(self, *args, **kwargs):
                raise AssertionError("Agent must use the tool-calling path.")

        model = ScriptedModel()
        result = asyncio.run(self.agent(model).run("校园卡补办需要什么材料", ConversationContext()))
        self.assertGreater(model.calls, 0)
        self.assertEqual(result["result_status"], "success")
        self.assertIn("20元", result["answer"])
        self.assertTrue(result["citations"])

    def test_10_private_action_is_rejected(self):
        from campuspilot.chat_runtime import ConversationContext

        result = asyncio.run(self.agent().run("请替我登录并缴费", ConversationContext()))
        self.assertNotEqual(result["result_status"], "success")
        self.assertIn("不能", result["answer"])

    def test_11_offline_configuration_overrides_external_flags(self):
        from run_agent import settings_for_package

        with patch.dict(
            os.environ,
            {
                "CAMPUSPILOT_WEB_SEARCH": "on",
                "CAMPUSPILOT_JEV": "on",
                "CAMPUSPILOT_IMAGES": "on",
                "CAMPUSPILOT_MODEL_API_KEY": "offline-check-only",
            },
        ):
            settings = settings_for_package(offline=True)
            self.assertFalse(settings.web_search)
            self.assertFalse(settings.images_enabled)
            self.assertEqual(settings.jev, "off")
            self.assertNotIn("CAMPUSPILOT_MODEL_API_KEY", os.environ)
            self.assertTrue(settings.agent_loop)
            self.assertEqual(settings.runtime_mode, "phase2")
            self.assertFalse(settings.harness_profile)

    def test_12_external_config_validation(self):
        from run_agent import read_config

        with self.assertRaises(ValueError):
            read_config(ROOT / "config.example.json")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"CAMPUSPILOT_MODEL": "example-model"}', encoding="utf-8")
            self.assertEqual(read_config(path)["CAMPUSPILOT_MODEL"], "example-model")
            path.write_text('{"UNRECOGNIZED_COMMAND": "bad"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_config(path)
            path.write_text('{"CAMPUSPILOT_MODEL": 123}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_config(path)

    def test_13_web_answers_citations_and_sse(self):
        from campuspilot.app.main import build_app
        from fastapi.testclient import TestClient

        headers = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
        with TestClient(build_app(self.settings)) as client:
            self.assertEqual(client.get("/healthz").json()["status"], "ready")
            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertIn(self.package["frontend_fingerprint"], home.text)
            session = client.post("/api/session", headers=headers).json()
            self.assertFalse(session["model_configured"])
            self.assertEqual(session["runtime_mode"], "phase2")
            self.assertEqual(len(client.get("/api/catalog").json()["services"]), 36)
            result = client.post(
                "/api/chat", json={"message": "校园卡补办需要什么材料"}, headers=headers
            ).json()
            self.assertEqual(result["degraded_reason"], "model_not_configured")
            self.assertTrue(result["citations"])
            self.assertEqual(
                result["checklist"]["service_id"], "cdut:service:campus-card-replacement"
            )
            stream = client.post(
                "/api/chat/stream", json={"message": "校园卡补办需要什么材料"}, headers=headers
            )
            self.assertIn("text/event-stream", stream.headers["content-type"])
            self.assertIn("model_not_configured", stream.text)
            self.assertIn("campus-card-replacement", stream.text)
            self.assertFalse(client.get("/api/map-config").json()["configured"])

    def test_14_bundled_knowledge_preserves_every_source_byte(self):
        expected = {
            n.removeprefix("data/cdut/"): checksum
            for n, checksum in self.package["unchanged_source_files_sha256"].items()
            if n.startswith("data/cdut/")
        }
        self.assertEqual(len(expected), 259)
        with zipfile.ZipFile(ROOT / "data/knowledge.zip") as archive:
            self.assertEqual(set(archive.namelist()), set(expected))
            for name, checksum in expected.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), checksum)

    def test_15_knowledge_bootstrap_rejects_corruption_and_unsafe_paths(self):
        from knowledge_bundle import prepare_knowledge

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()

            def fixture(name, content):
                with zipfile.ZipFile(root / "data/knowledge.zip", "w") as archive:
                    archive.writestr(name, content)
                (root / "PACKAGE.json").write_text(
                    json.dumps(
                        {
                            "unchanged_source_files_sha256": {
                                "data/cdut/" + name: hashlib.sha256(content).hexdigest()
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                (root / "MANIFEST.json").write_text(
                    json.dumps(
                        {"files": {"data/knowledge.zip": digest(root / "data/knowledge.zip")}}
                    ),
                    encoding="utf-8",
                )

            # Synthetic archive contract fixture, not a university record.
            fixture("rag/current.json", b'{"synthetic_test":true}')
            restored = prepare_knowledge(root)
            self.assertEqual(
                (restored / "rag/current.json").read_bytes(), b'{"synthetic_test":true}'
            )
            self.assertEqual(prepare_knowledge(root), restored)
            (restored / "rag/current.json").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "Existing knowledge was modified"):
                prepare_knowledge(root)
            fixture("../escape.txt", b"synthetic unsafe path test")
            with self.assertRaisesRegex(ValueError, "Unsafe knowledge archive member"):
                prepare_knowledge(root)
            self.assertFalse((root / "data/escape.txt").exists())
            (root / "data/knowledge.zip").write_bytes(b"corrupt archive")
            with self.assertRaisesRegex(ValueError, "Knowledge bundle checksum mismatch"):
                prepare_knowledge(root)

    def test_16_restored_hybrid_index_is_usable(self):
        from campuspilot.rag import SnapshotStore

        store = SnapshotStore(self.settings.data_dir / "rag", retrieval_mode="hybrid")
        reader = store.acquire()
        self.assertEqual(reader.snapshot.version, self.package["knowledge_version"])
        self.assertEqual(store.index_error, "")
        self.assertIsNotNone(reader.index)
        reader.index.close()

    def test_17_sqlite_file_uri_escapes_filename_delimiters(self):
        from campuspilot.knowledge_release import load_candidate_index
        from campuspilot.retrieval.vector import VectorIndex

        version = self.settings.data_dir / "rag/versions" / self.package["knowledge_version"]
        manifest = json.loads((version / "manifest.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            # A literal #, percent sign and spaces are valid filename characters.
            target = Path(temp) / "synthetic URI path #100%"
            target.mkdir()
            shutil.copyfile(version / "vectors.sqlite", target / "vectors.sqlite")
            checked = load_candidate_index(target, self.reader.snapshot, manifest)
            self.assertEqual(len(checked.vectors), 402)
            checked.close()
            loaded = VectorIndex.load(
                target / "vectors.sqlite", self.reader.snapshot, manifest["vector_index"]["model"]
            )
            self.assertEqual(len(loaded.vectors), 402)
            loaded.close()


def main() -> None:
    # Any accidental real HTTP/DNS call fails this offline acceptance immediately.
    with patch.object(
        socket,
        "getaddrinfo",
        side_effect=AssertionError("Network forbidden in offline verification"),
    ):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(AgentPackageChecks)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
