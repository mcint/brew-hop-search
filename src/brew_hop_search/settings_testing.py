# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Test harness for the settings layers. Importable by sibling tools:

    from brew_hop_search.settings_testing import layers, sample_values

`layers` is a pytest fixture: a clean env (no BREW_HOP*/HOMEBREW_HOP*), a
tmp config file, and helpers to set a value at any layer. It ships in the
package (not tests/) on purpose — a tool built on this table gets the
precedence matrix in tests/test_settings_layers.py for its own rows by
copying that one file.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from brew_hop_search.settings import Setting, resolve, Resolved


def sample_values(setting: Setting) -> tuple[str, str]:
    """Two distinct valid raw values for `setting`, as a user would type them."""
    k = setting.kind
    if k == "bool":
        return ("1", "0")
    if k == "duration":
        return ("2h", "45m")
    if k == "enum":
        keys = list(setting.aliases or {})
        assert len(keys) >= 2, f"enum {setting.key} needs two values to test precedence"
        return (keys[0], keys[1])
    if k == "list":
        return ("alpha,beta", "gamma")
    if k == "path":
        return ("/tmp/a-path", "/tmp/b-path")
    if k == "secret":
        return ("ghp_aaaa", "ghp_bbbb")
    if k == "limit":
        return ("30", "10+5")
    return ("value-a", "value-b")


class Layers:
    def __init__(self, tmp_path: Path, monkeypatch):
        self.tmp_path = tmp_path
        self.mp = monkeypatch
        self.cfg_path = tmp_path / "config.toml"
        self.cfg: dict[str, dict] = {}
        self.top: dict[str, object] = {}
        for k in list(os.environ):
            if k.startswith(("BREW_HOP", "HOMEBREW_HOP")):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("BREW_HOP_SEARCH_CONFIG", str(self.cfg_path))

    def set_env(self, name: str, raw: str) -> None:
        self.mp.setenv(name, raw)

    def set_config(self, scope: str, key: str, raw) -> None:
        self.cfg.setdefault(scope, {})[key] = raw
        self.write_config()

    def set_config_top(self, key: str, raw) -> None:
        """Top-level (legacy) key such as `user_agent`."""
        self.top[key] = raw
        self.write_config()

    def write_config(self) -> None:
        lines = [f"{k} = {_toml(v)}" for k, v in self.top.items()]
        for scope, table in self.cfg.items():
            lines.append(f"[{scope}]")
            lines.extend(f"{k} = {_toml(v)}" for k, v in table.items())
        self.cfg_path.write_text("\n".join(lines) + "\n")

    def resolve(self, key: str, tool: str = "search", flag=None) -> Resolved:
        return resolve(key, tool, flag)


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return '"' + str(v).replace('"', '\\"') + '"'


@pytest.fixture
def layers(tmp_path, monkeypatch) -> Layers:
    return Layers(tmp_path, monkeypatch)
