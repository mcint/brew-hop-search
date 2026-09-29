# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Experimental `clock` duration style: `-h:mm:ss` age, `+h:mm:ss` time left.

Opt-in via BREW_HOP_SEARCH_DURATION=clock (default `compact`, the existing
`2h`/`12m`/`3d2h` words). Rationale in cache-flow.md § Duration style.
"""
from __future__ import annotations

import pytest

from tests.snap import expect  # noqa: F401


# ── resolution ─────────────────────────────────────────────────────────────

def test_default_style_is_compact(monkeypatch):
    from brew_hop_search.defaults import duration_style
    monkeypatch.delenv("BREW_HOP_SEARCH_DURATION", raising=False)
    assert duration_style() == "compact"


def test_env_selects_clock(monkeypatch):
    from brew_hop_search.defaults import duration_style
    monkeypatch.setenv("BREW_HOP_SEARCH_DURATION", "clock")
    assert duration_style() == "clock"


def test_unknown_style_falls_back_to_compact(monkeypatch):
    from brew_hop_search.defaults import duration_style
    monkeypatch.setenv("BREW_HOP_SEARCH_DURATION", "sundial")
    assert duration_style() == "compact"


# ── fmt_clock: the tiers ───────────────────────────────────────────────────

@pytest.mark.parametrize("secs,want", [
    (0, "0s"),
    (12, "12s"),                       # < 5m: m/s words — "0:00:12" reads as nothing
    (250, "4m10s"),
    (299, "4m59s"),
    (300, "0:05:00"),                  # ≥ 5m, < 1d: h:mm:ss, no zero-padded hour
    (2412, "0:40:12"),
    (5 * 3600 + 19 * 60 + 48, "5:19:48"),
    (23 * 3600 + 59 * 60 + 59, "23:59:59"),
    (86400, "1d 00:00"),               # 1–7 days: days + hh:mm (morning vs evening)
    (3 * 86400 + 14 * 3600 + 5 * 60 + 9, "3d 14:05"),
    (6 * 86400 + 23 * 3600 + 59 * 60, "6d 23:59"),
    (7 * 86400, "1w"),                 # 1–8 weeks: weeks + days
    (17 * 86400, "2w3d"),
    (60 * 86400, "2M"),                # ≥ 60 days: 30-day months
    (100 * 86400, "3M"),
    (365 * 86400, "1y"),
    (400 * 86400, "1y1M"),
    (float("inf"), "never"),
])
def test_fmt_clock_tiers(secs, want):
    from brew_hop_search.display import fmt_clock
    assert fmt_clock(secs) == want


# ── fmt_age / fmt_left: signed, style-aware ────────────────────────────────

def test_signed_clock_forms():
    from brew_hop_search.display import fmt_age, fmt_left
    assert fmt_age(2412, style="clock") == "-0:40:12"
    assert fmt_age(45, style="clock") == "-45s"
    assert fmt_left(19188, style="clock") == "+5:19:48"
    assert fmt_age(3 * 86400 + 14 * 3600, style="clock") == "-3d 14:00"


def test_compact_forms_keep_the_words():
    from brew_hop_search.display import fmt_age, fmt_left
    assert fmt_age(2412, style="compact") == "40m old"
    assert fmt_left(19188, style="compact") == "5h19m left"
    assert fmt_left(30, style="compact") == "30s left"


# ── the reminder line in each style ────────────────────────────────────────

_ENTRIES = [
    {"label": "index", "age": 2412, "ttl": 21600, "changed": False},
    {"label": "installed", "age": 2770, "ttl": 3600, "changed": True},
    {"label": "local", "age": 90000, "ttl": 3600, "changed": False},
]


def test_render_cache_line_compact():
    from brew_hop_search.display import render_cache_line
    expect(render_cache_line(_ENTRIES, style="compact"),
           "# [cache] index 40m old, 5h19m left · installed 46m old, 13m left, changed"
           " · local 1d1h old, stale  [--refresh]\n")


def test_render_cache_line_clock():
    from brew_hop_search.display import render_cache_line
    expect(render_cache_line(_ENTRIES, style="clock"),
           "# [cache] index updated -0:40:12 ttl +5:19:48 · installed updated -0:46:10 ttl +0:13:50 changed"
           " · local updated -1d 01:00 stale  [--refresh]\n")


def test_render_cache_line_defaults_to_env(monkeypatch):
    from brew_hop_search.display import render_cache_line
    monkeypatch.setenv("BREW_HOP_SEARCH_DURATION", "clock")
    assert render_cache_line(_ENTRIES[:1]) == "# [cache] index updated -0:40:12 ttl +5:19:48  [--refresh]"
