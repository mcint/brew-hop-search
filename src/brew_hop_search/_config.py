# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""User configuration from ~/.config/brew-hop-search/config.toml.

Resolution order for any setting that supports it:

    config.toml  →  env var  →  CLI flag

CLI flag wins over env wins over config wins over built-in default.

Override the config path with $BREW_HOP_SEARCH_CONFIG (mainly for tests).
"""
from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "brew-hop-search"
CONFIG_PATH = CONFIG_DIR / "config.toml"


def effective_config_path() -> Path:
    override = os.environ.get("BREW_HOP_SEARCH_CONFIG")
    return Path(override) if override else CONFIG_PATH


def load_config() -> dict:
    """Load TOML config, returning empty dict if missing or invalid."""
    p = effective_config_path()
    if not p.exists():
        return {}
    try:
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
        with open(p, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


# ── output format resolution ───────────────────────────────────────────────

def resolve_output_format() -> str | None:
    """User-configured default output format (canonical name), or None.

    Layers per settings.py: env (any namespace) > [search] format >
    [hop] format > legacy [output] default. "default" means no override.
    """
    from brew_hop_search.settings import resolve
    r = resolve("format", tool="search")
    return None if r.source == "default" else r.value   # an explicit "default" is returned as such
