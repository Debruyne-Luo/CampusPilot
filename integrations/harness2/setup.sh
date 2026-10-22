#!/usr/bin/env bash
# Isolated optional optimizer environment; never changes the normal project interpreter.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$HOME/.local/bin:$PATH"
pin=1cfe254e8d25b15f37048c3730134686abe60335
upstream="$PWD/.cache/harness2-upstream"
if [ ! -d "$upstream/.git" ]; then
  git clone --filter=blob:none --no-checkout https://github.com/google-research/harness2.git "$upstream"
  git -C "$upstream" checkout --detach "$pin"
fi
test "$(git -C "$upstream" rev-parse HEAD)" = "$pin"
uv python install 3.12 3.14.7
uv venv --python 3.12 --allow-existing .cache/harness-env
uv pip install --python .cache/harness-env/bin/python -e "$upstream"
uv venv --python 3.14.7 --allow-existing .cache/campus-env
UV_PROJECT_ENVIRONMENT=.cache/campus-env uv sync --locked --extra api --extra maintenance
python3 integrations/harness2/patch_surface.py "$upstream"
.cache/harness-env/bin/harness2-demo --output output/harness-jev-20261020/upstream-demo --k 1
