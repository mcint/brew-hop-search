# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The console scripts the package installs (docs/specs/drafts/short-names.md).

`brew` runs any `brew-<name>` executable on PATH as `brew <name>`, so the
`brew-hs` script is what makes `brew hs` work; `brewhs` is the standalone
short alias. All three point at the same main.
"""
from __future__ import annotations

import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _scripts() -> dict:
    text = PYPROJECT.read_text()
    m = re.search(r"^\[project\.scripts\]\n(.*?)(?=^\[|\Z)", text, re.M | re.S)
    assert m, "no [project.scripts] table"
    out = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, v = (s.strip() for s in line.split("=", 1))
        out[k] = v.split("#", 1)[0].strip().strip('"')
    return out


def test_console_scripts_all_point_at_cli_main():
    scripts = _scripts()
    assert scripts == {
        "brew-hop-search": "brew_hop_search.cli:main",  # canonical
        "brewhs": "brew_hop_search.cli:main",           # short alias
        "brew-hs": "brew_hop_search.cli:main",          # `brew hs` subcommand
    }
