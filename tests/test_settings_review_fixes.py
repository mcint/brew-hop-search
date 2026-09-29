# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Findings from the whole-branch review of config-layers, pinned."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from brew_hop_search.settings_testing import layers  # noqa: F401


def _run(*args, env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    base.update(env)
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, env=base, timeout=30)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout), re.sub(r"\033\[[0-9;]*m", "", r.stderr), r.returncode


# ── 1. -C ttl source label goes through the table ──────────────────────────

def test_ttl_source_reports_family_env_and_config(layers):
    from brew_hop_search.cli import _ttl_for
    layers.set_env("BREW_HOP_STALE_API", "2h")
    val, src, name = _ttl_for("formula")
    assert (val, src, name) == (7200, "env", "BREW_HOP_STALE_API")
    layers.set_config("search", "stale_taps", "5m")
    val, src, name = _ttl_for("tap")
    assert (val, src, name) == (300, "config", "[search] stale_taps")


def test_c_json_ttl_source_for_config(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[search]\nstale_api = "1h"\n')
    import sqlite_utils, time
    db_path = tmp_path / "x.db"
    db = sqlite_utils.Database(db_path)
    db["formula"].insert_all([{"name": "foo", "desc": "", "raw": "{}"}], pk="name")
    db["_meta"].insert({"kind": "formula", "updated_at": time.time(), "count": 1}, pk="kind")
    out, _, _ = _run("-C", "--json", env={"BREW_HOP_SEARCH_DB": str(db_path),
                                          "BREW_HOP_SEARCH_CONFIG": str(cfg)})
    f = json.loads(out)["sources"]["formula"]
    assert f["ttl_seconds"] == 3600 and f["ttl_source"] == "config"
    assert f["ttl_env_var"] == "[search] stale_api"


# ── 2. limit is validated like every other kind ────────────────────────────

@pytest.mark.parametrize("raw", ["30", "10+5", "+5", "0", "999999"])
def test_limit_accepts_n_plus_off(raw):
    from brew_hop_search.settings import SETTING_BY_KEY, parse_value
    assert parse_value(SETTING_BY_KEY["limit"], raw) == raw


@pytest.mark.parametrize("raw", ["abc", "all", "10+x", "-1", ""])
def test_limit_rejects_garbage(raw):
    from brew_hop_search.settings import SETTING_BY_KEY, parse_value
    with pytest.raises(ValueError):
        parse_value(SETTING_BY_KEY["limit"], raw)


def test_garbage_family_limit_does_not_crash_search(tmp_path):
    from tests.test_output import _seed_db
    db = tmp_path / "t.db"
    _seed_db(db)
    out, err, code = _run("-v", "python", env={"BREW_HOP_SEARCH_DB": str(db),
                                                "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
                                                "BREW_HOP_LIMIT": "abc"})
    assert code == 0 and "python@3.13" in out
    assert "# [env] BREW_HOP_LIMIT='abc' ignored" in err


# ── 3. config path honors its twin and the family name ────────────────────

def test_config_path_from_homebrew_twin(tmp_path, monkeypatch):
    from brew_hop_search._config import effective_config_path
    for k in list(os.environ):
        if k.startswith(("BREW_HOP", "HOMEBREW_HOP")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOMEBREW_HOP_SEARCH_CONFIG", str(tmp_path / "twin.toml"))
    assert effective_config_path() == tmp_path / "twin.toml"
    monkeypatch.setenv("BREW_HOP_CONFIG", str(tmp_path / "fam.toml"))   # family name also works
    monkeypatch.delenv("HOMEBREW_HOP_SEARCH_CONFIG")
    assert effective_config_path() == tmp_path / "fam.toml"
