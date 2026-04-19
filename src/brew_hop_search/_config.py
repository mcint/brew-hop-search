# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""User configuration from ~/.config/brew-hop-search/config.toml."""
from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "brew-hop-search"
CONFIG_PATH = CONFIG_DIR / "config.toml"


def load_config() -> dict:
    """Load TOML config, returning empty dict if missing or invalid."""
    if not CONFIG_PATH.exists():
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
        with open(CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}
