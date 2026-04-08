"""Collect and report outdated Homebrew packages."""
from __future__ import annotations

import json
import subprocess
import sys

from brew_hop_search.cache import get_db, table_exists
from brew_hop_search.display import (
    bold, dim, green, yellow, cyan, red, magenta, status_line,
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


def _version_with_rev(version: str, revision: int) -> str:
    """Combine version + revision like brew does: 1.2.3_1."""
    if revision and revision > 0:
        return f"{version}_{revision}"
    return version


def collect_outdated_fast() -> dict:
    """Compare installed vs API index using raw JSON (no brew subprocess).

    Compares version+revision from installed JSON against API JSON.
    Respects pinned status and marks keg-only packages.

    Limitations vs `brew outdated`:
    - Does not check bottle rebuild numbers
    - Does not evaluate `pour_bottle_only_if` conditions
    - Tap-only formulae not in the main API index are skipped
    Use --brew-verify to cross-check.
    """
    db = get_db()
    outdated_formulae = []
    outdated_casks = []

    # Build API version lookup from raw JSON
    api_versions = {}  # name -> (version, revision)
    if table_exists(db, "formula"):
        for row in db.execute("SELECT name, raw FROM formula").fetchall():
            raw = json.loads(row[1])
            ver = (raw.get("versions") or {}).get("stable", "")
            rev = raw.get("revision", 0)
            api_versions[row[0]] = (ver, rev)

    if table_exists(db, "installed_formula"):
        for row in db.execute("SELECT raw FROM installed_formula").fetchall():
            raw = json.loads(row[0])
            name = raw.get("name", "")
            pinned = raw.get("pinned", False)
            keg_only = raw.get("keg_only", False)

            # Get installed version(s) from the installed array
            installed_list = raw.get("installed") or []
            if not installed_list:
                continue
            installed_ver = installed_list[0].get("version", "")

            # Compare against API
            if name not in api_versions:
                continue  # tap-only formula, not in main index
            api_ver, api_rev = api_versions[name]
            if not api_ver:
                continue
            api_full = _version_with_rev(api_ver, api_rev)

            if installed_ver != api_full:
                entry = {
                    "name": name,
                    "installed_versions": [installed_ver],
                    "current_version": api_full,
                    "pinned": pinned,
                }
                if keg_only:
                    entry["keg_only"] = True
                outdated_formulae.append(entry)

    # Casks: simpler — just version string comparison
    api_cask_versions = {}
    if table_exists(db, "cask"):
        for row in db.execute("SELECT token, raw FROM cask").fetchall():
            raw = json.loads(row[1])
            api_cask_versions[row[0]] = str(raw.get("version", ""))

    if table_exists(db, "installed_cask"):
        for row in db.execute("SELECT raw FROM installed_cask").fetchall():
            raw = json.loads(row[0])
            token = raw.get("token", "")
            installed_ver = str(raw.get("installed", ""))
            if not installed_ver or token not in api_cask_versions:
                continue
            api_ver = api_cask_versions[token]
            if installed_ver != api_ver and api_ver != "latest":
                outdated_casks.append({
                    "name": token,
                    "installed_versions": [installed_ver],
                    "current_version": api_ver,
                    "auto_updates": raw.get("auto_updates", False),
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
        print(f"  {dim('#')} {green('outdated formulae')} {dim(f'({len(formulae)})')}")
        for f in formulae:
            name = f.get("name", "")
            current = f.get("installed_versions", ["?"])
            if isinstance(current, list):
                current = current[0] if current else "?"
            latest = f.get("current_version", "?")
            tags = []
            if f.get("pinned"):
                tags.append(yellow("[pinned]"))
            if f.get("keg_only"):
                tags.append(dim("[keg-only]"))
            tag_str = "  " + " ".join(tags) if tags else ""
            print(f"  {bold(green(name))}  {dim(str(current))} → {latest}{tag_str}")

    if casks:
        print(f"  {dim('#')} {yellow('outdated casks')} {dim(f'({len(casks)})')}")
        for c in casks:
            name = c.get("name", "")
            current = c.get("installed_versions", "?")
            if isinstance(current, list):
                current = current[0] if current else "?"
            latest = c.get("current_version", "?")
            tag_str = f"  {dim('[auto-updates]')}" if c.get("auto_updates") else ""
            print(f"  {bold(yellow(name))}  {dim(str(current))} → {latest}{tag_str}")

    print(dim(f"  -- brew upgrade • brew pin <name> • -H <name> for history"))
    print(dim(f"  -- may differ from brew outdated (pins, bottles, tap-only)"))
    print(dim(f"  -- use --brew-verify for authoritative results"))
