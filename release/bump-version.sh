#!/usr/bin/env bash
# Version bumper with three modes:
#
#   bump-version.sh            # patch bump, release form  (0.3.1 → 0.3.2,
#                              #   0.3.1-dev → 0.3.2)
#   bump-version.sh --dev      # patch bump, add -dev      (0.3.1 → 0.3.2-dev);
#                              # no-op if already -dev
#   bump-version.sh --release  # strip -dev                (0.3.2-dev → 0.3.2);
#                              # no-op if no -dev
#
# The `-dev` suffix is a placeholder; the build/runtime version resolver
# turns `X.Y.Z-dev` into `X.Y.Z.devN+HASH[.dirty]` using git.
#
# Prints "FROM → TO" on a real change, "no-op: VERSION" otherwise.
# Exits 0 in both cases so callers can run it idempotently.
set -euo pipefail

VERSION_FILE="src/brew_hop_search/VERSION"

MODE="patch"
case "${1:-}" in
    --dev) MODE="dev" ;;
    --release) MODE="release" ;;
    "") MODE="patch" ;;
    *) echo "Usage: $0 [--dev|--release]" >&2; exit 2 ;;
esac

if [ ! -f "$VERSION_FILE" ]; then
    echo "Version file not found: $VERSION_FILE" >&2
    exit 1
fi
current=$(tr -d '[:space:]' < "$VERSION_FILE")
if [ -z "$current" ]; then
    echo "Empty version file: $VERSION_FILE" >&2
    exit 1
fi

# Split into base (X.Y.Z) and optional -dev suffix.
if [[ "$current" =~ ^([0-9]+\.[0-9]+\.[0-9]+)(-dev)?$ ]]; then
    base="${BASH_REMATCH[1]}"
    dev_suffix="${BASH_REMATCH[2]:-}"
else
    echo "Unrecognized version format: $current" >&2
    exit 1
fi

IFS='.' read -r major minor patch <<< "$base"

case "$MODE" in
    patch)
        # Normalize to release form and bump patch.
        new_version="$major.$minor.$((patch + 1))"
        ;;
    dev)
        if [ -n "$dev_suffix" ]; then
            echo "no-op: $current (already dev)"
            exit 0
        fi
        new_version="$major.$minor.$((patch + 1))-dev"
        ;;
    release)
        if [ -z "$dev_suffix" ]; then
            echo "no-op: $current (already release)"
            exit 0
        fi
        new_version="$base"
        ;;
esac

if [ "$new_version" = "$current" ]; then
    echo "no-op: $current"
    exit 0
fi

printf '%s\n' "$new_version" > "$VERSION_FILE"

echo "$current → $new_version"
