# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""FEATURES list + per-feature alias; clock as the first feature.
Spec: docs/specs/drafts/config-layers.md § Features."""
from __future__ import annotations

import pytest

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_nothing_enabled_by_default(layers):
    from brew_hop_search.features import features_enabled
    assert features_enabled() == set()


def test_list_env_family(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("BREW_HOP_FEATURES", "peek, clock")
    assert features_enabled() == {"peek", "clock"}


def test_list_env_homebrew_twin(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("HOMEBREW_HOP_FEATURES", "peek")
    assert features_enabled() == {"peek"}


def test_list_config(layers):
    from brew_hop_search.features import features_enabled
    layers.set_config("hop", "features", ["clock"])
    assert features_enabled() == {"clock"}


def test_per_feature_alias_bool(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("BREW_HOP_FEATURE_PEEK", "1")
    layers.set_env("HOMEBREW_HOP_FEATURE_CLOCK", "yes")
    layers.set_env("BREW_HOP_FEATURE_OTHER", "0")      # falsy → not enabled
    assert features_enabled() == {"peek", "clock"}


def test_alias_and_list_union(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("BREW_HOP_FEATURES", "peek")
    layers.set_env("BREW_HOP_FEATURE_CLOCK", "1")
    assert features_enabled() == {"peek", "clock"}


def test_unknown_names_reported_not_fatal(layers):
    from brew_hop_search.features import features_enabled, unknown_features
    layers.set_env("BREW_HOP_FEATURES", "peek,frobnicate")
    assert "peek" in features_enabled()
    assert unknown_features() == ["frobnicate"]


def test_feature_on(layers):
    from brew_hop_search.features import feature_on
    assert feature_on("clock") is False
    layers.set_env("BREW_HOP_FEATURES", "clock")
    assert feature_on("clock") is True


def test_require_feature_exits_2_with_hint(layers, capsys):
    from brew_hop_search.features import require_feature
    with pytest.raises(SystemExit) as e:
        require_feature("peek", tool="peek", prog="brew hop peek")
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "peek is experimental" in err
    assert "BREW_HOP_FEATURES=peek" in err
    assert "HOMEBREW_HOP_FEATURES=peek" in err


def test_require_feature_passes_when_on(layers):
    from brew_hop_search.features import require_feature
    layers.set_env("BREW_HOP_FEATURES", "peek")
    require_feature("peek", tool="peek", prog="brew hop peek")   # no exit


def test_clock_feature_turns_on_clock_style(layers):
    from brew_hop_search.defaults import duration_style
    assert duration_style() == "compact"
    layers.set_env("BREW_HOP_FEATURES", "clock")
    assert duration_style() == "clock"


def test_duration_setting_still_works_without_feature(layers):
    from brew_hop_search.defaults import duration_style
    layers.set_env("BREW_HOP_SEARCH_DURATION", "clock")
    assert duration_style() == "clock"
