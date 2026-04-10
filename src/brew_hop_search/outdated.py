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


def _outdated_name(entry: dict) -> str:
    return entry.get("name", entry.get("token", ""))


def _outdated_installed(entry: dict) -> str:
    v = entry.get("installed_versions", ["?"])
    return v[0] if isinstance(v, list) and v else str(v)


def _outdated_current(entry: dict) -> str:
    return entry.get("current_version", "?")


def _fmt_outdated_line(name: str, installed: str, current: str, tags: list[str],
                       color_fn=green, prefix: str = " ") -> str:
    """Format one outdated line with optional diff prefix."""
    tag_str = "  " + " ".join(tags) if tags else ""
    return f"  {prefix} {bold(color_fn(name))}  {dim(installed)} → {current}{tag_str}"


def display_outdated(data: dict, as_json: bool = False,
                     diff_data: dict | None = None) -> None:
    """Display outdated packages with upgrade/pin hints.

    If diff_data is provided, show a package-matched diff between
    the fast (data) and brew-verify (diff_data) results using
    +/-/~ prefixes.
    """
    formulae = data.get("formulae", [])
    casks = data.get("casks", [])

    if as_json:
        if diff_data:
            print(json.dumps({"fast": data, "brew": diff_data}, indent=2))
        else:
            print(json.dumps(data, indent=2))
        return

    if diff_data:
        _display_outdated_diff(data, diff_data)
        return

    if not formulae and not casks:
        print(dim("  all packages are up to date"))
        return

    if formulae:
        print(f"  {dim('#')} {green('outdated formulae')} {dim(f'({len(formulae)})')}")
        for f in formulae:
            name = _outdated_name(f)
            installed = _outdated_installed(f)
            current = _outdated_current(f)
            tags = []
            if f.get("pinned"):
                tags.append(yellow("[pinned]"))
            if f.get("keg_only"):
                tags.append(dim("[keg-only]"))
            print(_fmt_outdated_line(name, installed, current, tags, green))

    if casks:
        print(f"  {dim('#')} {yellow('outdated casks')} {dim(f'({len(casks)})')}")
        for c in casks:
            name = _outdated_name(c)
            installed = _outdated_installed(c)
            current = _outdated_current(c)
            tags = []
            if c.get("auto_updates"):
                tags.append(dim("[auto-updates]"))
            print(_fmt_outdated_line(name, installed, current, tags, yellow))

    print(dim(f"  -- brew upgrade • brew pin <name> • -H <name> for history"))
    print(dim(f"  -- use --brew-verify to diff against brew's authoritative results"))


def _display_outdated_diff(fast: dict, brew: dict) -> None:
    """Show package-matched diff between fast and brew-verify results.

    Prefixes:
      ~  both agree (version match or both present with different versions)
      +  only in brew (fast missed it)
      -  only in fast (brew disagrees)
    """
    for kind, label, color_fn in [
        ("formulae", "outdated formulae", green),
        ("casks", "outdated casks", yellow),
    ]:
        fast_list = fast.get(kind, [])
        brew_list = brew.get(kind, [])
        fast_map = {_outdated_name(e): e for e in fast_list}
        brew_map = {_outdated_name(e): e for e in brew_list}
        all_names = sorted(set(fast_map) | set(brew_map))
        if not all_names:
            continue

        # Counts
        agree = sum(1 for n in all_names if n in fast_map and n in brew_map)
        only_fast = sum(1 for n in all_names if n in fast_map and n not in brew_map)
        only_brew = sum(1 for n in all_names if n not in fast_map and n in brew_map)
        total = len(all_names)
        print(f"  {dim('#')} {color_fn(label)} {dim(f'({total})')}"
              f"  {dim(f'~{agree} +{only_brew} -{only_fast}')}")

        for name in all_names:
            in_fast = name in fast_map
            in_brew = name in brew_map
            f_entry = fast_map.get(name, {})
            b_entry = brew_map.get(name, {})

            if in_fast and in_brew:
                # Both agree it's outdated — show brew's version, word-diff if different
                f_inst = _outdated_installed(f_entry)
                b_inst = _outdated_installed(b_entry)
                f_cur = _outdated_current(f_entry)
                b_cur = _outdated_current(b_entry)
                tags = []
                if b_entry.get("pinned"):
                    tags.append(yellow("[pinned]"))
                if b_entry.get("keg_only") or f_entry.get("keg_only"):
                    tags.append(dim("[keg-only]"))
                if b_entry.get("auto_updates"):
                    tags.append(dim("[auto-updates]"))
                # Word-diff: highlight version differences
                if f_cur != b_cur:
                    ver_str = f"{dim(f_inst)} → {red(f_cur)}{dim('|')}{green(b_cur)}"
                    tag_line = "  " + " ".join(tags) if tags else ""
                    print(f"  {yellow('~')} {bold(color_fn(name))}  {ver_str}{tag_line}")
                else:
                    print(_fmt_outdated_line(name, str(b_inst), b_cur, tags, color_fn, "~"))
            elif in_brew and not in_fast:
                # Brew found it, fast missed it
                installed = _outdated_installed(b_entry)
                current = _outdated_current(b_entry)
                tags = [dim("[brew-only]")]
                print(_fmt_outdated_line(name, installed, current, tags, color_fn, green("+")))
            else:
                # Fast found it, brew disagrees
                installed = _outdated_installed(f_entry)
                current = _outdated_current(f_entry)
                tags = [dim("[fast-only]")]
                print(_fmt_outdated_line(name, installed, current, tags, color_fn, red("-")))

    print()
    print(dim(f"  ~ both agree  {green('+')} brew-only (fast missed)  {red('-')} fast-only (brew disagrees)"))
    print(dim(f"  version word-diff: {red('fast')}{dim('|')}{green('brew')} when versions differ"))
