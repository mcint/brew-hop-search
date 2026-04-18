#!/usr/bin/env bash
# Build and publish to PyPI (or TestPyPI).
#
# Usage:
#   ./scripts/publish.sh            # build + tag rc + publish to TestPyPI
#   ./scripts/publish.sh --release  # build + tag release + publish to PyPI
#   ./scripts/publish.sh --skip-build  # skip rebuild (use existing dist/)
#
# Guards applied before upload:
#   1. Working tree is clean.
#   2. Current version is NOT already published on the target index.
#   3. Built artifacts exist for the current version.
#   4. Artifacts are newer than the matching git tag (if tagged).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=_guards.sh
. "$here/_guards.sh"

INIT_FILE="src/brew_hop_search/__init__.py"
version=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$INIT_FILE")

RELEASE=false
SKIP_BUILD=false
while [ $# -gt 0 ]; do
    case "$1" in
        --release) RELEASE=true ;;
        --skip-build) SKIP_BUILD=true ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
    shift
done

INDEX="testpypi"
TAG_FLAGS=()
PUBLISH_FLAGS=(--index testpypi)
if $RELEASE; then
    INDEX="pypi"
    TAG_FLAGS=(--promote)
    PUBLISH_FLAGS=()
fi

echo "Version: $version  → $INDEX"

if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Working tree not clean. Commit or stash changes first." >&2
    exit 1
fi

guard_pypi_unique "$version" "$INDEX"

if ! $SKIP_BUILD; then
    echo "Building..."
    uv build
fi

guard_dist_exists "$version"

# Tag before freshness check so the tag's commit date is the floor.
./scripts/build-tag.sh "${TAG_FLAGS[@]}"

guard_wheel_fresh "$version"

echo "Publishing to $INDEX..."
# shellcheck disable=SC2086  # glob intentional
uv publish "${PUBLISH_FLAGS[@]}" dist/*"${version}"*

echo "Done."

# ── Post-publish: bump to next .dev0 on dev branch ───────────
# Leaves files uncommitted — the dirty tree is the "release done" marker,
# swept by the next real commit. No-op if already .devN.
if $RELEASE; then
    echo
    echo "── Post-publish: bump dev version ──"
    ./scripts/bump-version.sh --dev
    echo "(uncommitted — git diff to review; sweep with next commit)"
fi
