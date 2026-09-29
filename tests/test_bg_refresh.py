# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Background refresh for every offline source, and witness → stale.

Before this, only `installed` (and the API index) refreshed in the
background; `taps` and `local` blocked the foreground when stale. Now all
three share one detached runner (`sources/_bg.py`), and a moved witness
mtime (see witness.py) counts as stale exactly like an expired TTL — and
takes the same *non-blocking* path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "bhs.db"
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(db_path))
    monkeypatch.setattr("brew_hop_search.sources.taps.fetch_tap_meta", lambda: {})
    return db_path


@pytest.fixture
def taps_root(tmp_path, monkeypatch):
    root = tmp_path / "Taps"
    rb = root / "u1" / "homebrew-foo" / "bar.rb"
    rb.parent.mkdir(parents=True)
    rb.write_text('class Bar < Formula\n  desc "A bar"\n  version "1.0"\nend\n')
    monkeypatch.setattr("brew_hop_search.sources.taps._taps_dir", lambda: root)
    return root


@pytest.fixture
def local_api(tmp_path, monkeypatch):
    api = tmp_path / "Homebrew" / "api"
    (api / "formula").mkdir(parents=True)
    (api / "cask").mkdir(parents=True)
    (api / "formula" / "bar.json").write_text(json.dumps(
        {"name": "bar", "desc": "A bar", "homepage": "", "versions": {"stable": "1.0"}}))
    monkeypatch.setenv("HOMEBREW_CACHE", str(tmp_path / "Homebrew"))
    return api


class _Recorder:
    def __init__(self):
        self.calls: list = []

    def __call__(self, *a, **kw):
        self.calls.append((a, kw))


def _age_meta(kind: str, seconds: float) -> None:
    """Backdate a `_meta` row so the TTL path sees it as stale."""
    from brew_hop_search.cache import get_db
    db = get_db()
    db["_meta"].update(kind, {"updated_at": time.time() - seconds})


# ── env roots (no subprocess when the env says where things are) ──────────

def test_taps_dir_honors_homebrew_repository(tmp_path, monkeypatch):
    from brew_hop_search.sources import taps
    monkeypatch.setenv("HOMEBREW_REPOSITORY", str(tmp_path))
    assert taps._taps_dir() == tmp_path / "Library" / "Taps"


def test_local_api_dir_honors_homebrew_cache(tmp_path, monkeypatch):
    from brew_hop_search.sources import local
    monkeypatch.setenv("HOMEBREW_CACHE", str(tmp_path))
    assert local._brew_cache_api() == tmp_path / "api"


# ── refresh stamps the witness ─────────────────────────────────────────────

def test_taps_refresh_stamps_witness(taps_root, isolated_db, monkeypatch):
    from brew_hop_search import witness
    from brew_hop_search.sources import taps
    from brew_hop_search.cache import get_db
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [taps_root])
    assert taps.refresh(silent=True)
    assert witness.stored_witness(get_db(), "tap") == taps_root.stat().st_mtime


def test_local_refresh_stamps_witness(local_api, isolated_db):
    from brew_hop_search import witness
    from brew_hop_search.sources import local
    from brew_hop_search.cache import get_db
    assert local.refresh(silent=True)
    db = get_db()
    expected = max(p.stat().st_mtime for p in (local_api, local_api / "formula",
                                               local_api / "cask"))
    assert witness.stored_witness(db, "local_formula") == expected
    assert witness.stored_witness(db, "local_cask") == expected


# ── ensure_cache: stale → background, never blocking ──────────────────────

@pytest.mark.parametrize("kind", ["taps", "local"])
def test_stale_ttl_goes_to_background(kind, taps_root, local_api, isolated_db,
                                      monkeypatch):
    from brew_hop_search.sources import taps, local
    mod = {"taps": taps, "local": local}[kind]
    table = {"taps": "tap", "local": "local_formula"}[kind]
    assert mod.refresh(silent=True)
    _age_meta(table, 10_000)

    bg, sync = _Recorder(), _Recorder()
    monkeypatch.setattr(mod, "background_refresh", bg)
    monkeypatch.setattr(mod, "refresh", sync)
    assert mod.ensure_cache(stale=3600) is True
    assert len(bg.calls) == 1 and not sync.calls


@pytest.mark.parametrize("kind", ["taps", "local"])
def test_stale_ttl_sync_when_bg_disallowed(kind, taps_root, local_api,
                                           isolated_db, monkeypatch):
    from brew_hop_search.sources import taps, local
    mod = {"taps": taps, "local": local}[kind]
    table = {"taps": "tap", "local": "local_formula"}[kind]
    assert mod.refresh(silent=True)
    _age_meta(table, 10_000)

    bg, sync = _Recorder(), _Recorder()
    monkeypatch.setattr(mod, "background_refresh", bg)
    monkeypatch.setattr(mod, "refresh", lambda *a, **kw: (sync(*a, **kw), True)[1])
    assert mod.ensure_cache(stale=3600, allow_bg=False) is True
    assert len(sync.calls) == 1 and not bg.calls


