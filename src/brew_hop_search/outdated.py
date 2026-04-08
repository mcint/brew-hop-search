"""Collect and report outdated Homebrew packages."""
from __future__ import annotations

import json
import subprocess
import sys

from brew_hop_search.cache import get_db, table_exists
from brew_hop_search.display import (
    bold, dim, green, yellow, red, status_line, fmt_duration,
)


def _brew_outdated_json() -> list[dict]:
    """Run `brew outdated --json` and return parsed list."""
    result = subprocess.run(
        ["brew", "outdated", "--json=v2"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"brew outdated failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def collect_outdated_fast() -> dict:
    """Compare installed vs API index versions locally (no brew subprocess).

    Returns dict with 'formulae' and 'casks' lists matching brew outdated format.

    NOTE: This may differ from `brew outdated` because brew considers revision,
    bottle availability, pinned status, and keg-only semantics. Use --brew-verify
    to cross-check. See: https://docs.brew.sh/FAQ
    """
    db = get_db()
    outdated_formulae = []
    outdated_casks = []

    if table_exists(db, "installed_formula") and table_exists(db, "formula"):
        for row in db.execute(
            """SELECT i.name, i.version AS installed_ver, a.version AS latest_ver
               FROM installed_formula i
               JOIN formula a ON i.name = a.name
               WHERE i.version != a.version AND a.version != ''"""
        ).fetchall():
            outdated_formulae.append({
                "name": row[0],
                "installed_versions": [row[1]],
                "current_version": row[2],
                "pinned": False,
            })

    if table_exists(db, "installed_cask") and table_exists(db, "cask"):
        for row in db.execute(
            """SELECT i.token, i.version AS installed_ver, a.version AS latest_ver
               FROM installed_cask i
               JOIN cask a ON i.token = a.token
               WHERE i.version != a.version AND a.version != ''"""
        ).fetchall():
            outdated_casks.append({
                "name": row[0],
                "installed_versions": [row[1]],
                "current_version": row[2],
            })

    return {"formulae": outdated_formulae, "casks": outdated_casks}


def collect_outdated_brew(silent: bool = False) -> dict:
    """Collect outdated via `brew outdated --json=v2` (slow, authoritative)."""
    if not silent:
        status_line(dim("  [outdated] querying brew …"))
    data = _brew_outdated_json()
    formulae = data.get("formulae", [])
    casks = data.get("casks", [])
    if not silent:
        total = len(formulae) + len(casks)
        status_line(dim(f"  [outdated] ✓ brew reports {total} outdated"), done=True)
    return {"formulae": formulae, "casks": casks}


def collect_outdated(use_brew: bool = False, silent: bool = False) -> dict:
    """Collect outdated packages. Fast local comparison by default."""
    if use_brew:
        return collect_outdated_brew(silent=silent)
    if not silent:
        status_line(dim("  [outdated] comparing installed vs index …"))
    data = collect_outdated_fast()
    total = len(data["formulae"]) + len(data["casks"])
    if not silent:
        status_line(dim(f"  [outdated] ✓ {total} outdated (local)"), done=True)
    return data


def display_outdated(data: dict, as_json: bool = False) -> None:
    """Display outdated packages with upgrade/pin hints."""
    formulae = data.get("formulae", [])
    casks = data.get("casks", [])

    if as_json:
        print(json.dumps(data, indent=2))
        return

    if not formulae and not casks:
        print(dim("  all packages are up to date"))
        return

    if formulae:
        print(f"  {green('outdated formulae')}")
        for f in formulae:
            name = f.get("name", "")
            current = f.get("installed_versions", ["?"])
            if isinstance(current, list):
                current = current[0] if current else "?"
            latest = f.get("current_version", "?")
            pinned = f.get("pinned", False)
            pin_tag = f"  {yellow('[pinned]')}" if pinned else ""
            print(f"  {bold(green(name))}  {dim(str(current))} → {latest}{pin_tag}")
        print()

    if casks:
        print(f"  {yellow('outdated casks')}")
        for c in casks:
            name = c.get("name", "")
            current = c.get("installed_versions", "?")
            if isinstance(current, str):
                pass
            elif isinstance(current, list):
                current = current[0] if current else "?"
            latest = c.get("current_version", "?")
            print(f"  {bold(yellow(name))}  {dim(str(current))} → {latest}")
        print()

    total = len(formulae) + len(casks)
    print(dim(f"  {total} outdated  •  brew upgrade"))
    print(dim(f"  pin:      brew pin <name>"))
    print(dim(f"  rollback: brew install <name>@<version>"))
    print(dim(f"  history:  brew-hop-search -H <name>"))
