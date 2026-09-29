# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""-C -v prints non-default settings with their source; -C --json carries them;
-v in search surfaces env notes."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys


def _run(*args, env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    base.update(env)
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, env=base, timeout=30)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout), re.sub(r"\033\[[0-9;]*m", "", r.stderr)


def test_c_verbose_lists_non_defaults(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_STALE_API": "2h", "BREW_HOP_GITHUB_TOKEN": "ghp_SENTINEL"}
    out, _ = _run("-C", "-v", env=env)
    assert re.search(r"settings.*non-default", out)
    assert "BREW_HOP_SEARCH_STALE_API  2h  env:BREW_HOP_STALE_API" in out
    assert "BREW_HOP_GITHUB_TOKEN  set  " in out
    assert "ghp_" not in out


def test_c_default_is_silent_about_settings(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_STALE_API": "2h"}
    out, _ = _run("-C", env=env)
    assert "BREW_HOP_STALE_API" not in out


def test_c_verbose_prints_notes(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           # (not FORMAT: a family FORMAT=json would put -C itself into JSON mode)
           "BREW_HOP_STALE_API": "2h", "HOMEBREW_HOP_STALE_API": "3h"}
    _, err = _run("-C", "-v", env=env)
    assert "# [env] BREW_HOP_STALE_API=2h overrides HOMEBREW_HOP_STALE_API=3h" in err


def test_c_json_carries_settings(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_STALE_API": "2h", "BREW_HOP_FEATURES": "clock"}
    out, _ = _run("-C", "--json", env=env)
    data = json.loads(out)
    # Keyed by the name in the setting's own scope (stale_api is a search setting);
    # `source` says which layer actually answered (here the family-scope env var).
    assert data["settings"]["BREW_HOP_SEARCH_STALE_API"] == {
        "value": "2h", "source": "env:BREW_HOP_STALE_API"}
    assert data["features"] == ["clock"]


def test_search_verbose_prints_env_notes(tmp_path):
    from tests.test_output import _seed_db
    db = tmp_path / "t.db"
    _seed_db(db)
    env = {"BREW_HOP_SEARCH_DB": str(db),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_SEARCH_STALE_API": "soon"}
    _, err = _run("-v", "python", env=env)
    assert "# [env] BREW_HOP_SEARCH_STALE_API='soon' ignored: not a duration" in err
