# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""settings.py: the declarative table, name generation, parsing, resolution.

Spec: docs/specs/drafts/config-layers.md § Names, § Precedence, § Kinds.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def clean(tmp_path, monkeypatch):
    """No BREW_HOP*/HOMEBREW_HOP* in env; config at a tmp path that may not exist."""
    for k in list(os.environ):
        if k.startswith(("BREW_HOP", "HOMEBREW_HOP")):
            monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "config.toml"
    monkeypatch.setenv("BREW_HOP_SEARCH_CONFIG", str(cfg))
    return cfg


# ── names ──────────────────────────────────────────────────────────────────

def test_env_names_most_specific_first_with_twins():
    from brew_hop_search.settings import SETTING_BY_KEY, env_names
    s = SETTING_BY_KEY["format"]
    assert env_names(s, "peek") == [
        "BREW_HOP_PEEK_FORMAT", "HOMEBREW_HOP_PEEK_FORMAT",
        "BREW_HOP_FORMAT", "HOMEBREW_HOP_FORMAT",
    ]
    assert env_names(s, "search") == [
        "BREW_HOP_SEARCH_FORMAT", "HOMEBREW_HOP_SEARCH_FORMAT",
        "BREW_HOP_FORMAT", "HOMEBREW_HOP_FORMAT",
    ]


def test_negated_bool_gets_no_prefix():
    from brew_hop_search.settings import SETTING_BY_KEY, env_name
    assert env_name(SETTING_BY_KEY["timing"], "search") == "BREW_HOP_SEARCH_NO_TIMING"


def test_env_only_setting_has_only_search_names():
    """The config path can't come from config. Today's name is BREW_HOP_SEARCH_CONFIG."""
    from brew_hop_search.settings import SETTING_BY_KEY, env_names
    assert env_names(SETTING_BY_KEY["config"], "search")[0] == "BREW_HOP_SEARCH_CONFIG"


def test_every_existing_env_name_is_generated():
    """Back-compat: the names users have exported today must all exist."""
    from brew_hop_search.settings import SETTINGS, env_names
    generated = {n for s in SETTINGS for n in env_names(s, "search")}
    for name in ("BREW_HOP_SEARCH_STALE_API", "BREW_HOP_SEARCH_STALE_INSTALLED",
                 "BREW_HOP_SEARCH_STALE_TAPS", "BREW_HOP_SEARCH_STALE_LOCAL",
                 "BREW_HOP_SEARCH_DURATION", "BREW_HOP_SEARCH_FORMAT",
                 "BREW_HOP_SEARCH_NO_TIMING", "BREW_HOP_SEARCH_DB",
                 "BREW_HOP_SEARCH_CONFIG", "BREW_HOP_SEARCH_UA",
                 "BREW_HOP_SEARCH_LIMIT", "BREW_HOP_SEARCH_BREW_VERSION"):
        assert name in generated, name


# ── parsing ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("1", True), ("yes", True), ("anything", True), ("TRUE", True),
    ("0", False), ("false", False), ("No", False), ("off", False), ("nil", False),
])
def test_bool_uses_brew_falsy_rule(raw, want):
    from brew_hop_search.settings import Setting, parse_value
    assert parse_value(Setting("x", "bool", False), raw) is want


def test_list_is_comma_separated_trimmed_no_empties():
    from brew_hop_search.settings import Setting, parse_value
    assert parse_value(Setting("x", "list", []), " peek, clock ,,") == ["peek", "clock"]


def test_enum_canonicalizes_aliases_and_rejects_unknown():
    from brew_hop_search.settings import SETTING_BY_KEY, parse_value
    fmt = SETTING_BY_KEY["format"]
    assert parse_value(fmt, "long") == "multi"
    assert parse_value(fmt, "JSON:Short") == "json:short"
    with pytest.raises(ValueError):
        parse_value(fmt, "sundial")


def test_duration_parses_and_rejects():
    from brew_hop_search.settings import SETTING_BY_KEY, parse_value
    assert parse_value(SETTING_BY_KEY["stale_api"], "2h") == 7200
    with pytest.raises(ValueError):
        parse_value(SETTING_BY_KEY["stale_api"], "soon")


