#!/usr/bin/env bash
# Shared preflight guards for build/publish scripts.
# Source, don't execute: `. scripts/_guards.sh`
#
# Functions:
#   pypi_versions INDEX    # print published versions (INDEX: pypi|testpypi)
#   guard_pypi_unique VERSION INDEX
#                          # abort if VERSION already published on INDEX
#   guard_wheel_fresh VERSION
#                          # abort if any dist/*VERSION* predates its tag commit
#   guard_dist_exists VERSION
#                          # abort if no dist/*VERSION* files found

PKG_NAME="${PKG_NAME:-brew-hop-search}"

pypi_versions() {
    local index="${1:-pypi}"
    local url
    case "$index" in
        pypi)     url="https://pypi.org/pypi/${PKG_NAME}/json" ;;
        testpypi) url="https://test.pypi.org/pypi/${PKG_NAME}/json" ;;
        *) echo "pypi_versions: unknown index '$index'" >&2; return 2 ;;
    esac
    # 404 = package not yet published → no versions, silent success.
    local body
    body=$(curl -fsSL "$url" 2>/dev/null) || return 0
    printf '%s' "$body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for v in sorted(d.get("releases", {}).keys()):
    print(v)
' | sort -V
}

guard_pypi_unique() {
    local version="$1"
    local index="${2:-pypi}"
    if [ -z "$version" ]; then
        echo "guard_pypi_unique: version required" >&2
        return 2
    fi
    local published
    published=$(pypi_versions "$index") || return 0
    if printf '%s\n' "$published" | grep -qx "$version"; then
        echo "✗ Version $version is already published on $index." >&2
        echo "  Bump the version before building: make bump" >&2
        return 1
    fi
    return 0
}

guard_wheel_fresh() {
    local version="$1"
    if [ -z "$version" ]; then
        echo "guard_wheel_fresh: version required" >&2
        return 2
    fi
    local tag="v${version}"
    local tag_epoch=""
    if git rev-parse --verify "refs/tags/$tag" >/dev/null 2>&1; then
        # Use tagged commit's committer date (not the tag's own date,
        # which can drift if the tag is moved).
        tag_epoch=$(git log -1 --format=%ct "$tag")
    fi
    local stale=0
    shopt -s nullglob
    local files=( dist/*"${version}"*.whl dist/*"${version}"*.tar.gz )
    shopt -u nullglob
    if [ ${#files[@]} -eq 0 ]; then
        echo "✗ No dist/ artifacts matching version $version." >&2
        echo "  Build first: make build" >&2
        return 1
    fi
    for f in "${files[@]}"; do
        local file_epoch
        file_epoch=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f")
        if [ -n "$tag_epoch" ] && [ "$file_epoch" -lt "$tag_epoch" ]; then
            echo "✗ $f predates tag $tag (rebuild needed)." >&2
            stale=1
        fi
    done
    [ "$stale" -eq 0 ]
}

guard_dist_exists() {
    local version="$1"
    shopt -s nullglob
    local files=( dist/*"${version}"* )
    shopt -u nullglob
    if [ ${#files[@]} -eq 0 ]; then
        echo "✗ No dist/ artifacts matching version $version." >&2
        return 1
    fi
    return 0
}
