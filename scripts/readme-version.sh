#!/usr/bin/env bash
# The line README.md shows under "## Version".
#
# A release VERSION (no -dev) prints exactly `brew-hop-search <VERSION>`:
# the README documents the release, not the git state it was built from.
# Before the tag exists, -V reports commits since the previous tag, which is
# how v0.3.8 shipped "0.3.7 (dev+3: …+dirty)". Dev versions print live -V.
#
# Env: VERSION_FILE (default src/brew_hop_search/VERSION), BHS (the command).
set -euo pipefail
VF=${VERSION_FILE:-src/brew_hop_search/VERSION}
v=$(tr -d '[:space:]' < "$VF")
case "$v" in
  *-dev*) ${BHS:-uv run brew-hop-search} -V 2>&1 ;;
  *)      echo "brew-hop-search $v" ;;
esac
