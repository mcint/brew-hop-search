# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Witness mtimes: cheap "did brew change anything?" detection.

Each offline source (installed, taps, local) names a few directories
whose mtime moves when brew mutates that source. The max mtime is
stamped into `_meta.witness` at index time; a later read compares the
live max against the stamp. See docs/specs/features/cache-flow.md
§ "Witness mtimes".
"""
from __future__ import annotations

import os
import time

import pytest


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "bhs.db"
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(db_path))
    return db_path


def _touch(p, when: float) -> None:
    p.mkdir(parents=True, exist_ok=True)
    os.utime(p, (when, when))


# ── path resolution (no subprocess) ────────────────────────────────────────

def test_witness_paths_come_from_env_roots(tmp_path, monkeypatch):
    """HOMEBREW_PREFIX / HOMEBREW_REPOSITORY / HOMEBREW_CACHE win; no `brew` call."""
    from brew_hop_search import witness
    prefix = tmp_path / "prefix"
    repo = tmp_path / "repo"
    cache = tmp_path / "cache"
    monkeypatch.setenv("HOMEBREW_PREFIX", str(prefix))
    monkeypatch.setenv("HOMEBREW_REPOSITORY", str(repo))
    monkeypatch.setenv("HOMEBREW_CACHE", str(cache))

    assert witness.witness_paths("installed") == [
        prefix / "opt", prefix / "Cellar", prefix / "Caskroom"]
    assert witness.witness_paths("local") == [
        cache / "api", cache / "api" / "formula", cache / "api" / "cask"]
    # taps: the Taps dir plus every user/tap dir and its FETCH_HEAD
    taps = repo / "Library" / "Taps"
    (taps / "u1" / "homebrew-a" / ".git").mkdir(parents=True)
    (taps / "u1" / "homebrew-a" / ".git" / "FETCH_HEAD").write_text("x")
    (taps / "u2" / "homebrew-b").mkdir(parents=True)
    assert witness.witness_paths("taps") == [
        taps,
        taps / "u1" / "homebrew-a",
        taps / "u1" / "homebrew-a" / ".git" / "FETCH_HEAD",
        taps / "u2" / "homebrew-b",
    ]


def test_witness_paths_unknown_kind_is_empty():
    from brew_hop_search import witness
    assert witness.witness_paths("index") == []
    assert witness.witness_paths("nope") == []


# ── mtime sampling ─────────────────────────────────────────────────────────

def test_witness_mtime_is_max_over_existing_paths(tmp_path, monkeypatch):
    from brew_hop_search import witness
    a, b, missing = tmp_path / "a", tmp_path / "b", tmp_path / "missing"
    _touch(a, 1_000)
    _touch(b, 2_000)
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [a, b, missing])
    assert witness.witness_mtime("installed") == 2_000
    _touch(a, 3_000)
    assert witness.witness_mtime("installed") == 3_000


def test_witness_mtime_none_when_nothing_exists(tmp_path, monkeypatch):
    from brew_hop_search import witness
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [tmp_path / "nope"])
    assert witness.witness_mtime("installed") is None


# ── stamp + compare through the DB ─────────────────────────────────────────

def _import(table: str, witness_val):
    from brew_hop_search.cache import get_db, import_to_db
    db = get_db()
    import_to_db(db, table, [{"name": "x", "raw": "{}"}], ["name", "raw"],
                 "name", ["name"], witness=witness_val)
    return db


def test_import_stamps_witness_into_meta(isolated_db):
    from brew_hop_search import witness
    db = _import("installed_formula", 1234.0)
    assert witness.stored_witness(db, "installed_formula") == 1234.0


def test_import_without_witness_leaves_null(isolated_db):
    from brew_hop_search import witness
    db = _import("installed_formula", None)
    assert witness.stored_witness(db, "installed_formula") is None


def test_changed_false_when_no_stamp(isolated_db, tmp_path, monkeypatch):
    """Pre-witness DBs (or sources with no roots) never thrash: unknown ≠ changed."""
    from brew_hop_search import witness
    _touch(tmp_path / "opt", 5_000)
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [tmp_path / "opt"])
    db = _import("installed_formula", None)
    assert witness.changed(db, "installed_formula") is False


def test_changed_tracks_live_mtime(isolated_db, tmp_path, monkeypatch):
    from brew_hop_search import witness
    opt = tmp_path / "opt"
    _touch(opt, 5_000)
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [opt])
    db = _import("installed_formula", witness.witness_mtime("installed"))
    assert witness.changed(db, "installed_formula") is False
    _touch(opt, 6_000)  # brew install/upgrade/remove relinks under opt/
    assert witness.changed(db, "installed_formula") is True


def test_changed_false_when_witness_vanishes(isolated_db, tmp_path, monkeypatch):
    from brew_hop_search import witness
    opt = tmp_path / "opt"
    _touch(opt, 5_000)
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [opt])
    db = _import("installed_formula", 5_000.0)
    opt.rmdir()
    assert witness.changed(db, "installed_formula") is False


def test_state_reports_all_fields(isolated_db, tmp_path, monkeypatch):
    from brew_hop_search import witness
    opt = tmp_path / "opt"
    _touch(opt, 5_000)
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [opt])
    db = _import("installed_formula", 4_000.0)
    st = witness.state(db, "installed_formula")
    assert st == {"kind": "installed", "stored": 4_000.0, "current": 5_000.0,
                  "changed": True, "paths": [str(opt)]}


def test_state_for_index_has_no_witness(isolated_db):
    from brew_hop_search import witness
    db = _import("formula", None)
    st = witness.state(db, "formula")
    assert st["kind"] is None
    assert st["changed"] is False
    assert st["paths"] == []


def test_schema_version_bumped_for_witness_column():
    from brew_hop_search.cache import SCHEMA_VERSION
    assert SCHEMA_VERSION >= 2
