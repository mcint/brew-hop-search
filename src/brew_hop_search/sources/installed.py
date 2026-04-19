# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Index locally installed Homebrew packages."""
from __future__ import annotations

import json
import subprocess
import sys

from brew_hop_search.cache import get_db, import_to_db, table_age, table_exists
from brew_hop_search.display import dim, red, status_line

DEFAULT_STALE = 3600  # re-index installed packages if older than 1h


def _brew_installed_json() -> dict:
    """Run `brew info --json=v2 --installed` and return parsed JSON."""
    result = subprocess.run(
        ["brew", "info", "--json=v2", "--installed"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"brew info failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def refresh(silent: bool = False) -> bool:
    prefix = "[installed]"
    if not silent:
        status_line(dim(f"  {prefix} querying brew \u2026"))
    try:
        data = _brew_installed_json()
        db = get_db()

        # Formulae
        formulae = data.get("formulae", [])
        if not silent:
            status_line(dim(f"  {prefix} indexing {len(formulae)} formulae \u2026"))
        formula_rows = [
            {
                "name": item.get("name", ""),
                "desc": item.get("desc") or "",
                "homepage": item.get("homepage", ""),
                "version": (item.get("versions") or {}).get("stable", ""),
                "raw": json.dumps(item),
            }
            for item in formulae
        ]
        import_to_db(db, "installed_formula", formula_rows,
                      list(formula_rows[0].keys()) if formula_rows else [],
                      "name", ["name", "desc"])

        # Casks
        casks = data.get("casks", [])
        if not silent:
            status_line(dim(f"  {prefix} indexing {len(casks)} casks \u2026"))
        cask_rows = [
            {
                "token": item.get("token", ""),
                "name": json.dumps(item.get("name")) if isinstance(item.get("name"), list) else str(item.get("name", "")),
                "desc": item.get("desc") or "",
                "homepage": item.get("homepage", ""),
                "version": str(item.get("version", "")),
                "raw": json.dumps(item),
            }
            for item in casks
        ]
        import_to_db(db, "installed_cask", cask_rows,
                      list(cask_rows[0].keys()) if cask_rows else [],
                      "token", ["token", "name", "desc"])

        # Record to install history log
        from brew_hop_search.history import record_installed
        try:
            record_installed(formulae, casks)
        except Exception:
            pass  # never block on history logging

        if not silent:
            status_line(dim(f"  {prefix} \u2713 {len(formulae)} formulae, {len(casks)} casks"), done=True)
        return True
    except Exception as e:
        if not silent:
            status_line(red(f"  {prefix} \u2717 index failed: {e}"), done=True)
        return False


def ensure_cache(force: bool = False, stale: int = DEFAULT_STALE) -> bool:
    db = get_db()
    needs_sync = force or not table_exists(db, "installed_formula")
    if not needs_sync:
        age = table_age(db, "installed_formula")
        if age > stale:
            needs_sync = True
    if needs_sync:
        return refresh()
    return True
