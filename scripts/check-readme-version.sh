#!/usr/bin/env bash
# Refuse to build a release whose README.md names a different version.
#
#   scripts/check-readme-version.sh [README.md]
#
# Dev versions are not checked. Exit 1, with what the README says and how
# to fix it, when a release VERSION isn't the README's version line.
set -euo pipefail
README=${1:-README.md}
VF=${VERSION_FILE:-src/brew_hop_search/VERSION}
v=$(tr -d '[:space:]' < "$VF")
case "$v" in *-dev*) exit 0 ;; esac
want="brew-hop-search $v"
if grep -qxF "$want" "$README"; then
  exit 0
fi
have=$(awk '/^## Version/{f=1; next} f && /^brew-hop-search /{print; exit}' "$README")
echo "README.md version line is '${have#brew-hop-search }', but VERSION is $v." >&2
echo "Regenerate it before building: make readme (release.sh does this at Step 2.5)." >&2
exit 1
