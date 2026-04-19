"""Collect and report outdated Homebrew packages."""
from __future__ import annotations

import json
import subprocess
import sys

from brew_hop_search.cache import get_db, table_count, table_exists
from brew_hop_search.display import (
    bold, dim, green, yellow, cyan, red, magenta, status_line, _envelope,
)


ALL_KINDS = frozenset({"formulae", "casks"})


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
                    "revision": api_rev,
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


def _tag_strs(entry: dict, kind: str) -> list[str]:
    """Plain (uncolored) tag strings for row output."""
    tags = []
    if kind == "formulae":
        if entry.get("pinned"):
            tags.append("pinned")
        if entry.get("keg_only"):
            tags.append("keg-only")
    else:
        if entry.get("auto_updates"):
            tags.append("auto-updates")
    return tags


def _source_char(kind: str) -> str:
    return "f" if kind == "formulae" else "c"


def _filter_kinds(args_formulae: bool, args_casks: bool) -> set:
    """Compute kinds set from -f/-c flags (neither set = both)."""
    if not args_formulae and not args_casks:
        return set(ALL_KINDS)
    kinds = set()
    if args_formulae:
        kinds.add("formulae")
    if args_casks:
        kinds.add("casks")
    return kinds


def _rows_for(data: dict, kinds: set) -> list[dict]:
    """Flatten outdated data to row dicts (formulae first, then casks)."""
    rows = []
    for kind in ("formulae", "casks"):
        if kind not in kinds:
            continue
        for entry in data.get(kind, []):
            rows.append({
                "source": _source_char(kind),
                "name": _outdated_name(entry),
                "installed": _outdated_installed(entry),
                "current": _outdated_current(entry),
                "tags": ",".join(_tag_strs(entry, kind)),
            })
    return rows


def _fmt_outdated_line(name: str, installed: str, current: str, tags: list[str],
                       color_fn=green, prefix: str = " ") -> str:
    """Format one outdated line with optional diff prefix."""
    tag_str = "  " + " ".join(tags) if tags else ""
    return f"  {prefix} {bold(color_fn(name))}  {dim(installed)} → {current}{tag_str}"


# ── format outputs ─────────────────────────────────────────────────────────

def output_outdated_grep(data: dict, kinds: set) -> None:
    for row in _rows_for(data, kinds):
        print(f"{row['source']}\t{row['name']}\t{row['installed']}\t{row['current']}\t{row['tags']}")


def output_outdated_quiet(data: dict, kinds: set) -> None:
    """Tab-separated, no source column, no headers, no color."""
    for row in _rows_for(data, kinds):
        print(f"{row['name']}\t{row['installed']}\t{row['current']}\t{row['tags']}")


def output_outdated_csv(data: dict, kinds: set) -> None:
    import csv
    import io
    rows = _rows_for(data, kinds)
    if not rows:
        return
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["source", "name", "installed", "current", "tags"])
    w.writeheader()
    w.writerows(rows)
    print(buf.getvalue(), end="")


def output_outdated_tsv(data: dict, kinds: set) -> None:
    rows = _rows_for(data, kinds)
    if not rows:
        return
    cols = ["source", "name", "installed", "current", "tags"]
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r.get(c, "")) for c in cols))


def output_outdated_table(data: dict, kinds: set) -> None:
    rows = _rows_for(data, kinds)
    if not rows:
        return
    cols = ["source", "name", "installed", "current", "tags"]
    headers = {"source": "S", "name": "Name", "installed": "Installed",
               "current": "Current", "tags": "Tags"}
    widths = {}
    for col in cols:
        w = len(headers[col])
        for r in rows:
            w = max(w, len(str(r.get(col, ""))))
        widths[col] = w
    hdr = "  ".join(headers[c].ljust(widths[c]) for c in cols)
    sep = "  ".join("-" * widths[c] for c in cols)
    print(hdr)
    print(sep)
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def output_outdated_sql(data: dict, kinds: set) -> None:
    """Kind-specific INSERT statements with typed flag columns."""
    any_output = False
    if "formulae" in kinds and data.get("formulae"):
        print("CREATE TABLE IF NOT EXISTS outdated_formula (name TEXT, installed TEXT, current TEXT, pinned INTEGER, keg_only INTEGER);")
        for e in data["formulae"]:
            name = _outdated_name(e).replace("'", "''")
            installed = _outdated_installed(e).replace("'", "''")
            current = _outdated_current(e).replace("'", "''")
            pinned = 1 if e.get("pinned") else 0
            keg_only = 1 if e.get("keg_only") else 0
            print(f"INSERT INTO outdated_formula VALUES ('{name}', '{installed}', '{current}', {pinned}, {keg_only});")
        any_output = True
    if "casks" in kinds and data.get("casks"):
        print("CREATE TABLE IF NOT EXISTS outdated_cask (name TEXT, installed TEXT, current TEXT, auto_updates INTEGER);")
        for e in data["casks"]:
            name = _outdated_name(e).replace("'", "''")
            installed = _outdated_installed(e).replace("'", "''")
            current = _outdated_current(e).replace("'", "''")
            auto = 1 if e.get("auto_updates") else 0
            print(f"INSERT INTO outdated_cask VALUES ('{name}', '{installed}', '{current}', {auto});")
        any_output = True


