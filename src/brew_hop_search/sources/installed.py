# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Index locally installed Homebrew packages."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from brew_hop_search.cache import (
    get_db, import_to_db, table_age, table_exists,
    sentinel_path, register_pending_refresh,
)
from brew_hop_search.display import dim, red, status_line

from brew_hop_search.defaults import stale_installed_seconds


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


def installed_formula_version(item: dict) -> str:
    """The version on disk: the linked keg, else the newest installed keg."""
    if item.get("linked_keg"):
        return item["linked_keg"]
    kegs = item.get("installed") or []
    return kegs[-1].get("version", "") if kegs else ""


def formula_row(item: dict) -> dict:
    """installed_formula row; `version` is installed, not available."""
    return {
        "name": item.get("name", ""),
        "desc": item.get("desc") or "",
        "homepage": item.get("homepage", ""),
        "version": installed_formula_version(item),
        "raw": json.dumps(item),
    }


def cask_row(item: dict) -> dict:
    """installed_cask row; `version` is installed, not available."""
    name = item.get("name")
    return {
        "token": item.get("token", ""),
        "name": json.dumps(name) if isinstance(name, list) else str(name or ""),
        "desc": item.get("desc") or "",
        "homepage": item.get("homepage", ""),
        "version": str(item.get("installed") or ""),
        "raw": json.dumps(item),
    }


def refresh(silent: bool = False, timeout: int = _FG_TIMEOUT) -> bool:
    prefix = "[installed]"
    if not silent:
        status_line(dim(f"  {prefix} querying brew \u2026"))
    try:
        data = _brew_installed_json(timeout=timeout)
        db = get_db()

        # Formulae
        formulae = data.get("formulae", [])
        if not silent:
            status_line(dim(f"  {prefix} indexing {len(formulae)} formulae \u2026"))
        formula_rows = [formula_row(item) for item in formulae]
        import_to_db(db, "installed_formula", formula_rows,
                      list(formula_rows[0].keys()) if formula_rows else [],
                      "name", ["name", "desc"])

        # Casks
        casks = data.get("casks", [])
        if not silent:
            status_line(dim(f"  {prefix} indexing {len(casks)} casks \u2026"))
        cask_rows = [cask_row(item) for item in casks]
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


def background_refresh() -> None:
    """Spawn a detached subprocess to rerun `brew info`. Returns immediately."""
    try:
        spath = sentinel_path("installed", os.getpid())
        try:
            spath.unlink()
        except FileNotFoundError:
            pass
        env = {**os.environ, "BHS_REFRESH_SENTINEL": str(spath)}
        subprocess.Popen(
            [sys.executable, "-m", "brew_hop_search._bg_installed"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        register_pending_refresh("installed", spath)
    except Exception:
        pass


def ensure_cache(force: bool = False, stale: int | None = None,
                 allow_bg: bool = True) -> bool:
    """Cache-first: serve from disk if it exists, refresh in background if stale.

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
    if age > stale:
        if allow_bg:
            background_refresh()
        else:
            return refresh()
    return True
