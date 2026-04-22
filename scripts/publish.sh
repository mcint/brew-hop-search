#!/usr/bin/env bash
# Publish the already-tagged, already-built package to PyPI (or TestPyPI).
#
# Usage:
#   ./scripts/publish.sh            # publish to TestPyPI
#   ./scripts/publish.sh --release  # publish to PyPI
#   ./scripts/publish.sh --skip-build  # assume dist/ is already populated
#
# Invariants (see claude-collab/release-flow.md):
#   - HEAD must be on the tag matching the current version (no tagging here).
#   - dist/*VERSION* must exist.
#   - wheel version must match tag version (quick identity check).
#   - VERSION must not already be on the target index.
#
# Re-runnable: if an upload fails mid-flight, re-invoke. This script never
# re-tags and never rebuilds (unless --skip-build is absent and dist/ is
# empty).
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=_guards.sh
. "$here/_guards.sh"

VERSION_FILE="src/brew_hop_search/VERSION"
version=$(tr -d '[:space:]' < "$VERSION_FILE")

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
PUBLISH_FLAGS=(--index testpypi)
if $RELEASE; then
    INDEX="pypi"
    PUBLISH_FLAGS=()
fi

echo "Version: $version  → $INDEX"

# ── Guard: tree clean ────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "✗ Working tree not clean. Commit or stash first." >&2
    exit 1
fi

# ── Guard: HEAD is on the version tag ────────────────────────
tag="v${version}"
if ! git rev-parse --verify "refs/tags/${tag}" >/dev/null 2>&1; then
    echo "✗ Tag ${tag} does not exist. Tag first:" >&2
    echo "    ./scripts/build-tag.sh --promote" >&2
    exit 1
fi
head_sha=$(git rev-parse HEAD)
tag_sha=$(git rev-parse "refs/tags/${tag}^{commit}")
if [ "$head_sha" != "$tag_sha" ]; then
    echo "✗ HEAD is not on ${tag}." >&2
    echo "    HEAD: $head_sha" >&2
    echo "    ${tag}: $tag_sha" >&2
    echo "  Checkout the tag or retag HEAD before publishing." >&2
    exit 1
fi

guard_pypi_unique "$version" "$INDEX"

# ── Build (if needed) ────────────────────────────────────────
if ! $SKIP_BUILD; then
    shopt -s nullglob
    existing=( dist/*"${version}"*.whl dist/*"${version}"*.tar.gz )
    shopt -u nullglob
    if [ ${#existing[@]} -eq 0 ]; then
        echo "Building..."
        uv build
    else
        echo "dist/ already has artifacts for ${version} — skipping build."
        echo "  (pass --skip-build to silence, or rm dist/ to force rebuild)"
    fi
fi

guard_dist_exists "$version"
guard_wheel_at_tag "$version"

# ── Publish ──────────────────────────────────────────────────
echo "Publishing to $INDEX..."
# shellcheck disable=SC2086
uv publish "${PUBLISH_FLAGS[@]}" dist/*"${version}"*

echo "Done."
