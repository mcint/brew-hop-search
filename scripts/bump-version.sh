#!/usr/bin/env bash
# Version bumper with three modes:
#
#   bump-version.sh            # patch bump, release form  (0.3.1 → 0.3.2,
#                              #   0.3.1.dev0 → 0.3.2)
#   bump-version.sh --dev      # patch bump, add .dev0     (0.3.1 → 0.3.2.dev0);
#                              # no-op if already .devN
#   bump-version.sh --release  # strip .devN               (0.3.2.dev0 → 0.3.2);
#                              # no-op if no .devN
#
# Prints "FROM → TO" on a real change, "no-op: VERSION" otherwise.
# Exits 0 in both cases so callers can run it idempotently.
set -euo pipefail

INIT_FILE="src/brew_hop_search/__init__.py"
PYPROJECT="pyproject.toml"

MODE="patch"
case "${1:-}" in
    --dev) MODE="dev" ;;
    --release) MODE="release" ;;
    "") MODE="patch" ;;
    *) echo "Usage: $0 [--dev|--release]" >&2; exit 2 ;;
esac

current=$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$INIT_FILE")
if [ -z "$current" ]; then
    echo "Could not find __version__ in $INIT_FILE" >&2
    exit 1
fi

# Split into base (X.Y.Z) and optional .devN suffix.
if [[ "$current" =~ ^([0-9]+\.[0-9]+\.[0-9]+)(\.dev[0-9]+)?$ ]]; then
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
        new_version="$major.$minor.$((patch + 1)).dev0"
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

# sed on macOS needs '' after -i; use a tmp file for portability-free syntax.
python3 - "$INIT_FILE" "$PYPROJECT" "$current" "$new_version" <<'PY'
import sys, pathlib, re
init_file, pyproject, old, new = sys.argv[1:]
for path, pat, tmpl in [
    (init_file, r'^__version__ = "' + re.escape(old) + r'"', f'__version__ = "{new}"'),
    (pyproject, r'^version = "' + re.escape(old) + r'"',     f'version = "{new}"'),
]:
    p = pathlib.Path(path)
    txt = p.read_text()
    new_txt = re.sub(pat, tmpl, txt, count=1, flags=re.MULTILINE)
    if new_txt == txt:
        sys.stderr.write(f"warning: no match for {old} in {path}\n")
    p.write_text(new_txt)
PY

echo "$current → $new_version"
