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


# ── --offline ──────────────────────────────────────────────────────────────

def _seed(db_path, *tables):
    """Create empty-but-present source tables so offline reads have a cache."""
    import time
    import sqlite_utils
    db = sqlite_utils.Database(db_path)
    pk = {"formula": "name", "cask": "token", "installed_formula": "name",
          "installed_cask": "token", "tap": "slug", "local_formula": "name",
          "local_cask": "token"}
    for t in tables:
        db[t].insert({pk[t]: "seed", "desc": "", "homepage": "", "version": "",
                      "raw": "{}"}, pk=pk[t])
        db["_meta"].insert({"kind": t, "updated_at": time.time(), "count": 1},
                           pk="kind", replace=True)


def test_offline_search_skips_all_network_and_refresh(monkeypatch, tmp_path):
    _seed(tmp_path / "db.sqlite", "formula", "cask")
    calls, code = _main(monkeypatch, tmp_path, ["--offline", "foo"])
    assert code == 0
    assert calls["api_formula"] == [] and calls["api_cask"] == []


def test_offline_with_missing_cache_errors_clearly(monkeypatch, tmp_path, capsys):
    calls, code = _main(monkeypatch, tmp_path, ["--offline", "foo"])
    assert code == 1
    err = capsys.readouterr().err
    assert "offline" in err and "formula" in err
    assert calls["api_formula"] == []


def test_offline_installed_does_not_touch_brew(monkeypatch, tmp_path):
    _seed(tmp_path / "db.sqlite", "installed_formula", "installed_cask")
    calls, code = _main(monkeypatch, tmp_path, ["-i", "--offline", "foo"])
    assert code == 0
    assert calls["installed"] == []


def test_offline_taps_and_local(monkeypatch, tmp_path):
    _seed(tmp_path / "db.sqlite", "tap", "local_formula", "local_cask")
    calls, code = _main(monkeypatch, tmp_path, ["-tl", "--offline", "foo"])
    assert code == 0
    assert calls["taps"] == [] and calls["local"] == []


@pytest.mark.parametrize("refresh", ["--refresh", "--refresh=6h", "--refresh=taps", "--fresh"])
def test_offline_conflicts_with_refresh(monkeypatch, tmp_path, capsys, refresh):
    # Query first: bare --refresh has nargs="?" and would swallow a
    # following positional as its value.
    _, code = _main(monkeypatch, tmp_path, ["foo", "--offline", refresh])
    assert code == 2
    assert "--offline and --refresh conflict" in capsys.readouterr().err


def test_offline_outdated_skips_ensure_cache(monkeypatch, tmp_path):
    monkeypatch.setattr("brew_hop_search.outdated.collect_outdated",
                        lambda *a, **kw: {"formulae": [], "casks": []})
    monkeypatch.setattr("brew_hop_search.outdated.display_outdated",
                        lambda *a, **kw: None)
    calls, code = _main(monkeypatch, tmp_path, ["-O", "--offline"])
    assert code == 0
    assert calls["api_formula"] == [] and calls["installed"] == []


def test_help_lists_offline():
    out, _, _ = _run("--help")
    assert "--offline" in out


# ── --stale universalized ──────────────────────────────────────────────────

def test_parse_stale_forms():
    from brew_hop_search.cli import parse_stale
    assert parse_stale("1h") == 3600
    assert parse_stale("installed:5m") == {"installed": 300}
    assert parse_stale("i:5m,t:10m") == {"installed": 300, "taps": 600}
    assert parse_stale("x:1h") == {"index": 3600}
    assert parse_stale("all:2m") == {"index": 120, "installed": 120,
                                     "taps": 120, "local": 120}


@pytest.mark.parametrize("bad", ["bogus:1h", "installed:zzz", "installed:", ":5m", "outdated:1h"])
def test_parse_stale_rejects(bad):
    import argparse
    from brew_hop_search.cli import parse_stale
    with pytest.raises(argparse.ArgumentTypeError):
        parse_stale(bad)


def test_no_stale_flag_leaves_source_defaults(monkeypatch, tmp_path):
    calls, _ = _main(monkeypatch, tmp_path, ["-itl", "foo"])
    assert calls["installed"][0]["stale"] is None
    assert calls["taps"][0]["stale"] is None
    assert calls["local"][0]["stale"] is None


def test_bare_stale_duration_applies_to_every_touched_source(monkeypatch, tmp_path):
    calls, _ = _main(monkeypatch, tmp_path, ["--stale", "1h", "-itl", "foo"])
    assert calls["installed"][0]["stale"] == 3600
    assert calls["taps"][0]["stale"] == 3600
    assert calls["local"][0]["stale"] == 3600


def test_stale_selector_targets_one_source(monkeypatch, tmp_path):
    calls, _ = _main(monkeypatch, tmp_path, ["--stale=installed:5m", "-it", "foo"])
    assert calls["installed"][0]["stale"] == 300
    assert calls["taps"][0]["stale"] is None


def test_stale_selector_index_reaches_api(monkeypatch, tmp_path):
    calls, _ = _main(monkeypatch, tmp_path, ["--stale=x:1h", "foo"])
    assert calls["api_formula"][0]["stale"] == 3600
    assert calls["api_cask"][0]["stale"] == 3600


def test_stale_selector_multi(monkeypatch, tmp_path):
    calls, _ = _main(monkeypatch, tmp_path, ["--stale=i:5m,l:10m", "-itl", "foo"])
    assert calls["installed"][0]["stale"] == 300
    assert calls["local"][0]["stale"] == 600
    assert calls["taps"][0]["stale"] is None


def test_stale_reaches_outdated_installed(monkeypatch, tmp_path):
    monkeypatch.setattr("brew_hop_search.outdated.collect_outdated",
                        lambda *a, **kw: {"formulae": [], "casks": []})
    monkeypatch.setattr("brew_hop_search.outdated.display_outdated",
                        lambda *a, **kw: None)
    calls, code = _main(monkeypatch, tmp_path, ["-O", "--stale=installed:5m"])
    assert code == 0
    assert calls["installed"][0]["stale"] == 300
    assert calls["api_formula"][0]["stale"] is None or calls["api_formula"][0]["stale"] > 300


def test_stale_bad_kind_is_a_usage_error(monkeypatch, tmp_path, capsys):
    _, code = _main(monkeypatch, tmp_path, ["--stale=bogus:1h", "foo"])
    assert code == 2
    assert "unknown kind" in capsys.readouterr().err
