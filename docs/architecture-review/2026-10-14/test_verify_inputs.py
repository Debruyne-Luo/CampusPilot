"""Exercise the audit input checker in disposable Git repositories."""

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).with_name("verify_inputs.py")


class ReviewInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="campuspilot-review-check-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_git("init", "-q")
        (self.root / "source.txt").write_bytes(b"original\n")
        self.run_git("add", "source.txt")
        self.run_git(
            "-c",
            "user.name=Review Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.hooksPath=NUL",
            "commit",
            "-qm",
            "synthetic baseline",
        )
        self.manifest = self.root / "docs/architecture-review/test/REVIEW_INPUTS.json"
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(
            json.dumps(
                {
                    "head": self.run_git("rev-parse", "HEAD"),
                    "branch": self.run_git("branch", "--show-current"),
                    "files": [
                        {"path": "source.txt", "sha256": hashlib.sha256(b"original\n").hexdigest()}
                    ],
                }
            ),
            encoding="utf-8",
        )

    def run_git(self, *args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=self.root, encoding="utf-8").strip()

    def check(self) -> tuple[int, dict]:
        import sys

        process = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-B",
                str(CHECKER),
                "--root",
                str(self.root),
                "--manifest",
                str(self.manifest),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        return process.returncode, json.loads(process.stdout)

    def test_unchanged_and_audit_docs_pass(self) -> None:
        (self.manifest.parent / "notes.md").write_text("audit notes", encoding="utf-8")
        code, report = self.check()
        self.assertEqual(code, 0)
        self.assertTrue(report["matches_captured_inputs"])

    def test_changed_existing_input_fails(self) -> None:
        (self.root / "source.txt").write_bytes(b"changed\n")
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertIn({"path": "source.txt", "reason": "bytes_changed"}, report["differences"])

    def test_deleted_input_fails(self) -> None:
        (self.root / "source.txt").unlink()
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertIn({"path": "source.txt", "reason": "missing_input"}, report["differences"])

    def test_new_untracked_input_fails(self) -> None:
        (self.root / "new.txt").write_text("new work", encoding="utf-8")
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertIn({"path": "new.txt", "reason": "new_input"}, report["differences"])

    def test_new_filename_with_leading_space_fails(self) -> None:
        (self.root / " source.txt").write_text("new work", encoding="utf-8")
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertIn({"path": " source.txt", "reason": "new_input"}, report["differences"])

    def test_commit_drift_fails(self) -> None:
        self.run_git(
            "-c",
            "user.name=Review Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "core.hooksPath=NUL",
            "commit",
            "--allow-empty",
            "-qm",
            "drift",
        )
        code, report = self.check()
        self.assertEqual(code, 1)
        self.assertIn({"path": "HEAD", "reason": "commit_changed"}, report["differences"])

    def test_malformed_manifest_fails_closed(self) -> None:
        self.manifest.write_text("not json", encoding="utf-8")
        code, report = self.check()
        self.assertEqual(code, 2)
        self.assertFalse(report["matches_captured_inputs"])


if __name__ == "__main__":
    unittest.main()
