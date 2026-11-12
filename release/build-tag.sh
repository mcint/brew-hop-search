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

VERSION_FILE="src/brew_hop_search/VERSION"

version=$(tr -d '[:space:]' < "$VERSION_FILE" 2>/dev/null || true)
if [ -z "$version" ]; then
    echo "Could not read version from $VERSION_FILE" >&2
    exit 1
fi

# Print a tag message: title + "Changes since <prev tag>:" + bulleted log.
# $1 = title (e.g. "Release 0.3.6"), $2 = prev-tag match mode: "release-only"
# skips `-rc*` tags when finding the comparison base.
_tag_message() {
    local title="$1" mode="${2:-any}" prev_tag
    if [ "$mode" = "release-only" ]; then
        prev_tag=$(git describe --tags --abbrev=0 --match 'v*' --exclude '*-rc*' 2>/dev/null || true)
    else
        prev_tag=$(git describe --tags --abbrev=0 --match 'v*' 2>/dev/null || true)
    fi
    printf '%s\n\n' "$title"
    if [ -n "$prev_tag" ]; then
        printf 'Changes since %s:\n\n' "$prev_tag"
        git log --pretty=format:'- %s' "${prev_tag}..HEAD"
        printf '\n'
    else
        printf 'Initial tagged release.\n'
    fi
}

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
        _tag_message "Release ${version}" release-only | git tag -a "$tag" -F -
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
        _tag_message "Release candidate ${version}-rc${rc}" | git tag -a "$tag" -F -
        echo "Tagged: $tag"
        echo "Promote with: ./scripts/build-tag.sh --promote"
        exit 0
        ;;
    *)
        echo "Usage: $0 [--promote|--list|--latest]" >&2
        exit 1
        ;;
esac
