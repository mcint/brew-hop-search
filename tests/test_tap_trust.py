# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tap trust metadata from `brew tap-info --installed --json=v1` (brew ≥ 6.0).

Since Homebrew 6.0 a third-party tap must be trusted before its Ruby is
evaluated, and tap-info reports `trusted` / `official` per tap. We fold
that onto each tap row at refresh time so `-t -v` can show it, and skip
the whole step visibly on older brews via the brewver gate.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from brew_hop_search import brewver
from brew_hop_search.sources import taps

_TAP_INFO = [
    {"name": "anomalyco/tap", "official": False, "trusted": False,
     "remote": "https://github.com/anomalyco/homebrew-tap",
     "HEAD": "307a17a", "branch": "master", "last_commit": "2 days ago",
     "path": "/opt/homebrew/Library/Taps/anomalyco/homebrew-tap"},
    {"name": "homebrew/services", "official": True, "trusted": True,
     "remote": "https://github.com/Homebrew/homebrew-services",
     "HEAD": "abc", "branch": "master", "last_commit": "3 weeks ago",
     "path": "/opt/homebrew/Library/Taps/homebrew/homebrew-services"},
    {"name": "steipete/tap", "official": False, "trusted": True,
     "remote": "https://github.com/steipete/homebrew-tap",
     "HEAD": "def", "branch": "main", "last_commit": "5 hours ago",
     "path": "/opt/homebrew/Library/Taps/steipete/homebrew-tap"},
]


def test_tap_meta_from_json_keys_by_tap_name():
    meta = taps._tap_meta_from_json(_TAP_INFO)
    assert set(meta) == {"anomalyco/tap", "homebrew/services", "steipete/tap"}
    assert meta["anomalyco/tap"]["trusted"] is False
    assert meta["homebrew/services"]["official"] is True
    assert meta["steipete/tap"]["remote"].endswith("homebrew-tap")


def test_annotate_trust_folds_meta_onto_rows():
    rows = [{"tap": "anomalyco/tap", "name": "opencode"},
            {"tap": "steipete/tap", "name": "goplaces"},
            {"tap": "nobody/unknown", "name": "x"}]
    meta = taps._tap_meta_from_json(_TAP_INFO)
    taps._annotate_trust(rows, meta)
    assert rows[0]["trusted"] == 0 and rows[0]["official"] == 0
    assert rows[1]["trusted"] == 1 and rows[1]["official"] == 0
    # Not in tap-info (tap removed between scan and query): unknown → None
    assert rows[2]["trusted"] is None and rows[2]["official"] is None


def test_fetch_tap_meta_gated_on_old_brew(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "5.2.0")
    brewver.reset_skipped()

    def _boom(*a, **kw):
        raise AssertionError("tap-info must not run on brew < 6.0")
    monkeypatch.setattr(subprocess, "run", _boom)

    assert taps.fetch_tap_meta() == {}
    assert any("tap-info-trusted" in s for s in brewver.skipped_report())


def test_fetch_tap_meta_runs_tap_info_on_new_brew(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "7.0.1")
    brewver.reset_skipped()
    seen = []

    class _R:
        returncode = 0
        stdout = json.dumps(_TAP_INFO)
        stderr = ""

    def _fake(cmd, *a, **kw):
        seen.append(cmd)
        return _R()
    monkeypatch.setattr(subprocess, "run", _fake)

    meta = taps.fetch_tap_meta()
    assert seen and seen[0][:2] == ["brew", "tap-info"]
    assert "--installed" in seen[0] and "--json=v1" in seen[0]
    assert meta["anomalyco/tap"]["trusted"] is False
    assert brewver.skipped_report() == []


def test_fetch_tap_meta_failure_is_empty_not_fatal(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "7.0.1")

    class _R:
        returncode = 1
        stdout = ""
        stderr = "Error: something"
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert taps.fetch_tap_meta() == {}


def test_refresh_writes_trust_columns(monkeypatch, tmp_path):
    """End to end: scan rows + tap-info → `tap` table has trusted/official."""
    import sqlite_utils
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "7.0.1")
    monkeypatch.setattr(taps, "scan_taps", lambda: [
        {"name": "opencode", "tap": "anomalyco/tap", "kind": "formula", "desc": "",
         "homepage": "", "version": "1", "url": "", "added_at": 0.0, "modified_at": 0.0},
        {"name": "goplaces", "tap": "steipete/tap", "kind": "formula", "desc": "",
         "homepage": "", "version": "1", "url": "", "added_at": 0.0, "modified_at": 0.0},
    ])
    monkeypatch.setattr(taps, "fetch_tap_meta",
                        lambda: taps._tap_meta_from_json(_TAP_INFO))
    assert taps.refresh(silent=True) is True
    db = sqlite_utils.Database(tmp_path / "x.db")
    rows = {r["name"]: r for r in db["tap"].rows}
    assert rows["opencode"]["trusted"] == 0
    assert rows["goplaces"]["trusted"] == 1
    assert rows["goplaces"]["official"] == 0


def test_fmt_tap_formula_shows_trust_when_asked():
    from brew_hop_search.display import fmt_tap_formula
    import re
    strip = lambda s: re.sub(r"\033\[[0-9;]*m", "", s)
    untrusted = {"name": "opencode", "tap": "anomalyco/tap", "trusted": 0, "official": 0}
    trusted = {"name": "goplaces", "tap": "steipete/tap", "trusted": 1, "official": 0}
    official = {"name": "svc", "tap": "homebrew/services", "trusted": 1, "official": 1}
    unknown = {"name": "x", "tap": "nobody/unknown"}
    assert "untrusted" in strip(fmt_tap_formula(untrusted, show_trust=True))
    assert "trusted" in strip(fmt_tap_formula(trusted, show_trust=True))
    assert "untrusted" not in strip(fmt_tap_formula(trusted, show_trust=True))
    assert "official" in strip(fmt_tap_formula(official, show_trust=True))
    assert "trust" not in strip(fmt_tap_formula(unknown, show_trust=True))
    # Default view stays as it was.
    assert "trust" not in strip(fmt_tap_formula(untrusted))