def output_outdated_json(data: dict, kinds: set, *, mode: str = "full",
                         diff_data: dict | None = None) -> None:
    """Emit JSON with meta envelope. `short` mode = compact row form."""
    filtered = {k: v for k, v in data.items() if k in kinds}
    if diff_data is not None:
        filtered_diff = {k: v for k, v in diff_data.items() if k in kinds}
        total = sum(len(filtered.get(k, [])) for k in kinds) + \
                sum(len(filtered_diff.get(k, [])) for k in kinds)
        env = _envelope("outdated",
                        {"bhs": filtered, "brew": filtered_diff},
                        count=total, mode="diff")
        print(json.dumps(env, indent=2))
        return
    if mode == "short":
        rows = _rows_for(data, kinds)
        env = _envelope("outdated", {"results": rows},
                        count=len(rows), mode="short")
    else:
        total = sum(len(filtered.get(k, [])) for k in kinds)
        env = _envelope("outdated", filtered, count=total)
    print(json.dumps(env, indent=2))


# ── human/default output ──────────────────────────────────────────────────

def _source_summary_header(kinds: set) -> str:
    """-v summary like: -- comparing installed:f (460) vs formula (8314) index."""
    db = get_db()
    parts = []
    if "formulae" in kinds:
        ic = table_count(db, "installed_formula") or 0
        fc = table_count(db, "formula") or 0
        parts.append(f"installed:f ({ic}) vs formula ({fc}) index")
    if "casks" in kinds:
        ic = table_count(db, "installed_cask") or 0
        cc = table_count(db, "cask") or 0
        parts.append(f"installed:c ({ic}) vs cask ({cc}) index")
    return dim(f"  -- comparing {' • '.join(parts)}")


def _vv_details(entry: dict, kind: str) -> str | None:
    """Per-entry raw detail line for -vv, or None if nothing to show."""
    bits = []
    if kind == "formulae":
        rev = entry.get("revision")
        if rev:
            bits.append(f"revision={rev}")
        if entry.get("pinned"):
            bits.append("pinned=true")
    else:
        if entry.get("auto_updates"):
            bits.append("auto_updates=true")
    installed_list = entry.get("installed_versions") or []
    if len(installed_list) > 1:
        bits.append(f"installed_versions={len(installed_list)}")
    return dim(f"      {' '.join(bits)}") if bits else None