def test_fresh_ttl_and_still_witness_does_nothing(taps_root, isolated_db,
                                                  monkeypatch):
    from brew_hop_search import witness
    from brew_hop_search.sources import taps
    monkeypatch.setattr(witness, "witness_paths", lambda kind: [taps_root])
    assert taps.refresh(silent=True)
    bg, sync = _Recorder(), _Recorder()
    monkeypatch.setattr(taps, "background_refresh", bg)
    monkeypatch.setattr(taps, "refresh", sync)
    assert taps.ensure_cache(stale=3600) is True
    assert not bg.calls and not sync.calls


@pytest.mark.parametrize("kind", ["taps", "local", "installed"])
def test_moved_witness_goes_to_background(kind, taps_root, local_api,
                                          isolated_db, monkeypatch):
    """Fresh TTL, but brew touched a witness → bg refresh (the --stale path)."""
    from brew_hop_search import witness
    from brew_hop_search.sources import taps, local, installed
    from brew_hop_search.cache import get_db, import_to_db
    mod = {"taps": taps, "local": local, "installed": installed}[kind]
    table = {"taps": "tap", "local": "local_formula",
             "installed": "installed_formula"}[kind]
    wit = taps_root / "u1" / "homebrew-foo"
    monkeypatch.setattr(witness, "witness_paths", lambda k: [wit])

    # Index with the witness as it is now.
    import_to_db(get_db(), table, [{"name": "x", "raw": "{}"}], ["name", "raw"],
                 "name", ["name"], witness=witness.witness_mtime(kind))
    if kind == "installed":  # ensure_cache checks installed_formula only
        pass

    bg, sync = _Recorder(), _Recorder()
    monkeypatch.setattr(mod, "background_refresh", bg)
    monkeypatch.setattr(mod, "refresh", sync)
    assert mod.ensure_cache(stale=3600) is True
    assert not bg.calls and not sync.calls

    # brew install/untap/update: the witness moves.
    now = time.time() + 5
    os.utime(wit, (now, now))
    assert mod.ensure_cache(stale=3600) is True
    assert len(bg.calls) == 1 and not sync.calls


# ── the shared detached runner ─────────────────────────────────────────────

def test_bg_runner_refreshes_local_and_writes_sentinel(local_api, isolated_db,
                                                       tmp_path):
    """End to end: `python -m brew_hop_search.sources._bg local` populates the
    DB (with witness), writes the sentinel, and appends to refresh.log."""
    from brew_hop_search import witness
    from brew_hop_search.cache import get_db
    sentinel = tmp_path / "local.done"
    env = {**os.environ, "BHS_REFRESH_SENTINEL": str(sentinel)}
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.sources._bg", "local"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    line = sentinel.read_text().split("\t")
    assert line[2] == "ok"
    db = get_db()
    assert "local_formula" in db.table_names()
    assert witness.stored_witness(db, "local_formula") is not None


def test_bg_runner_rejects_unknown_kind(tmp_path):
    sentinel = tmp_path / "x.done"
    env = {**os.environ, "BHS_REFRESH_SENTINEL": str(sentinel)}
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.sources._bg", "nope"],
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode != 0
    assert sentinel.read_text().split("\t")[2] == "fail"


def test_background_refresh_registers_pending(monkeypatch, tmp_path):
    """The spawn registers a pending sentinel so the trailing line can poll it."""
    from brew_hop_search.sources import _bg
    from brew_hop_search import cache
    popen = _Recorder()
    monkeypatch.setattr(_bg.subprocess, "Popen", popen)
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    before = len(cache.pending_refreshes())
    _bg.background_refresh("taps")
    assert len(popen.calls) == 1
    argv = popen.calls[0][0][0]
    assert argv[-2:] == ["brew_hop_search.sources._bg", "taps"]
    assert popen.calls[0][1]["start_new_session"] is True
    new = cache.pending_refreshes()[before:]
    assert [k for k, _, _ in new] == ["taps"]


def test_installed_background_refresh_uses_shared_runner(monkeypatch):
    from brew_hop_search.sources import installed, _bg
    rec = _Recorder()
    monkeypatch.setattr(_bg, "background_refresh", rec)
    installed.background_refresh()
    assert rec.calls == [(("installed",), {})]


def test_old_bg_installed_module_is_gone():
    import importlib.util
    assert importlib.util.find_spec("brew_hop_search._bg_installed") is None
