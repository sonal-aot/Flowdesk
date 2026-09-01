#!/usr/bin/env bash
# Rebuild the m8flow-bpmn-core wheel from source and reinstall it here.
# Usage: ./scripts/refresh_wheel.sh [path-to-core-repo]
set -euo pipefail

core_repo="${1:-$HOME/Documents/GitHub/m8flow-bpmn-core}"
app_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Building wheel in $core_repo"
(cd "$core_repo" && uv build --wheel)

wheel="$(ls -1t "$core_repo"/dist/m8flow_bpmn_core-*.whl | head -n 1)"
echo "==> Staging $(basename "$wheel")"
rm -f "$app_root"/vendor/m8flow_bpmn_core-*.whl
cp "$wheel" "$app_root/vendor/"

# The version is pinned at 0.1.0, so the path in pyproject.toml stays valid and
# only the cached build needs busting.
echo "==> Reinstalling into the app environment"
(cd "$app_root" && uv sync --reinstall-package m8flow-bpmn-core)