def display_outdated(data: dict, *, kinds: set | None = None,
                     verbose: int = 1,
                     as_json: str | bool | None = None,
                     fmt: str | None = None,
                     diff_data: dict | None = None) -> None:
    """Display outdated packages.

    Args:
        data: {"formulae": [...], "casks": [...]} from collect_outdated*.
        kinds: which kinds to show (subset of {"formulae","casks"}).
               None = both.
        verbose: 0 (quiet) | 1 (default) | 2 (-v) | 3 (-vv).
        as_json: "full" | "short" | truthy for full | None/False disables.
        fmt: "grep" | "csv" | "tsv" | "table" | "sql" | None.
        diff_data: if provided, diff mode (brew-verify).
    """
    if kinds is None:
        kinds = set(ALL_KINDS)

    # JSON takes precedence over other format flags (per spec priority).
    if as_json:
        mode = as_json if isinstance(as_json, str) else "full"
        output_outdated_json(data, kinds, mode=mode, diff_data=diff_data)
        return

    # Machine formats (bypass verbosity). Priority: csv > tsv > table > sql > grep
    if diff_data is not None and fmt in ("csv", "tsv", "table", "sql", "grep"):
        _emit_diff_machine(data, diff_data, kinds, fmt)
        return

    if fmt == "csv":
        output_outdated_csv(data, kinds)
        return
    if fmt == "tsv":
        output_outdated_tsv(data, kinds)
        return
    if fmt == "table":
        output_outdated_table(data, kinds)
        return
    if fmt == "sql":
        output_outdated_sql(data, kinds)
        return
    if fmt == "grep":
        output_outdated_grep(data, kinds)
        return

    # Quiet (level 0): tab rows, no headers, no color, no footer.
    if verbose <= 0:
        output_outdated_quiet(data, kinds)
        return

    # Diff human view
    if diff_data is not None:
        _display_outdated_diff(data, diff_data, kinds=kinds, verbose=verbose)
        return

    formulae = data.get("formulae", []) if "formulae" in kinds else []
    casks = data.get("casks", []) if "casks" in kinds else []

    # Level 2+ source summary
    if verbose >= 2:
        print(_source_summary_header(kinds))

    if not formulae and not casks:
        print(dim("  all packages are up to date"))
        return

    if "formulae" in kinds and formulae:
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
            if verbose >= 2:
                # Prefix with source indicator column.
                src = green("f")
                print(f"  {src} {bold(green(name))}  {dim(installed)} → {current}"
                      + ("  " + " ".join(tags) if tags else ""))
            else:
                print(_fmt_outdated_line(name, installed, current, tags, green))
            if verbose >= 3:
                det = _vv_details(f, "formulae")
                if det:
                    print(det)

    if "casks" in kinds and casks:
        print(f"  {dim('#')} {yellow('outdated casks')} {dim(f'({len(casks)})')}")
        for c in casks:
            name = _outdated_name(c)
            installed = _outdated_installed(c)
            current = _outdated_current(c)
            tags = []
            if c.get("auto_updates"):
                tags.append(dim("[auto-updates]"))
            if verbose >= 2:
                src = yellow("c")
                print(f"  {src} {bold(yellow(name))}  {dim(installed)} → {current}"
                      + ("  " + " ".join(tags) if tags else ""))
            else:
                print(_fmt_outdated_line(name, installed, current, tags, yellow))
            if verbose >= 3:
                det = _vv_details(c, "casks")
                if det:
                    print(det)

    print(dim(f"  -- brew upgrade • brew pin <name> • -H <name> for history"))
    print(dim(f"  -- use --brew-verify to diff against brew's authoritative results"))


# ── diff mode ─────────────────────────────────────────────────────────────

def _diff_rows(bhs: dict, brew: dict, kinds: set) -> list[dict]:
    """Machine rows for diff mode: every (kind, name) with reporter label."""
    rows = []
    for kind in ("formulae", "casks"):
        if kind not in kinds:
            continue
        bhs_map = {_outdated_name(e): e for e in bhs.get(kind, [])}
        brew_map = {_outdated_name(e): e for e in brew.get(kind, [])}
        all_names = sorted(set(bhs_map) | set(brew_map))
        for name in all_names:
            b = bhs_map.get(name)
            br = brew_map.get(name)
            entry = br or b  # prefer brew for tags if both present
            if b and br:
                reporter = "both"
                installed = _outdated_installed(br)
                current = _outdated_current(br)
                agree = _outdated_current(b) == _outdated_current(br)
            elif br:
                reporter = "brew"
                installed = _outdated_installed(br)
                current = _outdated_current(br)
                agree = False
            else:
                reporter = "bhs"
                installed = _outdated_installed(b)
                current = _outdated_current(b)
                agree = False
            rows.append({
                "source": _source_char(kind),
                "reporter": reporter,
                "name": name,
                "installed": installed,
                "current": current,
                "versions_agree": "1" if agree else "0",
                "tags": ",".join(_tag_strs(entry or {}, kind)),
            })
    return rows


def _emit_diff_machine(bhs: dict, brew: dict, kinds: set, fmt: str) -> None:
    """Emit diff in machine formats (csv/tsv/table/sql/grep) with union rows."""
    rows = _diff_rows(bhs, brew, kinds)
    cols = ["source", "reporter", "name", "installed", "current",
            "versions_agree", "tags"]
    if fmt == "grep":
        for r in rows:
            print("\t".join(str(r.get(c, "")) for c in cols))
        return
    if fmt == "tsv":
        if not rows:
            return
        print("\t".join(cols))
        for r in rows:
            print("\t".join(str(r.get(c, "")) for c in cols))
        return
    if fmt == "csv":
        import csv
        import io
        if not rows:
            return
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
        print(buf.getvalue(), end="")
        return
    if fmt == "table":
        if not rows:
            return
        headers = {c: c.capitalize() for c in cols}
        headers["source"] = "S"
        headers["versions_agree"] = "Agree"
        widths = {c: max(len(headers[c]), *(len(str(r.get(c, ""))) for r in rows))
                  for c in cols}
        print("  ".join(headers[c].ljust(widths[c]) for c in cols))
        print("  ".join("-" * widths[c] for c in cols))
        for r in rows:
            print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))
        return
    if fmt == "sql":
        if not rows:
            return
        print("CREATE TABLE IF NOT EXISTS outdated_diff (source TEXT, reporter TEXT, name TEXT, installed TEXT, current TEXT, versions_agree INTEGER, tags TEXT);")
        for r in rows:
            vals = (
                f"'{r['source']}'",
                f"'{r['reporter']}'",
                "'" + r['name'].replace("'", "''") + "'",
                "'" + r['installed'].replace("'", "''") + "'",
                "'" + r['current'].replace("'", "''") + "'",
                r['versions_agree'],
                "'" + r['tags'].replace("'", "''") + "'",
            )
            print("INSERT INTO outdated_diff VALUES (" + ", ".join(vals) + ");")
        return


