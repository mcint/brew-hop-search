#!/usr/bin/env bash
# Interactive release process with checkpoints.
#
# Steps: test → build → review → tag → ff main → show publish command
# Each step pauses for confirmation unless --yes is passed.
#
# Flags:
#   --yes, -y      Auto-confirm all prompts (still stops on error)
#   --dry-run, -n  Show what would happen without doing it
#   --verbose, -V  Print each command before running it
#   --rc           Pre-select rc tag (default)
#   --release      Pre-select release tag
#
# Usage:
#   ./scripts/release.sh                # interactive
#   ./scripts/release.sh --yes --rc     # unattended rc build
#   ./scripts/release.sh --dry-run      # see the plan
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=_guards.sh
. "$here/_guards.sh"

# ── Flags ────────────────────────────────────────────────────
YES=false
DRY=false
VERBOSE=false
TAG_MODE="ask"  # ask | rc | release | skip

while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) YES=true ;;
        --dry-run|-n) DRY=true; VERBOSE=true ;;
        --verbose|-V) VERBOSE=true ;;
        --rc) TAG_MODE="rc" ;;
        --release) TAG_MODE="release" ;;
        --skip-tag) TAG_MODE="skip" ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
    shift
done

# ── Helpers ──────────────────────────────────────────────────
run() {
    if $VERBOSE; then
        echo "  \$ $*" >&2
    fi
    if $DRY; then
        return 0
    fi
    "$@"
}

confirm() {
    if $YES || $DRY; then
        echo "$1 [auto-yes]"
        return 0
    fi
    read -rp "$1 [y/N] " ans
    [ "$ans" = "y" ]
}

INIT_FILE="src/brew_hop_search/__init__.py"
VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$INIT_FILE")
BRANCH=$(git rev-parse --abbrev-ref HEAD)
TAG=""

# ── Auto-promote .devN → release ─────────────────────────────
# If __version__ is X.Y.Z.devN, strip the suffix before tagging so the tag
# and the release line up. Commit the promotion (silently no-op if not dev).
if [[ "$VERSION" == *.dev* ]]; then
    if $DRY; then
        promoted=${VERSION%.dev*}
        echo "(dry-run: would promote $VERSION → $promoted and commit)"
        VERSION="$promoted"
    else
        ./scripts/bump-version.sh --release
        VERSION=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$INIT_FILE")
        git add "$INIT_FILE" pyproject.toml
        git commit -m "Promote to release v${VERSION}" -q
        echo "✓ promoted to release v${VERSION}"
    fi
fi

echo "═══════════════════════════════════════════════════════"
echo "  brew-hop-search release process"
echo "  version: $VERSION  branch: $BRANCH"
$DRY && echo "  MODE: dry-run (no changes will be made)"
$YES && echo "  MODE: auto-confirm"
echo "═══════════════════════════════════════════════════════"
echo

# ── Preflight ────────────────────────────────────────────────
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
    echo "⚠  Uncommitted changes:"
    git status -s
    echo
    confirm "Continue anyway?" || exit 1
fi

# ── Step 0: PyPI preflight ───────────────────────────────────
echo "── Step 0: PyPI version check ─────────────────────────"
if $DRY; then
    echo "(dry-run: would check pypi + testpypi for v$VERSION)"
else
    if ! guard_pypi_unique "$VERSION" pypi; then
        echo "Run 'make versions' to see all published versions." >&2
        exit 1
    fi
    if ! guard_pypi_unique "$VERSION" testpypi; then
        echo "(testpypi collision — ok to --skip-tag and proceed to pypi, or bump)" >&2
        confirm "Continue to pypi anyway?" || exit 1
    fi
    echo "✓ $VERSION is unpublished on pypi + testpypi"
fi
echo

# ── Step 1: Test ─────────────────────────────────────────────
echo "── Step 1: Run tests ──────────────────────────────────"
run uv run python -m pytest tests/ -x -q --tb=short
echo "✓ Tests passed"
echo

# ── Step 2: Build ────────────────────────────────────────────
echo "── Step 2: Build package ──────────────────────────────"
run uv build
echo
if ! $DRY; then
    echo "Built:"
    ls -1 dist/*"${VERSION}"* 2>/dev/null || echo "(no matching dist files)"
fi
echo

# ── Step 3: Review changes ───────────────────────────────────
echo "── Step 3: Changes since last release ─────────────────"
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
if [ -n "$LAST_TAG" ]; then
    echo "Last tag: $LAST_TAG"
    echo
    git log --oneline "$LAST_TAG"..HEAD
else
    echo "(no previous tags — showing last 10 commits)"
    echo
    git log --oneline -10
fi
echo
confirm "Review complete. Ready to tag?" || { echo "Aborted."; exit 1; }

# ── Step 4: Tag ──────────────────────────────────────────────
echo
echo "── Step 4: Tag ──────────────────────────────────────"
if [ "$TAG_MODE" = "ask" ]; then
    if $DRY; then
        echo "(dry-run: would ask rc/release/skip, defaulting to rc)"
        TAG_MODE="rc"
    else
        echo "  a) v${VERSION}-rcN  (release candidate)"
        echo "  b) v${VERSION}      (release)"
        echo "  c) skip tagging"
        read -rp "Choice [a/b/c]: " tag_choice
        case "$tag_choice" in
            a) TAG_MODE="rc" ;;
            b) TAG_MODE="release" ;;
            c) TAG_MODE="skip" ;;
            *) echo "Invalid choice. Aborted."; exit 1 ;;
        esac
    fi
fi

case "$TAG_MODE" in
    rc)
        run ./scripts/build-tag.sh
        TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v${VERSION}-rc1")
        ;;
    release)
        run ./scripts/build-tag.sh --promote
        TAG="v${VERSION}"
        ;;
    skip)
        echo "Skipped tagging."
        ;;
esac
echo

# ── Step 5: Fast-forward main ────────────────────────────────
if [ "$BRANCH" != "main" ]; then
    echo "── Step 5: Fast-forward main ──────────────────────────"
    if git merge-base --is-ancestor main HEAD 2>/dev/null; then
        AHEAD=$(git rev-list main..HEAD --count)
        echo "main is $AHEAD commits behind $BRANCH"
        if confirm "Fast-forward main to $BRANCH?"; then
            run git fetch . "$BRANCH":main
            echo "✓ main fast-forwarded"
        fi
    else
        echo "⚠  main cannot be fast-forwarded (diverged)"
    fi
    echo
fi

# ── Step 6: Publish commands ─────────────────────────────────
echo "── Step 6: Publish ──────────────────────────────────"
echo
echo "# TestPyPI:"
echo "uv publish --index testpypi --token \$UV_PUBLISH_TOKEN dist/*${VERSION}*"
echo
echo "# PyPI:"
echo "uv publish --token \$UV_PUBLISH_TOKEN dist/*${VERSION}*"
echo
if [ -n "$TAG" ]; then
    echo "# Push tag + main:"
    echo "git push origin $TAG"
    [ "$BRANCH" != "main" ] && echo "git push origin main"
fi
echo
echo "Done. Copy and run the commands above when ready."
