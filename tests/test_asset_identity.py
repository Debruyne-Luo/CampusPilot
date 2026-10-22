"""Identical exported assets retain one version on case-sensitive and Windows hosts."""

import hashlib
from pathlib import Path

from campuspilot.app.factory import asset_hash


def test_asset_version_uses_case_sensitive_portable_filename_order(tmp_path: Path) -> None:
    (tmp_path / "alpha.txt").write_bytes(b"SYNTHETIC lower")
    (tmp_path / "Beta.txt").write_bytes(b"SYNTHETIC upper")
    # Portable order is Beta before alpha, regardless of host filesystem collation.
    expected = hashlib.sha256(
        b"Beta.txt\0SYNTHETIC upperalpha.txt\0SYNTHETIC lower"
    ).hexdigest()[:12]
    assert asset_hash(tmp_path) == expected
