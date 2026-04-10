#!/usr/bin/env bash
# Build and publish to PyPI (or TestPyPI).
#
# Usage:
#   ./scripts/publish.sh          # build + tag rc + publish to TestPyPI
#   ./scripts/publish.sh --release # build + tag release + publish to PyPI
set -euo pipefail

INIT_FILE="src/brew_hop_search/__init__.py"
version=$(grep -oP '(?<=__version__ = ")[^"]+' "$INIT_FILE")

echo "Version: $version"

# Ensure clean working tree
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Working tree not clean. Commit or stash changes first." >&2
    exit 1
fi

# Build
echo "Building..."
uv build

# Tag
if [ "${1:-}" = "--release" ]; then
    ./scripts/build-tag.sh --promote
    echo "Publishing to PyPI..."
    uv publish
else
    ./scripts/build-tag.sh
    echo "Publishing to TestPyPI..."
    uv publish --index testpypi
fi

echo "Done."
