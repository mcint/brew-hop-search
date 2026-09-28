# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Index locally installed Homebrew packages."""
from __future__ import annotations

import json
import subprocess

from brew_hop_search.cache import get_db, import_to_db, table_age, table_exists
from brew_hop_search.display import dim, red, status_line

from brew_hop_search.defaults import stale_installed_seconds
from brew_hop_search import witness


# `brew info --json=v2 --installed` can be slow on large brew installs.
# Foreground (sync) timeout: snappy bound. Background timeout: generous.
_FG_TIMEOUT = 60
_BG_TIMEOUT = 300


def _brew_installed_json(timeout: int = _FG_TIMEOUT) -> dict:
    """Run `brew info --json=v2 --installed` and return parsed JSON.

    `timeout` is bumped from the foreground 60s default to 300s when this
    runs as a background refresh — a slow brew shouldn't block the user.
    """
    result = subprocess.run(
        ["brew", "info", "--json=v2", "--installed"],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"brew info failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def refresh(silent: bool = False, timeout: int = _FG_TIMEOUT) -> bool:
    prefix = "[installed]"
    if not silent:
        status_line(dim(f"  {prefix} querying brew \u2026"))
    try:
        # Sample the witness *before* asking brew: anything brew changes
        # while `brew info` runs (30s+ cold) must show as moved next read.
        wit = witness.witness_mtime("installed")
        data = _brew_installed_json(timeout=timeout)
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
                      "name", ["name", "desc"], witness=wit)

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
                      "token", ["token", "name", "desc"], witness=wit)

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


def background_refresh() -> None:
    """Spawn a detached subprocess to rerun `brew info`. Returns immediately."""
    from brew_hop_search.sources import _bg
    _bg.background_refresh("installed")


def ensure_cache(force: bool = False, stale: int | None = None,
                 allow_bg: bool = True) -> bool:
    """Cache-first: serve from disk if it exists, refresh in background if stale.

    Stale means the TTL expired *or* a witness moved (brew installed,
    upgraded or removed something since we indexed — see witness.py).
    Both take the same non-blocking path.

    Args:
      force:    Synchronous refresh regardless of age.
      stale:    Override stale threshold (seconds). None → defaults().
      allow_bg: When True (default), stale-but-present cache → bg refresh
                instead of blocking. Off in --_bg-refresh subprocesses to
                avoid recursion.
    """
    if stale is None:
        stale = stale_installed_seconds()
    db = get_db()
    has_cache = table_exists(db, "installed_formula")
    if force or not has_cache:
        return refresh()
    age = table_age(db, "installed_formula")
    if age > stale or witness.changed(db, "installed_formula"):
        if allow_bg:
            background_refresh()
        else:
            return refresh()
    return True
