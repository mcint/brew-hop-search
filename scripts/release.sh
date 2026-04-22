#!/usr/bin/env bash
# Interactive release process with checkpoints.
#
# Flow (see claude-collab/release-flow.md):
#   test → promote dev → tag → build → publish → ff main → post-bump
#
# Flags:
#   --yes, -y        Auto-confirm all prompts (still stops on error)
#   --dry-run, -n    Show what would happen without doing it
#   --verbose, -V    Print each command before running it
#   --rc             Pre-select rc tag (default interactive)
#   --release        Pre-select release tag (promote)
#   --skip-tag       Skip tagging step (for re-runs, already tagged)
#   --skip-publish   Stop before publish (dry-publish mode)
#   --testpypi       Publish to TestPyPI instead of PyPI
#
# Usage:
#   ./scripts/release.sh                 # interactive
#   ./scripts/release.sh --yes --release # unattended PyPI release
#   ./scripts/release.sh --dry-run       # see the plan
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=_guards.sh
. "$here/_guards.sh"

# ── Flags ────────────────────────────────────────────────────
YES=false
DRY=false
VERBOSE=false
TAG_MODE="ask"      # ask | rc | release | skip
SKIP_PUBLISH=false
PUBLISH_INDEX="pypi"

while [ $# -gt 0 ]; do
    case "$1" in
        --yes|-y) YES=true ;;
        --dry-run|-n) DRY=true; VERBOSE=true ;;
        --verbose|-V) VERBOSE=true ;;
        --rc) TAG_MODE="rc" ;;
        --release) TAG_MODE="release" ;;
        --skip-tag) TAG_MODE="skip" ;;
        --skip-publish) SKIP_PUBLISH=true ;;
        --testpypi) PUBLISH_INDEX="testpypi" ;;
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

VERSION_FILE="src/brew_hop_search/VERSION"
VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")
BRANCH=$(git rev-parse --abbrev-ref HEAD)
TAG=""

# ── Auto-promote .devN → release ─────────────────────────────
if [[ "$VERSION" == *.dev* ]]; then
    if $DRY; then
        promoted=${VERSION%.dev*}
        echo "(dry-run: would promote $VERSION → $promoted and commit)"
        VERSION="$promoted"
    else
        ./scripts/bump-version.sh --release
        VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")
        git add "$VERSION_FILE"
        git commit -m "Promote to release v${VERSION}" -q
        echo "✓ promoted to release v${VERSION}"
    fi
fi

echo "═══════════════════════════════════════════════════════"
echo "  brew-hop-search release process"
echo "  version: $VERSION  branch: $BRANCH  index: $PUBLISH_INDEX"
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
    echo "(dry-run: would check $PUBLISH_INDEX for v$VERSION)"
else
    if ! guard_pypi_unique "$VERSION" "$PUBLISH_INDEX"; then
        echo "Run 'make versions' to see all published versions." >&2
        exit 1
    fi
    echo "✓ $VERSION is unpublished on $PUBLISH_INDEX"
fi
echo

# ── Step 1: Test ─────────────────────────────────────────────
echo "── Step 1: Run tests ──────────────────────────────────"
run uv run python -m pytest tests/ -x -q --tb=short
echo "✓ Tests passed"
echo

# ── Step 2: Review changes ───────────────────────────────────
echo "── Step 2: Changes since last release ─────────────────"
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

# ── Step 3: Tag ──────────────────────────────────────────────
echo
echo "── Step 3: Tag ──────────────────────────────────────"
if [ "$TAG_MODE" = "ask" ]; then
    if $DRY; then
        echo "(dry-run: would ask rc/release/skip, defaulting to release)"
        TAG_MODE="release"
    else
        echo "  a) v${VERSION}-rcN  (release candidate)"
        echo "  b) v${VERSION}      (release)"
        echo "  c) skip tagging    (already tagged — re-run path)"
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
        TAG="v${VERSION}"
        echo "Skipped tagging; assuming $TAG already points at HEAD."
        ;;
esac
echo

# ── Step 4: Build (after tagging, so _build_info records the tag) ──
echo "── Step 4: Build package ──────────────────────────────"
if ! $DRY; then
    rm -rf dist/
fi
run uv build
if ! $DRY; then
    echo
    echo "Built:"
    ls -1 dist/*"${VERSION}"* 2>/dev/null || echo "(no matching dist files)"
fi
echo

# ── Step 5: Publish ──────────────────────────────────────────
if $SKIP_PUBLISH; then
    echo "── Step 5: Publish (SKIPPED via --skip-publish) ──────"
    echo "  resume with: ./scripts/publish.sh $([ "$PUBLISH_INDEX" = pypi ] && echo --release) --skip-build"
    echo
else
    echo "── Step 5: Publish to $PUBLISH_INDEX ────────────────────"
    if $DRY; then
        echo "(dry-run: would call publish.sh --skip-build$([ "$PUBLISH_INDEX" = pypi ] && echo ' --release'))"
    else
        confirm "Publish v${VERSION} to ${PUBLISH_INDEX}?" || { echo "Aborted before publish."; exit 1; }
        publish_args=(--skip-build)
        [ "$PUBLISH_INDEX" = "pypi" ] && publish_args+=(--release)
        ./scripts/publish.sh "${publish_args[@]}"
    fi
    echo "✓ Published"
    echo
fi

# ── Step 6: Fast-forward main (only after real-PyPI publish) ─
if [ "$BRANCH" != "main" ] && ! $SKIP_PUBLISH && [ "$PUBLISH_INDEX" = "pypi" ]; then
    echo "── Step 6: Fast-forward main ──────────────────────────"
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

# ── Step 7: Post-publish bump to next .dev0 (PyPI only) ──────
if [ "$TAG_MODE" = "release" ] && ! $SKIP_PUBLISH && ! $DRY && [ "$PUBLISH_INDEX" = "pypi" ]; then
    echo "── Step 7: Post-publish: bump dev version ─────────────"
    ./scripts/bump-version.sh --dev
    echo "(uncommitted — git diff to review; sweep with next commit)"
    echo
fi

# ── Step 8: Push commands ────────────────────────────────────
echo "── Step 8: Push ─────────────────────────────────────"
echo
if [ -n "$TAG" ]; then
    echo "# Push tag + branches:"
    echo "git push origin $TAG"
fi
echo "git push origin $BRANCH"
[ "$BRANCH" != "main" ] && ! $SKIP_PUBLISH && echo "git push origin main"
echo
echo "Done."
