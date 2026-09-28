# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The `# [cache]` reminder line: age, time left, witness state, [--refresh].

Printed to stderr after results (TTY by default, always at -v, never at
-q), and mirrored into the JSON envelope as `meta.cache`. See
docs/specs/features/cache-flow.md § "Reminder line".
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.snap import expect  # noqa: F401
from tests.test_output import _seed_db


def _strip(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _run(db_path: Path, *args: str, env_extra: dict | None = None):
    r = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", *args],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "BREW_HOP_SEARCH_DB": str(db_path), **(env_extra or {})},
    )
    return _strip(r.stdout), _strip(r.stderr)


@pytest.fixture
def testdb(tmp_path):
    p = tmp_path / "t.db"
    _seed_db(p)
    return p


def _seed_installed(db_path: Path) -> None:
    """The shared seed leaves installed_* empty, and sqlite_utils never
    creates an empty table — so give it one row for the collapse tests."""
    import sqlite_utils
    db = sqlite_utils.Database(db_path)
    db["installed_formula"].insert({"name": "gh", "desc": "", "raw": "{}"}, pk="name")


# ── pure renderer ──────────────────────────────────────────────────────────

def test_render_one_fresh_source():
    from brew_hop_search.display import render_cache_line
    line = render_cache_line([
        {"label": "index", "age": 7200, "ttl": 21600, "changed": False}])
    expect(line, "# [cache] index 2h old, 4h left  [--refresh]\n")


def test_render_two_sources_one_changed():
    from brew_hop_search.display import render_cache_line
    line = render_cache_line([
        {"label": "installed", "age": 720, "ttl": 3600, "changed": True},
        {"label": "taps", "age": 30, "ttl": 3600, "changed": False},
    ])
    expect(line, "# [cache] installed 12m old, 48m left, changed · "
                 "taps <1m old, 59m left  [--refresh]\n")


def test_render_stale_source():
    from brew_hop_search.display import render_cache_line
    line = render_cache_line([
        {"label": "local", "age": 90000, "ttl": 3600, "changed": False}])
    expect(line, "# [cache] local 1d1h old, stale  [--refresh]\n")


def test_render_sub_minute_left_shows_seconds():
    from brew_hop_search.display import render_cache_line
    line = render_cache_line([
        {"label": "index", "age": 21570, "ttl": 21600, "changed": False}])
    expect(line, "# [cache] index 5h59m old, 30s left  [--refresh]\n")


def test_render_nothing_for_no_entries():
    from brew_hop_search.display import render_cache_line
    assert render_cache_line([]) == ""


# ── policy ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("verbose,tty,want", [
    (0, True, False),   # -q: never
    (0, False, False),
    (1, True, True),    # default: TTY only
    (1, False, False),
    (2, False, True),   # -v and up: always
    (3, False, True),
])
def test_should_emit_cache_line(verbose, tty, want):
    from brew_hop_search.display import should_emit_cache_line
    assert should_emit_cache_line(verbose, tty=tty) is want


# ── collapsing tables → sources ────────────────────────────────────────────

def test_cache_entries_collapse_tables_to_sources(testdb, monkeypatch):
    from brew_hop_search.cli import cache_entries
    from brew_hop_search.cache import get_db
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(testdb))
    _seed_installed(testdb)
    entries = cache_entries(get_db(), ["formula", "cask", "installed_formula",
                                       "installed_cask"])
    assert [e["label"] for e in entries] == ["index", "installed"]
    idx, inst = entries
    assert 3600 <= idx["age"] < 3700 and idx["ttl"] == 6 * 3600
    assert 60 <= inst["age"] < 160 and inst["ttl"] == 3600
    assert idx["changed"] is False and inst["changed"] is False


def test_cache_entries_skip_missing_tables(testdb, monkeypatch):
    from brew_hop_search.cli import cache_entries
    from brew_hop_search.cache import get_db
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(testdb))
    assert cache_entries(get_db(), ["tap", "local_formula"]) == []


def test_cache_entries_report_moved_witness(testdb, tmp_path, monkeypatch):
    from brew_hop_search import witness
    from brew_hop_search.cli import cache_entries
    from brew_hop_search.cache import get_db
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(testdb))
    _seed_installed(testdb)
    opt = tmp_path / "opt"
    opt.mkdir()
    monkeypatch.setattr(witness, "witness_paths", lambda k: [opt])
    db = get_db()
    db["_meta"].update("installed_formula", {"witness": opt.stat().st_mtime - 10},
                       alter=True)
    (entries,) = cache_entries(db, ["installed_formula"])
    assert entries["changed"] is True


# ── end to end ─────────────────────────────────────────────────────────────

def test_default_non_tty_has_no_cache_line(testdb):
    out, err = _run(testdb, "python")
    assert "python@3.13" in out
    assert "# [cache]" not in err


def test_verbose_prints_cache_line_on_stderr(testdb):
    out, err = _run(testdb, "-v", "python", env_extra={"BREW_HOP_SEARCH_NO_TIMING": "1"})
    assert "python@3.13" in out
    assert "# [cache]" not in out
    cache_lines = [l.strip() for l in err.splitlines() if "# [cache]" in l]
    assert cache_lines == ["# [cache] index 1h old, 5h left  [--refresh]"]


def test_quiet_beats_verbose_for_cache_line(testdb):
    _, err = _run(testdb, "-q", "-v", "python")
    assert "# [cache]" not in err


def test_json_envelope_carries_cache_meta(testdb):
    out, _ = _run(testdb, "--json", "python")
    env = json.loads(out)
    cache = env["meta"]["cache"]
    assert list(cache) == ["index"]
    idx = cache["index"]
    assert set(idx) == {"age_s", "ttl_s", "stale", "changed"}
    assert 3600 <= idx["age_s"] < 3700 and idx["ttl_s"] == 21600
    assert idx["stale"] is False and idx["changed"] is False
