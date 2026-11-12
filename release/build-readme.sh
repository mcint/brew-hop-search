#!/usr/bin/env bash
# Generate README.md from README.md.template + live command output.
# Run: ./scripts/build-readme.sh > README.md
#   or: make readme
set -euo pipefail

TEMPLATE="README.md.template"
BHS="uv run brew-hop-search"

if [ ! -f "$TEMPLATE" ]; then
    echo "Missing $TEMPLATE" >&2
    exit 1
fi

# ── Capture live outputs (strip ANSI) ────────────────────────
strip_ansi() { sed $'s/\033\\[[0-9;]*m//g'; }

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

$BHS python -n 5 2>&1      | strip_ansi > "$tmpdir/DEFAULT_OUTPUT"
$BHS -v python -n 5 2>&1   | strip_ansi > "$tmpdir/VERBOSE_OUTPUT"
$BHS -q python -n 3 2>&1   | strip_ansi > "$tmpdir/QUIET_OUTPUT"
$BHS --csv python -n 3 2>&1| strip_ansi > "$tmpdir/CSV_OUTPUT"
$BHS --table python -n 5 2>&1 | strip_ansi > "$tmpdir/TABLE_OUTPUT"
$BHS -C 2>&1               | strip_ansi > "$tmpdir/CACHE_OUTPUT"
$BHS --help 2>&1            | strip_ansi > "$tmpdir/HELP_OUTPUT"
$BHS -V 2>&1               | strip_ansi > "$tmpdir/VERSION_OUTPUT"

# ── Substitute placeholders ──────────────────────────────────
# Each {{PLACEHOLDER}} must appear alone on its line in the template.
# Replace the placeholder line with the contents of the corresponding file.

while IFS= read -r line; do
    if [[ "$line" =~ \{\{([A-Z_]+)\}\} ]]; then
        key="${BASH_REMATCH[1]}"
        file="$tmpdir/$key"
        if [ -f "$file" ]; then
            cat "$file"
        else
            echo "$line"
        fi
    else
        echo "$line"
    fi
done < "$TEMPLATE"