def _display_outdated_diff(bhs: dict, brew: dict, *, kinds: set | None = None,
                           verbose: int = 1) -> None:
    """Show package-matched diff between bhs and brew-verify results.

    Prefixes:
      ~  version differs between bhs and brew
      +  only in brew (bhs missed it)
      -  only in bhs (brew disagrees)
      (space)  both agree
    """
    if kinds is None:
        kinds = set(ALL_KINDS)
    if verbose >= 2:
        print(_source_summary_header(kinds))
    for kind, label, color_fn in [
        ("formulae", "outdated formulae", green),
        ("casks", "outdated casks", yellow),
    ]:
        if kind not in kinds:
            continue
        bhs_list = bhs.get(kind, [])
        brew_list = brew.get(kind, [])
        bhs_map = {_outdated_name(e): e for e in bhs_list}
        brew_map = {_outdated_name(e): e for e in brew_list}
        all_names = sorted(set(bhs_map) | set(brew_map))
        if not all_names:
            continue

        # Counts
        agree = sum(1 for n in all_names if n in bhs_map and n in brew_map
                    and _outdated_current(bhs_map[n]) == _outdated_current(brew_map[n]))
        differ = sum(1 for n in all_names if n in bhs_map and n in brew_map
                     and _outdated_current(bhs_map[n]) != _outdated_current(brew_map[n]))
        only_bhs = sum(1 for n in all_names if n in bhs_map and n not in brew_map)
        only_brew = sum(1 for n in all_names if n not in bhs_map and n in brew_map)
        total = len(all_names)
        parts = [s for s in [f"~{differ}" if differ else "",
                             f"+{only_brew}" if only_brew else "",
                             f"-{only_bhs}" if only_bhs else ""] if s]
        summary = f"  {dim(' '.join(parts))}" if parts else ""
        match_note = f"  {dim(f'{agree} match')}" if agree else ""
        print(f"  {dim('#')} {color_fn(label)} {dim(f'({total})')}{summary}{match_note}")

        for name in all_names:
            in_bhs = name in bhs_map
            in_brew = name in brew_map
            b_entry = bhs_map.get(name, {})
            br_entry = brew_map.get(name, {})

            if in_bhs and in_brew:
                # Both report outdated — check if versions differ
                b_inst = _outdated_installed(b_entry)
                br_inst = _outdated_installed(br_entry)
                b_cur = _outdated_current(b_entry)
                br_cur = _outdated_current(br_entry)
                tags = []
                if br_entry.get("pinned"):
                    tags.append(yellow("[pinned]"))
                if br_entry.get("keg_only") or b_entry.get("keg_only"):
                    tags.append(dim("[keg-only]"))
                if br_entry.get("auto_updates"):
                    tags.append(dim("[auto-updates]"))
                if b_cur != br_cur:
                    # Word-diff: bhs version | brew version
                    ver_str = f"{dim(b_inst)} → {red(b_cur)}{dim('|')}{green(br_cur)}"
                    tag_line = "  " + " ".join(tags) if tags else ""
                    print(f"  {yellow('~')} {bold(color_fn(name))}  {ver_str}{tag_line}")
                else:
                    # Agree completely — no prefix
                    print(_fmt_outdated_line(name, str(br_inst), br_cur, tags, color_fn, " "))
            elif in_brew and not in_bhs:
                # Brew found it, bhs missed it
                installed = _outdated_installed(br_entry)
                current = _outdated_current(br_entry)
                tags = [dim("[brew-only]")]
                print(_fmt_outdated_line(name, installed, current, tags, color_fn, green("+")))
            else:
                # bhs found it, brew disagrees
                installed = _outdated_installed(b_entry)
                current = _outdated_current(b_entry)
                tags = [dim("[bhs-only]")]
                print(_fmt_outdated_line(name, installed, current, tags, color_fn, red("-")))

    print()
    print(dim(f"  {yellow('~')} version differs  {green('+')} brew-only  {red('-')} bhs-only  (unmarked = agree)"))
    print(dim(f"  word-diff: {red('bhs')}{dim('|')}{green('brew')} on version mismatch"))
