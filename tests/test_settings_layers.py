# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Precedence, for every row of SETTINGS, without writing a test per row.

Adding a Setting adds ~8 cases here automatically. Sibling tools import
`brew_hop_search.settings_testing` and run the same matrix over their table.
Spec: docs/specs/drafts/config-layers.md § Testing.
"""
from __future__ import annotations

import pytest

from brew_hop_search.settings import SETTINGS, env_name, env_names, parse_value
from brew_hop_search.settings_testing import layers, sample_values  # noqa: F401

# `config` is the path the harness itself pins (BREW_HOP_SEARCH_CONFIG), so it
# can never be observed at default here; tests/test_settings.py covers it.
ROWS = [pytest.param(s, id=s.key) for s in SETTINGS if s.key != "config"]
CONFIGURABLE = [pytest.param(s, id=s.key) for s in SETTINGS if not s.env_only]
TOOL = "search"


def _typed(setting, raw):
    v = parse_value(setting, raw)
    return (not v) if setting.negate else v


@pytest.mark.parametrize("setting", ROWS)
def test_default(layers, setting):
    r = layers.resolve(setting.key, TOOL)
    assert r.source == "default" and r.value == setting.default


@pytest.mark.parametrize("setting", CONFIGURABLE)
def test_family_config_beats_default(layers, setting):
    a, _ = sample_values(setting)
    layers.set_config("hop", setting.key, a)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"config:[hop] {setting.key}" and r.value == parse_value(setting, a)


@pytest.mark.parametrize("setting", CONFIGURABLE)
def test_tool_config_beats_family_config(layers, setting):
    a, b = sample_values(setting)
    layers.set_config("hop", setting.key, a)
    layers.set_config(TOOL, setting.key, b)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"config:[{TOOL}] {setting.key}" and r.value == parse_value(setting, b)


@pytest.mark.parametrize("setting", CONFIGURABLE)
def test_family_env_beats_tool_config(layers, setting):
    a, b = sample_values(setting)
    layers.set_config(TOOL, setting.key, a)
    layers.set_env(env_name(setting, "hop"), b)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"env:{env_name(setting, 'hop')}" and r.value == _typed(setting, b)


@pytest.mark.parametrize("setting", ROWS)
def test_tool_env_beats_family_env(layers, setting):
    a, b = sample_values(setting)
    layers.set_env(env_name(setting, "hop"), a)
    layers.set_env(env_name(setting, TOOL), b)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"env:{env_name(setting, TOOL)}" and r.value == _typed(setting, b)


@pytest.mark.parametrize("setting", ROWS)
def test_homebrew_twin_equals_brew_hop_form(layers, setting):
    a, _ = sample_values(setting)
    twin = env_names(setting, TOOL)[1]
    assert twin.startswith("HOMEBREW_HOP_")
    layers.set_env(twin, a)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"env:{twin}" and r.value == _typed(setting, a)


@pytest.mark.parametrize("setting", ROWS)
def test_brew_hop_wins_twin_conflict(layers, setting):
    a, b = sample_values(setting)
    primary, twin = env_names(setting, TOOL)[:2]
    layers.set_env(primary, a)
    layers.set_env(twin, b)
    r = layers.resolve(setting.key, TOOL)
    assert r.value == _typed(setting, a)
    want = (f"{primary} overrides {twin}" if setting.kind == "secret"
            else f"{primary}={a} overrides {twin}={b}")
    assert r.notes == [want]


@pytest.mark.parametrize("setting", ROWS)
def test_flag_beats_env(layers, setting):
    a, b = sample_values(setting)
    layers.set_env(env_name(setting, TOOL), a)
    r = layers.resolve(setting.key, TOOL, flag=parse_value(setting, b))
    assert r.source == "flag" and r.value == parse_value(setting, b)


@pytest.mark.parametrize("setting", [pytest.param(s, id=s.key) for s in SETTINGS if s.kind == "secret"])
def test_secret_never_appears_in_source_or_notes(layers, setting):
    layers.set_env(env_name(setting, "hop"), "ghp_SENTINEL")
    layers.set_env(env_names(setting, "hop")[1], "ghp_OTHER")
    r = layers.resolve(setting.key, TOOL)
    assert "ghp_SENTINEL" not in r.source
    assert all("ghp_" not in n for n in r.notes)
