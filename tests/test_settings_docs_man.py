# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Man ENVIRONMENT block round-trips from the table; non-defaults dump; notes."""
from __future__ import annotations

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_man_environment_block_is_current():
    """docs/brew-hop-search.1.md carries the generated block verbatim.
    Regenerate with `make man-env` when SETTINGS changes."""
    from pathlib import Path
    from brew_hop_search.settings_docs import render_man_environment, MAN_BEGIN, MAN_END
    text = (Path(__file__).resolve().parents[1] / "docs" / "brew-hop-search.1.md").read_text()
    start, end = text.index(MAN_BEGIN) + len(MAN_BEGIN), text.index(MAN_END)
    assert text[start:end].strip("\n") == render_man_environment().strip("\n")


def test_non_defaults_lists_only_overrides(layers):
    from brew_hop_search.settings_docs import non_defaults

    def rows_():   # the harness itself pins BREW_HOP_SEARCH_CONFIG; ignore that row
        return [r for r in non_defaults() if r[0] != "BREW_HOP_SEARCH_CONFIG"]

    assert rows_() == []
    layers.set_env("BREW_HOP_SEARCH_STALE_API", "2h")
    layers.set_config("hop", "format", "table")
    layers.set_env("BREW_HOP_GITHUB_TOKEN", "ghp_SENTINEL")
    rows = rows_()
    assert ("BREW_HOP_SEARCH_STALE_API", "2h", "env:BREW_HOP_SEARCH_STALE_API") in rows
    assert ("BREW_HOP_FORMAT", "table", "config:[hop] format") in rows
    assert ("BREW_HOP_GITHUB_TOKEN", "set", "env:BREW_HOP_GITHUB_TOKEN") in rows
    assert not any("ghp_" in str(r) for r in rows)


def test_notes_collects_twin_conflicts_and_garbage(layers):
    from brew_hop_search.settings_docs import notes
    layers.set_env("BREW_HOP_FORMAT", "json")
    layers.set_env("HOMEBREW_HOP_FORMAT", "table")
    layers.set_env("BREW_HOP_SEARCH_STALE_API", "soon")
    got = notes()
    assert "BREW_HOP_FORMAT=json overrides HOMEBREW_HOP_FORMAT=table" in got
    assert any("STALE_API='soon' ignored" in n for n in got)
