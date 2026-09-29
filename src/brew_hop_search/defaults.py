# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Centralized default values, with env-var override layer.

Resolution order for any setting that supports it:

    defaults (settings.py table)  →  config.toml  →  env var  →  CLI flag
    env: BREW_HOP_SEARCH_<NAME>, BREW_HOP_<NAME>, or HOMEBREW_HOP… twins

`STALE_API` and friends are resolved at module import — set the env vars
*before* invoking the CLI to take effect. The accessor functions
(`stale_api_seconds()` etc.) re-resolve on each call, which matters for
in-process tests that mutate the environment between calls.

Test ergonomics ("12-factor short-timeout"):

    BREW_HOP_SEARCH_STALE_API=2s brew-hop-search python
    BREW_HOP_SEARCH_STALE_INSTALLED=1s brew-hop-search -i
"""
from __future__ import annotations

import re

# ── duration parsing ───────────────────────────────────────────────────────

_DUR_RE = re.compile(r"(\d+)\s*([smhd])")


def parse_duration(s: str) -> int:
    """Parse '6h', '30m', '1d', '1h30m', or bare seconds → integer seconds.

    Raises ValueError on unparseable input (callers in argparse wrap it as
    ArgumentTypeError; env-var resolution silently falls back to default).
    """
    s = s.strip().lower()
    total = 0
    for amount, unit in _DUR_RE.findall(s):
        n = int(amount)
        if unit == "s":
            total += n
        elif unit == "m":
            total += n * 60
        elif unit == "h":
            total += n * 3600
        elif unit == "d":
            total += n * 86400
    if total == 0:
        total = int(s)  # bare seconds; raises ValueError if non-numeric
    return total


# ── env-var resolution helper ──────────────────────────────────────────────

def _get(key: str):
    """Read `key` through the settings table (BREW_HOP_SEARCH_<KEY>,
    BREW_HOP_<KEY>, HOMEBREW_HOP… twins, config.toml tables, default)."""
    from brew_hop_search.settings import get
    return get(key, tool="search")


# ── duration display style (experimental) ─────────────────────────────────

DURATION_STYLES = ("compact", "clock")


def duration_style() -> str:
    """How ages and time-left render in the reminder line and `-C`.

    `compact` (default): `40m old, 5h19m left`.
    `clock`: signed clock, `-0:40:12 +5:19:48`; days out to a week keep
    hours (`-3d 14:05`), then `2w3d`, `2M`, `1y1M`. A trial — see
    cache-flow.md § Duration style. Unknown values fall back to compact.
    """
    from brew_hop_search.features import feature_on
    if feature_on("clock", tool="search"):   # same switch, spelled as a feature
        return "clock"
    return _get("duration")


# ── cache stale thresholds (seconds) ───────────────────────────────────────
# Each has a function form for tests that mutate env mid-process, plus a
# module constant that captures the env value once at import time. Most
# callers should use the function form so subprocess + in-process tests
# behave the same.

def stale_api_seconds() -> int:
    """API index (formulae.brew.sh). Drives `--stale` and bg refresh."""
    return _get("stale_api")


def stale_taps_seconds() -> int:
    """Tapped repos (scanned from $(brew --repo)/Library/Taps/)."""
    return _get("stale_taps")


def stale_installed_seconds() -> int:
    """Installed-packages index (`brew info --json=v2 --installed`)."""
    return _get("stale_installed")


def stale_local_seconds() -> int:
    """Local brew API cache at $(brew --cache)/api/."""
    return _get("stale_local")


# Back-compat constants, captured at import.
STALE_API = stale_api_seconds()
STALE_TAPS = stale_taps_seconds()
STALE_INSTALLED = stale_installed_seconds()
STALE_LOCAL = stale_local_seconds()

# ── result shaping ─────────────────────────────────────────────────────────

# -n / --limit default. Overridable by env var BREW_HOP_SEARCH_LIMIT and
# then by the CLI flag. Stored as str because argparse parses N[+OFF].
LIMIT = "20"

# ── network ────────────────────────────────────────────────────────────────

# HTTP timeout for API fetches (seconds).
API_TIMEOUT = 10

# Gap between live PyPI "up to date?" checks for `-VV`. Not a hard cap —
# -VV always hits PyPI; this is for passive warn-on-stale paths.
VERSION_CHECK_INTERVAL = 4 * 3600  # 4 hours
