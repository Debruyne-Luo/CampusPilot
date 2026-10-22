"""Install the upstream-pinned OpenCode editor and Bun into the optional cache."""

import io
import pathlib
import subprocess
import tempfile
import urllib.request
import zipfile

from harness2 import config, install


def main() -> None:
    install.clone("opencode")
    # A Windows checkout can convert the upstream .diff itself to CRLF. Feed the
    # unchanged patch content as LF to Linux git, preserving the upstream patch.
    source = config.THIRD_PARTY / "patches/opencode-compat.diff"
    with tempfile.NamedTemporaryFile(suffix=".diff") as patch:
        patch.write(source.read_bytes().replace(b"\r\n", b"\n"))
        patch.flush()
        cmd = ["git", "-C", str(config.OPENCODE_DIR), "apply"]
        if subprocess.run(
            cmd + ["--reverse", "--check", patch.name], capture_output=True
        ).returncode:
            subprocess.run(cmd + ["--check", patch.name], check=True)
            subprocess.run(cmd + [patch.name], check=True)
    binary = config.BUN
    if not binary.exists():
        url = "https://github.com/oven-sh/bun/releases/download/bun-v1.3.11/bun-linux-x64.zip"
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(100_000_000)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(archive.read("bun-linux-x64/bun"))
        binary.chmod(0o755)
    subprocess.run(
        [str(binary), "install", "--frozen-lockfile", "--ignore-scripts"],
        cwd=config.OPENCODE_DIR,
        check=True,
    )
    pathlib.Path(config.DEPENDENCIES / "editor-ready.txt").write_text(
        config.DEPENDENCY_PINS["opencode"] + "\nbun@1.3.11\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
