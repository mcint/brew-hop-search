# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Installed versions: what -i indexes and what -O compares.

Regressions from real data (2026-11-18): `-i flux` printed 2.10.0 (the
available version) while 2.9.5 was installed; `-O` reported the tap
formula fluxcd/tap/flux as "2.9.5 → 0.201.0" by matching homebrew/core's
unrelated `flux`; a stale index made fresh upgrades look outdated.
Spec: docs/specs/features/outdated.md § Comparison Logic, SCHEMA.md.
"""
from __future__ import annotations

import json

import pytest

from brew_hop_search.outdated import version_newer
from brew_hop_search.sources.installed import cask_row, formula_row


# ── what -i indexes ────────────────────────────────────────────────────────

def test_formula_row_version_is_installed_not_available():
    item = {"name": "flux", "desc": "", "homepage": "",
            "versions": {"stable": "2.10.0"}, "linked_keg": "2.9.5",
            "installed": [{"version": "2.9.5"}]}
    assert formula_row(item)["version"] == "2.9.5"


def test_formula_row_unlinked_uses_last_installed():
    item = {"name": "x", "versions": {"stable": "3"}, "linked_keg": None,
            "installed": [{"version": "1"}, {"version": "2"}]}
    assert formula_row(item)["version"] == "2"


def test_formula_row_nothing_installed_is_empty():
    item = {"name": "x", "versions": {"stable": "3"}, "installed": []}
    assert formula_row(item)["version"] == ""


def test_cask_row_version_is_installed_not_available():
    item = {"token": "alfred", "name": ["Alfred"], "desc": "", "homepage": "",
            "version": "6.0,3219", "installed": "5.8,2348"}
    assert cask_row(item)["version"] == "5.8,2348"


# ── version ordering ───────────────────────────────────────────────────────

@pytest.mark.parametrize("a,b", [
    ("21.7.0", "21.6.1"),
    ("1.24.5_1", "1.24.5"),
    ("2.10.0", "2.9.5"),
    ("1.0", "1.0rc1"),
    ("5.8.1,2349", "5.8,2348"),
    ("20261106", "20260426"),
])
def test_version_newer(a, b):
    assert version_newer(a, b)
    assert not version_newer(b, a)


def test_version_newer_equal_is_false():
    assert not version_newer("1.2.3", "1.2.3")


# ── what -O compares ───────────────────────────────────────────────────────

API = [
    {"name": "flux", "versions": {"stable": "0.201.0"}, "revision": 0},
    {"name": "jet", "versions": {"stable": "2.16.1"}, "revision": 0},
    {"name": "node", "versions": {"stable": "21.6.1"}, "revision": 0},
    {"name": "wget", "versions": {"stable": "1.24.5"}, "revision": 1},
]

INSTALLED = [
    # tap formula, outdated against its own tap
    {"name": "flux", "full_name": "fluxcd/tap/flux", "tap": "fluxcd/tap",
     "versions": {"stable": "2.10.0"}, "revision": 0,
     "linked_keg": "2.9.5", "installed": [{"version": "2.9.5"}]},
    # tap formula, current against its own tap (core jet is unrelated)
    {"name": "jet", "full_name": "borkdude/brew/jet", "tap": "borkdude/brew",
     "versions": {"stable": "0.7.27"}, "revision": 0,
     "linked_keg": "0.7.27", "installed": [{"version": "0.7.27"}]},
    # core formula upgraded past a stale index
    {"name": "node", "full_name": "node", "tap": "homebrew/core",
     "versions": {"stable": "21.7.0"}, "revision": 0,
     "linked_keg": "21.7.0", "installed": [{"version": "21.7.0"}]},
    # core formula behind on revision
    {"name": "wget", "full_name": "wget", "tap": "homebrew/core",
     "versions": {"stable": "1.24.5"}, "revision": 1,
     "linked_keg": "1.24.5", "installed": [{"version": "1.24.5"}]},
    # HEAD install: brew outdated skips these unless --fetch-HEAD
    {"name": "rlwrap", "full_name": "rlwrap", "tap": "homebrew/core",
     "versions": {"stable": "0.48"}, "revision": 0,
     "linked_keg": "HEAD-f14865f", "installed": [{"version": "HEAD-f14865f"}]},
]

API.append({"name": "rlwrap", "versions": {"stable": "0.48"}, "revision": 0})

INSTALLED_CASKS = [
    {"token": "alfred", "full_token": "alfred", "tap": "homebrew/cask",
     "name": ["Alfred"], "desc": "Launcher", "homepage": "",
     "version": "6.0,3219", "installed": "5.8,2348"},
    # tap cask, not in the API index
    {"token": "ntm", "full_token": "dicklesworthstone/tap/ntm",
     "tap": "dicklesworthstone/tap", "name": ["ntm"], "desc": "", "homepage": "",
     "version": "1.38.0", "installed": "1.33.1"},
]


@pytest.fixture
def tapdb(tmp_path, monkeypatch):
    import time
    import sqlite_utils
    from brew_hop_search.sources.installed import cask_row, formula_row
    path = tmp_path / "tap.db"
    db = sqlite_utils.Database(path)
    db["formula"].insert_all(
        [{"name": f["name"], "raw": json.dumps(f)} for f in API], pk="name")
    db["installed_formula"].insert_all(
        [formula_row(f) for f in INSTALLED], pk="name")
    db["installed_formula"].enable_fts(["name", "desc"], create_triggers=True)
    db["installed_cask"].insert_all(
        [cask_row(c) for c in INSTALLED_CASKS], pk="token")
    db["installed_cask"].enable_fts(["token", "name", "desc"], create_triggers=True)
    for kind in ("formula", "installed_formula", "installed_cask"):
        db["_meta"].insert({"kind": kind, "updated_at": time.time() - 60,
                            "count": 1}, pk="kind", replace=True)
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(path))
    return path


def _cli(*args: str) -> str:
    import os, re, subprocess, sys
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, timeout=60,
                       env=os.environ.copy())
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout)


# ── what -i shows ──────────────────────────────────────────────────────────

def test_installed_search_shows_installed_version(tapdb):
    out = _cli("-i", "flux")
    assert "2.9.5" in out and "2.10.0" not in out


def test_installed_search_grep_shows_installed_version(tapdb):
    assert _cli("-i", "-g", "flux").splitlines()[0].split("\t")[1] == "2.9.5"


def test_installed_search_csv_shows_installed_version(tapdb):
    assert 'c,alfred,"5.8,2348",Launcher,' in _cli("-i", "--csv", "alfred")


def test_installed_search_json_carries_installed_version(tapdb):
    doc = json.loads(_cli("-i", "--json", "flux"))
    text = json.dumps(doc)
    assert '"installed_version": "2.9.5"' in text


def _outdated_formulae():
    from brew_hop_search.outdated import collect_outdated_fast
    return {e["name"]: (e["installed_versions"][0], e["current_version"])
            for e in collect_outdated_fast()["formulae"]}


def test_outdated_tap_formula_uses_full_name_and_own_version(tapdb):
    got = _outdated_formulae()
    assert got.get("fluxcd/tap/flux") == ("2.9.5", "2.10.0")
    assert "flux" not in got


def test_outdated_tap_formula_current_is_not_outdated(tapdb):
    got = _outdated_formulae()
    assert "jet" not in got and "borkdude/brew/jet" not in got


def test_outdated_stale_index_is_not_outdated(tapdb):
    assert "node" not in _outdated_formulae()


def test_outdated_tap_cask_uses_own_version_and_short_token(tapdb):
    # brew outdated --json=v2 names tap casks by short token (observed
    # 2026-11-18: "ntm", not "dicklesworthstone/tap/ntm"), unlike formulae.
    from brew_hop_search.outdated import collect_outdated_fast
    got = {e["name"]: (e["installed_versions"][0], e["current_version"])
           for e in collect_outdated_fast()["casks"]}
    assert got.get("ntm") == ("1.33.1", "1.38.0")


def test_outdated_skips_head_installs(tapdb):
    assert "rlwrap" not in _outdated_formulae()


def test_outdated_revision_bump_still_outdated(tapdb):
    assert _outdated_formulae().get("wget") == ("1.24.5", "1.24.5_1")
