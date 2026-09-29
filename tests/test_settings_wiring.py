# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The old accessors now read through settings.py — same names, new layers."""
from __future__ import annotations

import types

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_stale_reads_family_env(layers):
    from brew_hop_search.defaults import stale_api_seconds
    layers.set_env("BREW_HOP_STALE_API", "2h")          # family scope, new
    assert stale_api_seconds() == 7200


def test_stale_reads_homebrew_twin(layers):
    from brew_hop_search.defaults import stale_taps_seconds
    layers.set_env("HOMEBREW_HOP_SEARCH_STALE_TAPS", "5m")
    assert stale_taps_seconds() == 300


def test_stale_reads_config(layers):
    from brew_hop_search.defaults import stale_local_seconds
    layers.set_config("search", "stale_local", "90m")
    assert stale_local_seconds() == 5400


def test_duration_style_from_config(layers):
    from brew_hop_search.defaults import duration_style
    layers.set_config("hop", "duration", "clock")
    assert duration_style() == "clock"


def test_format_legacy_output_default_still_works(layers):
    """Review Focus 1: a config from before this change keeps working."""
    from brew_hop_search._config import resolve_output_format
    layers.set_config("output", "default", "csv")
    assert resolve_output_format() == "csv"


def test_format_new_hop_table_beats_legacy(layers):
    from brew_hop_search._config import resolve_output_format
    layers.set_config("output", "default", "csv")
    layers.set_config("hop", "format", "table")
    assert resolve_output_format() == "table"


def test_format_none_when_default(layers):
    from brew_hop_search._config import resolve_output_format
    assert resolve_output_format() is None


def test_user_agent_legacy_top_level_key(layers):
    from brew_hop_search import user_agent
    layers.set_config_top("user_agent", "me/1.0")
    assert user_agent() == "me/1.0"


def test_user_agent_env_beats_config(layers):
    from brew_hop_search import user_agent
    layers.set_config_top("user_agent", "me/1.0")
    layers.set_env("BREW_HOP_UA", "env/2")
    assert user_agent() == "env/2"


def test_db_path_from_family_env(layers, tmp_path):
    from brew_hop_search.cache import effective_db_path
    layers.set_env("BREW_HOP_DB", str(tmp_path / "fam.db"))
    assert effective_db_path() == tmp_path / "fam.db"


def test_db_path_search_env_still_wins(layers, tmp_path):
    from brew_hop_search.cache import effective_db_path
    layers.set_env("BREW_HOP_DB", str(tmp_path / "fam.db"))
    layers.set_env("BREW_HOP_SEARCH_DB", str(tmp_path / "s.db"))
    assert effective_db_path() == tmp_path / "s.db"


def test_brew_version_override_env(layers):
    from brew_hop_search.brewver import _from_env
    layers.set_env("BREW_HOP_SEARCH_BREW_VERSION", "6.1.2")
    assert _from_env() == (6, 1, 2)


def _args(**kw):
    base = dict(quiet=False, no_timing=False, help_full=None, help_short=None,
                man=False, version=0, _bg_refresh=None, verbose=1)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_timing_no_timing_env_disables(layers):
    from brew_hop_search.timing import should_emit
    layers.set_env("BREW_HOP_SEARCH_NO_TIMING", "1")
    assert should_emit(_args()) is False


def test_timing_no_timing_zero_is_falsy(layers):
    """Review Focus 3: brew's rule. NO_TIMING=0 does NOT disable (it used to)."""
    from brew_hop_search.timing import should_emit
    layers.set_env("BREW_HOP_SEARCH_NO_TIMING", "0")
    assert should_emit(_args()) is True


def test_timing_config_false_disables(layers):
    from brew_hop_search.timing import should_emit
    layers.set_config("hop", "timing", False)
    assert should_emit(_args()) is False
