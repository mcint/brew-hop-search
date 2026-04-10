#!/usr/bin/env bash
# Tag the current commit with a version tag on build.
#
# Default: creates an rc tag (e.g., v0.3.0-rc1, v0.3.0-rc2)
# Promote: ./scripts/build-tag.sh --promote  → tags as v0.3.0 (release)
#
# Usage:
#   ./scripts/build-tag.sh           # auto rc tag
#   ./scripts/build-tag.sh --promote # promote to release tag
#   ./scripts/build-tag.sh --list    # list version tags
#   ./scripts/build-tag.sh --latest  # show latest tag
set -euo pipefail

INIT_FILE="src/brew_hop_search/__init__.py"

# Extract current version
version=$(grep -oP '(?<=__version__ = ")[^"]+' "$INIT_FILE")
if [ -z "$version" ]; then
    echo "Could not find __version__ in $INIT_FILE" >&2
    exit 1
fi

case "${1:-}" in
    --list)
        git tag -l "v${version}*" --sort=-version:refname
        exit 0
        ;;
    --latest)
        git describe --tags --abbrev=0 2>/dev/null || echo "(no tags)"
        exit 0
        ;;
    --promote)
        tag="v${version}"
        if git tag -l "$tag" | grep -q .; then
            echo "Tag $tag already exists. Delete it first: git tag -d $tag" >&2
            exit 1
        fi
        git tag -a "$tag" -m "Release ${version}"
        echo "Tagged: $tag"
        echo "Push with: git push origin $tag"
        exit 0
        ;;
    "")
        # Auto rc: find next rc number
        rc=1
        while git tag -l "v${version}-rc${rc}" | grep -q .; do
            rc=$((rc + 1))
        done
        tag="v${version}-rc${rc}"
        git tag -a "$tag" -m "Release candidate ${version}-rc${rc}"
        echo "Tagged: $tag"
        echo "Promote with: ./scripts/build-tag.sh --promote"
        exit 0
        ;;
    *)
        echo "Usage: $0 [--promote|--list|--latest]" >&2
        exit 1
        ;;
esac
