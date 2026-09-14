# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for the cli-vocabulary Option A changes (docs/specs/drafts/cli-vocabulary.md).

Covers the grammar fixes that make every flag sit in exactly one cell of
the sources × verbs × adverbs cartesian:

- `-L` → `-l` (lowercase = source), `-L` kept as a hidden alias for one
  release with a stderr hint;
- `--offline` as a distinct adverb (no network, no bg refresh), which
  conflicts with `--refresh`;
- `--stale` honored by every source, with a `KIND:DUR[,KIND:DUR]`
  selector form;
- `--cached` aggregate selector = installed + taps + local (locations.md).

Dispatch is verified by recording each source's `ensure_cache` call, the
same technique as tests/test_refresh_dispatch.py.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest


def _patch_sources(monkeypatch):
    """Record every ensure_cache call as its kwargs (force, stale, ...)."""
    calls: dict[str, list[dict]] = {
        "api_formula": [], "api_cask": [],
        "installed": [], "taps": [], "local": [],
    }

    def fake_api(kind, url, force=False, stale=None, fresh=None, **kw):
        calls[f"api_{kind}"].append({"force": bool(force), "stale": stale, "fresh": fresh})
        return True

    def fake_installed(force=False, stale=None, **kw):
        calls["installed"].append({"force": bool(force), "stale": stale, **kw})
        return True

    def fake_taps(force=False, stale=None, **kw):
        calls["taps"].append({"force": bool(force), "stale": stale, **kw})
        return True

    def fake_local(force=False, stale=None, **kw):
        calls["local"].append({"force": bool(force), "stale": stale, **kw})
        return True

    monkeypatch.setattr("brew_hop_search.sources.api.ensure_cache", fake_api)
    monkeypatch.setattr("brew_hop_search.sources.installed.ensure_cache", fake_installed)
    monkeypatch.setattr("brew_hop_search.sources.taps.ensure_cache", fake_taps)
    monkeypatch.setattr("brew_hop_search.sources.local.ensure_cache", fake_local)
    monkeypatch.setattr("brew_hop_search.search.search", lambda *a, **kw: [])
    return calls


def _main(monkeypatch, tmp_path, argv):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "db.sqlite"))
    calls = _patch_sources(monkeypatch)
    from brew_hop_search.cli import main
    code = 0
    try:
        main(argv)
    except SystemExit as e:
        code = int(e.code or 0)
    return calls, code


def _run(*args, env=None):
    import os
    r = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", *args],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, **(env or {})},
    )
    strip = lambda s: re.sub(r"\033\[[0-9;]*m", "", s)
    return strip(r.stdout), strip(r.stderr), r.returncode


# ── -L → -l ────────────────────────────────────────────────────────────────

def test_lowercase_l_selects_local_source(monkeypatch, tmp_path):
    calls, _ = _main(monkeypatch, tmp_path, ["-l", "foo"])
    assert len(calls["local"]) == 1
    assert calls["api_formula"] == [] and calls["installed"] == []


def test_uppercase_L_still_works_as_alias(monkeypatch, tmp_path, capsys):
    calls, _ = _main(monkeypatch, tmp_path, ["-L", "foo"])
    assert len(calls["local"]) == 1
    err = capsys.readouterr().err
    assert "-L" in err and "-l" in err, "expect a one-line rename hint on stderr"


def test_lowercase_l_emits_no_hint(monkeypatch, tmp_path, capsys):
    _main(monkeypatch, tmp_path, ["-l", "foo"])
    assert "-L" not in capsys.readouterr().err


def test_uppercase_L_hint_silenced_by_quiet(monkeypatch, tmp_path, capsys):
    _main(monkeypatch, tmp_path, ["-L", "-q", "foo"])
    assert capsys.readouterr().err == ""


def test_help_lists_l_not_L():
    out, _, _ = _run("--help")
    assert "-l, --local" in out
    assert "-L" not in out


def test_combined_short_flags_with_l(monkeypatch, tmp_path):
    """`-itl` is the spelled-out all-cached stack; must parse."""
    calls, _ = _main(monkeypatch, tmp_path, ["-itl", "foo"])
    assert len(calls["installed"]) == len(calls["taps"]) == len(calls["local"]) == 1
