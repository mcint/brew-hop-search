"""Index locally installed Homebrew packages."""
from __future__ import annotations

import json
import subprocess
import sys

from brew_search.cache import get_db, import_to_db, table_age, table_exists
from brew_search.display import dim, red

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
    if not silent:
        print(dim("  \u21bb indexing installed packages \u2026"), file=sys.stderr)
    try:
        data = _brew_installed_json()
        db = get_db()

        # Formulae
        formulae = data.get("formulae", [])
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

        if not silent:
            print(dim(f"  \u2713 indexed {len(formulae)} formulae, {len(casks)} casks"), file=sys.stderr)
        return True
    except Exception as e:
        if not silent:
            print(red(f"  \u2717 installed index failed: {e}"), file=sys.stderr)
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
