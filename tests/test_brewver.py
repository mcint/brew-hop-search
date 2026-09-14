# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for the brew-version gate (brewver.py).

Features that only exist on newer brew (tap trust JSON, `brew vulns`,
`brew doctor --json`, ...) must be skipped *visibly* on older installs
rather than failing or silently doing nothing. This module covers the
version parse, the env override, the sqlite cache, and the skip registry.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from brew_hop_search import brewver


# ── parsing ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Homebrew 7.0.1-3-g67f689a\nHomebrew/homebrew-cask (git revision 968111a6f05; last commit 2026-06-09)\n",
     (7, 0, 1)),
    ("Homebrew 6.1.0\n", (6, 1, 0)),
    ("Homebrew 4.6.15-108-gb7ea5c5\n", (4, 6, 15)),
    ("Homebrew >=7.0.0 (shallow or no git repository)\n", (7, 0, 0)),
])
def test_parse_brew_version(text, expected):
    assert brewver.parse_brew_version(text) == expected


@pytest.mark.parametrize("text", ["", "brew: command not found", "Homebrew"])
def test_parse_brew_version_garbage_is_none(text):
    assert brewver.parse_brew_version(text) is None


def test_format_version():
    assert brewver.format_version((7, 0, 1)) == "7.0.1"
    assert brewver.format_version(None) == "unknown"


# ── resolution: env override beats subprocess ──────────────────────────────

def test_env_override_short_circuits_subprocess(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "6.1.0")

    def _boom(*a, **kw):
        raise AssertionError("subprocess must not run under env override")
    monkeypatch.setattr(subprocess, "run", _boom)

    assert brewver.brew_version() == (6, 1, 0)


def test_env_override_garbage_falls_through_to_unknown(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "banana")

    def _no_brew(*a, **kw):
        raise OSError("simulated: no brew on PATH")
    monkeypatch.setattr(subprocess, "run", _no_brew)

    assert brewver.brew_version() is None


# ── resolution: sqlite cache ───────────────────────────────────────────────

def test_version_is_cached_in_meta(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.delenv("BREW_HOP_SEARCH_BREW_VERSION", raising=False)
    calls = []

    class _R:
        returncode = 0
        stdout = "Homebrew 7.0.1-3-g67f689a\n"
        stderr = ""

    def _fake_run(*a, **kw):
        calls.append(a)
        return _R()
    monkeypatch.setattr(subprocess, "run", _fake_run)

    assert brewver.brew_version() == (7, 0, 1)
    assert brewver.brew_version() == (7, 0, 1)
    assert len(calls) == 1, "second call must be served from _meta cache"


def test_force_refresh_reruns_brew(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.delenv("BREW_HOP_SEARCH_BREW_VERSION", raising=False)
    outputs = iter(["Homebrew 6.1.0\n", "Homebrew 7.0.0\n"])

    class _R:
        returncode = 0
        stderr = ""
        def __init__(self):
            self.stdout = next(outputs)

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _R())
    assert brewver.brew_version() == (6, 1, 0)
    assert brewver.brew_version(force=True) == (7, 0, 0)
    assert brewver.brew_version() == (7, 0, 0)


# ── feature gate + skip registry ───────────────────────────────────────────

def test_supports_and_skip_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("BREW_HOP_SEARCH_BREW_VERSION", "6.1.0")
    brewver.reset_skipped()

    assert brewver.supports("tap-info-trusted") is True   # 6.0.0+
    assert brewver.supports("vulns") is False              # 7.0.0+
    assert brewver.supports("doctor-json") is False

    skipped = brewver.skipped()
    assert [s.feature for s in skipped] == ["vulns", "doctor-json"]
    assert skipped[0].needs == (7, 0, 0)
    assert skipped[0].have == (6, 1, 0)

    lines = brewver.skipped_report()
    assert len(lines) == 2
    assert "vulns" in lines[0] and "7.0.0" in lines[0] and "6.1.0" in lines[0]


def test_supports_unknown_feature_is_a_programming_error():
    with pytest.raises(KeyError):
        brewver.supports("not-a-feature")


def test_supports_unknown_brew_version_skips(monkeypatch, tmp_path):
    """No brew at all → every gated feature is skipped, reason says unknown."""
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    monkeypatch.delenv("BREW_HOP_SEARCH_BREW_VERSION", raising=False)
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("no brew")))
    brewver.reset_skipped()
    assert brewver.supports("tap-info-trusted") is False
    assert "unknown" in brewver.skipped_report()[0]


# ── CLI surface: -C shows the brew version ─────────────────────────────────

def test_cache_status_shows_brew_version(tmp_path):
    import os as _os
    env = {**_os.environ,
           "BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_BREW_VERSION": "6.1.0"}
    r = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "-C"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    out = re.sub(r"\033\[[0-9;]*m", "", r.stdout)
    assert "brew  6.1.0" in out


def test_cache_status_verbose_lists_gated_features(tmp_path):
    import os as _os
    env = {**_os.environ,
           "BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_BREW_VERSION": "6.1.0"}
    r = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "-C", "-v"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    out = re.sub(r"\033\[[0-9;]*m", "", r.stdout)
    assert "vulns" in out and "needs 7.0.0" in out
    assert "tap-info-trusted" in out


def test_cache_status_json_carries_brew_block(tmp_path):
    import json, os as _os
    env = {**_os.environ,
           "BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_BREW_VERSION": "7.0.1"}
    r = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "-C", "--json"],
        capture_output=True, text=True, env=env, timeout=10,
    )
    data = json.loads(r.stdout)
    assert data["brew"]["version"] == "7.0.1"
    assert data["brew"]["features"]["vulns"] is True
