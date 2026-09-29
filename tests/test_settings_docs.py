# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""--help=env and --help=features are generated from the table."""
from __future__ import annotations

import os
import re
import subprocess
import sys

from brew_hop_search.settings_testing import layers  # noqa: F401
from tests.snap import snap  # noqa: F401


def _run(*args, env=None):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    base["HOME"] = "/home/tester"           # stable path defaults in snapshots
    base.update(env or {})
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, env=base, timeout=30)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout + r.stderr)


def test_help_env(snap):
    snap.assert_match(_run("--help=env"))


def test_help_features(snap):
    snap.assert_match(_run("--help=features"))


def test_help_features_shows_on_when_enabled():
    out = _run("--help=features", env={"BREW_HOP_FEATURES": "clock"})
    assert re.search(r"clock\s+on\b", out)
    assert re.search(r"peek\s+off\b", out)


def test_every_setting_appears_in_env_help():
    from brew_hop_search.settings import SETTINGS, env_name
    out = _run("--help=env")
    for s in SETTINGS:
        assert env_name(s, s.scope) in out, s.key


def test_env_help_mentions_twin_once():
    out = _run("--help=env")
    assert out.count("HOMEBREW_HOP") == 1   # the rule, once, in the header — not per row


def test_fmt_default_shapes():
    from brew_hop_search.settings_docs import fmt_default
    from brew_hop_search.settings import SETTING_BY_KEY
    assert fmt_default(SETTING_BY_KEY["stale_api"]) == "6h"
    assert fmt_default(SETTING_BY_KEY["timing"]) == "on"
    assert fmt_default(SETTING_BY_KEY["ua"]) == "(none)"
    assert fmt_default(SETTING_BY_KEY["features"]) == "[]"
    assert fmt_default(SETTING_BY_KEY["db"]).startswith("~/")


def test_unknown_mode_hint_lists_env_and_features():
    out = _run("--help=nope")
    assert "env" in out and "features" in out