def test_path_expands_home_and_vars(monkeypatch):
    from brew_hop_search.settings import Setting, parse_value
    monkeypatch.setenv("XDIR", "/tmp/x")
    p = parse_value(Setting("db", "path", None), "~/$XDIR/y.db")
    assert str(p).endswith("/tmp/x/y.db") and not str(p).startswith("~")


# ── resolution ─────────────────────────────────────────────────────────────

def test_default_when_nothing_set(clean):
    from brew_hop_search.settings import resolve
    r = resolve("stale_api", tool="search")
    assert r.value == 6 * 3600 and r.source == "default"


def test_tool_env_beats_family_env(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_FORMAT", "table")
    monkeypatch.setenv("BREW_HOP_SEARCH_FORMAT", "csv")
    r = resolve("format", tool="search")
    assert r.value == "csv" and r.source == "env:BREW_HOP_SEARCH_FORMAT"


def test_family_env_beats_tool_config(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    clean.write_text('[search]\nformat = "csv"\n')
    monkeypatch.setenv("BREW_HOP_FORMAT", "table")
    assert resolve("format", tool="search").value == "table"


def test_tool_config_beats_family_config(clean):
    from brew_hop_search.settings import resolve
    clean.write_text('[hop]\nformat = "table"\n[search]\nformat = "csv"\n')
    r = resolve("format", tool="search")
    assert r.value == "csv" and r.source == "config:[search] format"


def test_homebrew_twin_is_read(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("HOMEBREW_HOP_SEARCH_FORMAT", "csv")
    r = resolve("format", tool="search")
    assert r.value == "csv" and r.source == "env:HOMEBREW_HOP_SEARCH_FORMAT"


def test_brew_hop_wins_twin_conflict_and_notes_it(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_FORMAT", "json")
    monkeypatch.setenv("HOMEBREW_HOP_FORMAT", "table")
    r = resolve("format", tool="search")
    assert r.value == "json"
    assert r.notes == ["BREW_HOP_FORMAT=json overrides HOMEBREW_HOP_FORMAT=table"]


def test_empty_env_is_unset(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_SEARCH_FORMAT", "")
    assert resolve("format", tool="search").source == "default"


def test_garbage_env_falls_through_with_note(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    clean.write_text('[search]\nstale_api = "2h"\n')
    monkeypatch.setenv("BREW_HOP_SEARCH_STALE_API", "soon")
    r = resolve("stale_api", tool="search")
    assert r.value == 7200 and r.source == "config:[search] stale_api"
    assert r.notes == ["BREW_HOP_SEARCH_STALE_API='soon' ignored: not a duration (30s 5m 6h 1d)"]


def test_flag_beats_everything(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_SEARCH_FORMAT", "csv")
    r = resolve("format", tool="search", flag="json")
    assert r.value == "json" and r.source == "flag"


def test_negated_bool_env_turns_default_on_off(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    assert resolve("timing", tool="search").value is True
    monkeypatch.setenv("BREW_HOP_SEARCH_NO_TIMING", "1")
    assert resolve("timing", tool="search").value is False
    monkeypatch.setenv("BREW_HOP_SEARCH_NO_TIMING", "0")   # brew rule: 0 is falsy
    assert resolve("timing", tool="search").value is True


def test_legacy_config_keys_still_read(clean):
    from brew_hop_search.settings import resolve
    clean.write_text('user_agent = "me/1"\n[output]\ndefault = "csv"\n')
    assert resolve("format", tool="search").value == "csv"
    assert resolve("format", tool="search").source == "config:output.default (legacy)"
    assert resolve("ua", tool="search").value == "me/1"


def test_config_bool_and_list_types(clean):
    from brew_hop_search.settings import resolve
    clean.write_text('[hop]\ntiming = false\nfeatures = ["peek", "clock"]\n')
    assert resolve("timing", tool="search").value is False
    assert resolve("features", tool="search").value == ["peek", "clock"]


def test_secret_value_is_returned_but_flagged(clean, monkeypatch):
    from brew_hop_search.settings import resolve, SETTING_BY_KEY
    monkeypatch.setenv("BREW_HOP_GITHUB_TOKEN", "ghp_abc")
    assert resolve("github_token", tool="peek").value == "ghp_abc"
    assert SETTING_BY_KEY["github_token"].kind == "secret"


def test_unknown_key_raises():
    from brew_hop_search.settings import resolve
    with pytest.raises(KeyError):
        resolve("nope")
