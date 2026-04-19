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

guard_wheel_at_tag() {
    # Content-identity check (see claude-collab/release-flow.md).
    # Verifies the wheel on disk:
    #   1. was built from a clean tree at the tagged commit (BUILD_COMMIT +
    #      BUILD_DIRTY in the packaged _build_info.py), AND
    #   2. the .py files embedded in the wheel are byte-identical to the
    #      current source tree (which, if HEAD==tag, proves wheel == tag).
    local version="$1"
    if [ -z "$version" ]; then
        echo "guard_wheel_at_tag: version required" >&2
        return 2
    fi
    local tag="v${version}"
    if ! git rev-parse --verify "refs/tags/${tag}" >/dev/null 2>&1; then
        echo "✗ tag ${tag} does not exist" >&2
        return 1
    fi
    local tag_sha
    tag_sha=$(git rev-parse "refs/tags/${tag}^{commit}")

    shopt -s nullglob
    local whls=( dist/*"${version}"*.whl )
    shopt -u nullglob
    if [ ${#whls[@]} -eq 0 ]; then
        echo "✗ No dist/*${version}*.whl found." >&2
        return 1
    fi

    local failed=0
    for whl in "${whls[@]}"; do
        local info
        info=$(unzip -p "$whl" 'brew_hop_search/_build_info.py' 2>/dev/null || true)
        if [ -z "$info" ]; then
            echo "✗ ${whl}: missing _build_info.py (was hatch_build.py skipped?)" >&2
            failed=1
            continue
        fi
        local wheel_commit wheel_dirty
        wheel_commit=$(printf '%s\n' "$info" | sed -n 's/^BUILD_COMMIT_FULL = "\([^"]*\)"/\1/p')
        wheel_dirty=$(printf '%s\n' "$info" | sed -n 's/^BUILD_DIRTY = \(.*\)/\1/p')
        if [ "$wheel_commit" != "$tag_sha" ]; then
            echo "✗ ${whl}: built from ${wheel_commit:-?}, expected ${tag_sha}" >&2
            failed=1
        fi
        if [ "$wheel_dirty" = "True" ]; then
            echo "✗ ${whl}: built from a dirty tree (BUILD_DIRTY=True)" >&2
            failed=1
        fi
        # Content check: every .py file in the wheel's brew_hop_search/ tree
        # matches the on-disk src/brew_hop_search/ tree. Skip _build_info.py
        # (generated per build; not in source) and dist-info metadata.
        local tmp; tmp=$(mktemp -d)
        unzip -q "$whl" 'brew_hop_search/*' -d "$tmp" 2>/dev/null || true
        local diffs=""
        while IFS= read -r rel; do
            [[ "$rel" == *"_build_info.py" ]] && continue
            local wheel_file="$tmp/$rel"
            local tree_file="src/$rel"
            if [ ! -f "$tree_file" ]; then
                diffs+="  ✗ wheel has $rel, source tree does not"$'\n'
                continue
            fi
            if ! cmp -s "$wheel_file" "$tree_file"; then
                diffs+="  ✗ content differs: $rel"$'\n'
            fi
        done < <(cd "$tmp" && find brew_hop_search -type f -name '*.py')
        rm -rf "$tmp"
        if [ -n "$diffs" ]; then
            echo "✗ ${whl}: wheel content != current tree:" >&2
            printf '%s' "$diffs" >&2
            failed=1
        fi
    done
    [ "$failed" -eq 0 ]
}

# Back-compat alias: older scripts may still call guard_wheel_fresh.
guard_wheel_fresh() { guard_wheel_at_tag "$@"; }

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
