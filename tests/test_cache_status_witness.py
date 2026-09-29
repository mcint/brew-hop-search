# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""`-C` shows each source's witness state; `-C -v` names it; `-vv` lists paths."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

import pytest
import sqlite_utils


def _strip(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


@pytest.fixture
def seeded(tmp_path):
    """A DB with `formula` (no witness) and `installed_formula` whose witness
    stamp predates the live `opt/` mtime — i.e. brew installed something."""
    prefix = tmp_path / "prefix"
    (prefix / "opt").mkdir(parents=True)
    now = time.time()
    os.utime(prefix / "opt", (now, now))

    db_path = tmp_path / "x.db"
    db = sqlite_utils.Database(db_path)
    for table, pk in (("formula", "name"), ("installed_formula", "name")):
        db[table].insert_all([{"name": "foo", "desc": "", "raw": "{}"}], pk=pk)
        db[table].enable_fts(["name", "desc"], tokenize="porter")
    db["_meta"].insert({"kind": "formula", "updated_at": now, "count": 1,
                        "witness": None}, pk="kind", replace=True, alter=True)
    db["_meta"].insert({"kind": "installed_formula", "updated_at": now, "count": 1,
                        "witness": now - 100}, pk="kind", replace=True, alter=True)
    env = {**os.environ, "BREW_HOP_SEARCH_DB": str(db_path),
           "HOMEBREW_PREFIX": str(prefix), "BREW_HOP_SEARCH_NO_TIMING": "1"}
    return env, prefix


def _run(env, *args):
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, env=env, timeout=30)
    return _strip(r.stdout)


def _row(out: str, label: str) -> str:
    rows = [l for l in out.splitlines() if l.strip().startswith(label)]
    assert len(rows) == 1, out
    return rows[0]


def test_default_marks_only_changed_sources(seeded):
    env, _ = seeded
    out = _run(env, "-C")
    assert "changed" in _row(out, "installed:f")
    assert "changed" not in _row(out, "formula")
    assert "witness" not in out


def test_verbose_names_witness_state(seeded):
    env, _ = seeded
    out = _run(env, "-C", "-v")
    assert "witness changed" in _row(out, "installed:f")
    assert "witness" not in _row(out, "formula")


def test_verbose_shows_ok_when_witness_still(seeded):
    env, prefix = seeded
    db = sqlite_utils.Database(env["BREW_HOP_SEARCH_DB"])
    db["_meta"].update("installed_formula",
                       {"witness": (prefix / "opt").stat().st_mtime})
    out = _run(env, "-C", "-v")
    assert "witness ok" in _row(out, "installed:f")


def test_verbose_shows_none_when_unstamped(seeded):
    env, _ = seeded
    db = sqlite_utils.Database(env["BREW_HOP_SEARCH_DB"])
    db["_meta"].update("installed_formula", {"witness": None})
    out = _run(env, "-C", "-v")
    assert "witness none" in _row(out, "installed:f")
    assert "changed" not in _row(out, "installed:f")


def test_double_verbose_lists_witness_paths(seeded):
    env, prefix = seeded
    out = _run(env, "-C", "-vv")
    path_lines = [l for l in out.splitlines() if "witness:" in l]
    assert len(path_lines) == 1
    assert str(prefix / "opt") in path_lines[0]
    assert str(prefix / "Caskroom") in path_lines[0]


def test_json_carries_witness_block(seeded):
    env, prefix = seeded
    data = json.loads(_run(env, "-C", "--json"))
    inst = data["sources"]["installed_formula"]["witness"]
    assert inst["changed"] is True
    assert inst["stored"] < inst["current"]
    assert str(prefix / "opt") in inst["paths"]
    assert "witness" not in data["sources"]["formula"]
