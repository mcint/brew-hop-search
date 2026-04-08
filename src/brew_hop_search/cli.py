"""CLI entry point for brew-hop-search."""
from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from brew_hop_search.cache import (
    DB_PATH, CACHE_DIR, get_db, json_path, table_age, table_count,
    table_exists, table_updated_at, effective_db_path,
)
from brew_hop_search.display import (
    bold, dim, green, yellow, cyan, magenta, red,
    display_section, display_tap_section, display_installed_section,
    output_grep, output_json, fmt_duration, status_line,
)
from brew_hop_search.search import search
from brew_hop_search.sources import api, installed, taps, local

DEFAULT_STALE = 6 * 3600  # 6 hours


# ── duration parsing ─────────────────────────────────────────────────────────

def parse_duration(s: str) -> int:
    s = s.strip().lower()
    total = 0
    for amount, unit in re.findall(r"(\d+)\s*([smhd])", s):
        n = int(amount)
        if unit == "s":
            total += n
        elif unit == "m":
            total += n * 60
        elif unit == "h":
            total += n * 3600
        elif unit == "d":
            total += n * 86400
    if total == 0:
        try:
            total = int(s)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"invalid duration: {s!r}  (examples: 30m, 6h, 1d, 1h30m)"
            )
    return total


# ── cache status ─────────────────────────────────────────────────────────────

def show_cache_status() -> None:
    db_exists = DB_PATH.exists()
    print(f"  {bold('cache dir')}   {CACHE_DIR}")
    print(f"  {bold('database')}    {DB_PATH}  {'exists' if db_exists else red('missing')}")
    if db_exists:
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        print(f"  {bold('db size')}     {size_mb:.1f} MB")
    print()

    db = get_db() if db_exists else None

    for kind, label_fn, url in [
        ("formula", green, api.FORMULA_URL),
        ("cask", yellow, api.CASK_URL),
    ]:
        label = label_fn(kind)
        print(f"  {bold(label)}")

        jp = json_path(kind)
        if jp.exists():
            jp_size = jp.stat().st_size / (1024 * 1024)
            jp_mtime = datetime.fromtimestamp(jp.stat().st_mtime)
            jp_age = time.time() - jp.stat().st_mtime
            print(f"    json      {jp.name}  {jp_size:.1f} MB  {dim(jp_mtime.strftime('%Y-%m-%d %H:%M'))}  ({fmt_duration(jp_age)} ago)")
        else:
            print(f"    json      {dim('not cached')}")

        if db and table_exists(db, kind):
            count = table_count(db, kind)
            updated = table_updated_at(db, kind)
            age = table_age(db, kind)
            ts_str = datetime.fromtimestamp(updated).strftime('%Y-%m-%d %H:%M') if updated else "?"
            count_str = f"{count} entries" if count else "?"
            print(f"    db index  {count_str}  {dim(ts_str)}  ({fmt_duration(age)} ago)")
            fts_name = f"{kind}_fts"
            has_fts = fts_name in db.table_names()
            print(f"    fts5      {'ready' if has_fts else red('missing')}")
        else:
            print(f"    db index  {dim('not built')}")
        print()

    # Installed
    if db:
        for kind, label in [("installed_formula", "installed formulae"), ("installed_cask", "installed casks")]:
            if table_exists(db, kind):
                count = table_count(db, kind)
                age = table_age(db, kind)
                print(f"  {bold(green(label) if 'formula' in kind else yellow(label))}")
                print(f"    db index  {count} entries  ({fmt_duration(age)} ago)")
                print()

    # Taps
    if db and table_exists(db, "tap"):
        count = table_count(db, "tap")
        age = table_age(db, "tap")
        print(f"  {bold(magenta('taps'))}")
        print(f"    db index  {count} entries  ({fmt_duration(age)} ago)")
        print()

    # Local
    for kind in ("local_formula", "local_cask"):
        if db and table_exists(db, kind):
            count = table_count(db, kind)
            age = table_age(db, kind)
            label = "local formulae" if "formula" in kind else "local casks"
            print(f"  {bold(cyan(label))}")
            print(f"    db index  {count} entries  ({fmt_duration(age)} ago)")
            print()


def show_cache_status_json() -> None:
    """Machine-readable cache status."""
    import json as json_mod
    db_exists = DB_PATH.exists()
    info = {
        "cache_dir": str(CACHE_DIR),
        "db_path": str(DB_PATH),
        "db_exists": db_exists,
        "db_size_bytes": DB_PATH.stat().st_size if db_exists else 0,
        "sources": {},
    }
    if db_exists:
        db = get_db()
        all_kinds = [
            "formula", "cask",
            "installed_formula", "installed_cask",
            "tap",
            "local_formula", "local_cask",
        ]
        for kind in all_kinds:
            if table_exists(db, kind):
                info["sources"][kind] = {
                    "count": table_count(db, kind),
                    "age_seconds": round(table_age(db, kind), 1),
                    "updated_at": table_updated_at(db, kind),
                    "fts": f"{kind}_fts" in db.table_names(),
                }
    print(json_mod.dumps(info, indent=2))


# ── history display ─────────────────────────────────────────────────────────

def _show_history(name: str, as_json: bool = False) -> None:
    from brew_hop_search.history import get_history
    import json as json_mod
    rows = get_history(name)
    if not rows:
        print(dim(f"  no history for {name!r} — run with -i first to build the log"), file=sys.stderr)
        return
    if as_json:
        print(json_mod.dumps(rows, indent=2, default=str))
        return
    print(f"  {bold('version history')} for {green(name)}")
    for r in rows:
        ts = datetime.fromtimestamp(r["recorded_at"]).strftime("%Y-%m-%d %H:%M")
        commit = r.get("brew_commit", "")
        ver = r["version"]
        kind_tag = dim(f"[{r['kind']}]")
        commit_str = dim(commit) if commit else dim("n/a")
        print(f"  {ver}  {kind_tag}  {dim(ts)}  commit {commit_str}")
    print()
    print(dim("  rollback: brew install <name>@<version>"))
    print(dim("  pin:      brew pin <name>"))


# ── version display ─────────────────────────────────────────────────────────

def _show_version(level: int) -> None:
    from brew_hop_search import __version__, version_info
    print(f"brew-hop-search {version_info()}")
    if level >= 2:
        # Show git commit log for this package
        import subprocess
        try:
            pkg_dir = Path(__file__).resolve().parent
            result = subprocess.run(
                ["git", "-C", str(pkg_dir), "log", "--oneline", "-10"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"\n{bold('recent commits')}")
                for line in result.stdout.strip().splitlines():
                    print(f"  {dim(line)}")
        except Exception:
            pass
        # Live PyPI version check
        print()
        try:
            from brew_hop_search.version_check import PYPI_URL, _parse_version
            from urllib.request import Request, urlopen
            import json as json_mod
            req = Request(PYPI_URL, headers={"User-Agent": "brew-hop-search-cli/1.0"})
            with urlopen(req, timeout=5) as r:
                data = json_mod.loads(r.read())
            latest = data.get("info", {}).get("version", "")
            if latest:
                if _parse_version(latest) > _parse_version(__version__):
                    print(f"{bold('pypi')}  {yellow(latest)} available (current: {__version__})")
                    print(dim(f"  pip install -U brew-hop-search"))
                else:
                    print(f"{bold('pypi')}  {green('up to date')} ({latest})")
            else:
                print(f"{bold('pypi')}  {dim('could not determine latest version')}")
        except Exception as e:
            print(f"{bold('pypi')}  {dim(f'check failed: {e}')}")


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="brew-hop-search",
        usage="%(prog)s [-fcitL] [-gq|--json] [-n N[+OFF]] [--refresh[=DUR]] [-VCOH] [query ...]",
        description="Fast offline-first Homebrew formula/cask search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("query", nargs="*", help="search terms (AND-matched)")

    # ── sources ──
    src = ap.add_argument_group("sources (composable, default: remote API)")
    src.add_argument("-f", "--formulae", "--formula", action="store_true",
                     help="formulae only")
    src.add_argument("-c", "--casks", "--cask", action="store_true",
                     help="casks only")
    src.add_argument("-i", "--installed", action="store_true",
                     help="installed packages")
    src.add_argument("-t", "--taps", action="store_true",
                     help="tapped repos")
    src.add_argument("-L", "--local", action="store_true",
                     help="local API cache (offline)")

    # ── output ──
    fmt = ap.add_argument_group("output")
    fmt.add_argument("-g", "--grep", action="store_true",
                     help="tab-separated for piping")
    fmt.add_argument("-q", "--quiet", action="store_true",
                     help="results only (for grep/fzf)")
    fmt.add_argument("--json", action="store_true",
                     help="raw JSON")
    fmt.add_argument("-n", "--limit", type=str, default="20", metavar="N[+OFF]",
                     help="max results [+offset], 0=all (default: 20)")
    fmt.add_argument("-v", "--verbose", action="count", default=0,
                     help="process detail (-vv for more)")

    # ── cache ──
    cache = ap.add_argument_group("cache")
    cache.add_argument("--refresh", nargs="?", type=parse_duration, const=0,
                       default=None, metavar="DUR",
                       help="sync refresh (bare: force, =DUR: if older)")
    cache.add_argument("--stale", nargs="?", type=parse_duration,
                       const=DEFAULT_STALE, default=None, metavar="DUR",
                       help="background refresh threshold (default: 6h)")

    # ── info ──
    info = ap.add_argument_group("info")
    info.add_argument("-V", "--version", action="count", default=0,
                      help="version (-VV: commits + PyPI)")
    info.add_argument("-C", "--cache-status", dest="cache", action="store_true",
                      help="cache status")
    info.add_argument("-O", "--outdated", action="store_true",
                      help="outdated packages")
    info.add_argument("--brew-verify", action="store_true",
                      help="use brew for -O (slower, authoritative)")
    info.add_argument("-H", "--history", action="store_true",
                      help="version history for rollback")
    ap.add_argument("--_bg-refresh", nargs=2, metavar=("KIND", "URL"),
                    help=argparse.SUPPRESS)

    args = ap.parse_args(argv)

    # ── background refresh mode ──
    if getattr(args, "_bg_refresh", None):
        kind, url = args._bg_refresh
        api.refresh(kind, url, silent=True)
        return

    # ── version mode ──
    if args.version:
        _show_version(args.version)
        return

    # ── cache status ──
    if args.cache:
        if args.json:
            show_cache_status_json()
        else:
            show_cache_status()
        return

    # ── outdated mode ──
    if args.outdated:
        from brew_hop_search.outdated import collect_outdated, display_outdated
        data = collect_outdated(use_brew=args.brew_verify)
        display_outdated(data, as_json=args.json)
        return

    # Join multi-word query
    query = " ".join(args.query) if args.query else ""

    # ── history mode ──
    if args.history:
        if not query:
            print("Usage: brew-hop-search --history <package-name>", file=sys.stderr)
            sys.exit(1)
        # Ensure installed index exists so history can be populated
        from brew_hop_search.history import get_history
        if not get_history(query):
            installed.ensure_cache(force=False)
        _show_history(query, args.json)
        return

    # No query and no source flags → short usage hints
    has_source_flag = args.installed or args.local or args.taps
    if not query and not has_source_flag:
        from brew_hop_search import version_info
        print(dim(f"  brew-hop-search {version_info()}"))
        print()
        print(f"  {bold('try:')}  brew-hop-search python")
        print(f"        brew-hop-search -i           {dim('-- list installed')}")
        print(f"        brew-hop-search -O            {dim('-- show outdated')}")
        print(f"        brew-hop-search --help        {dim('-- full options')}")
        sys.exit(0)

    # Parse --limit N[+OFFSET]
    limit_str = args.limit
    if "+" in limit_str:
        lim_part, off_part = limit_str.split("+", 1)
        limit = int(lim_part) if lim_part else 20  # bare +OFF uses default limit
        offset = int(off_part) if off_part else 0
    else:
        limit = int(limit_str)
        offset = 0
    if limit == 0:
        limit = 999999  # 0 = all

    stale = args.stale if args.stale is not None else DEFAULT_STALE
    # --refresh: None=no force, 0=force now, >0=sync if older than DUR
    force_refresh = args.refresh is not None and args.refresh == 0
    fresh = args.refresh if args.refresh and args.refresh > 0 else None
    verbose = args.verbose
    quiet = args.quiet
    silent = quiet or verbose == 0

    # Show app name on first run (no DB yet)
    if not effective_db_path().exists() and verbose > 0:
        from brew_hop_search import __version__
        status_line(dim(f"  brew-hop-search v{__version__} — first run, building index \u2026"), done=True)

    # ── determine search sources ──
    # -f/-c filter which kinds. -i/-t/-L select which data sources.
    # Sources are additive: -i -t searches installed + taps.
    # Default (no source flags): remote API.
    want_formula = not args.casks  # True unless -c only
    want_cask = not args.formulae  # True unless -f only

    search_sources = []  # (kind, label, pk_col)

    if args.installed:
        installed.ensure_cache(force=force_refresh)
        if want_formula:
            search_sources.append(("installed_formula", "installed formulae", "name"))
        if want_cask:
            search_sources.append(("installed_cask", "installed casks", "token"))

    if args.local:
        local.ensure_cache(force=force_refresh)
        if want_formula:
            search_sources.append(("local_formula", "local formulae", "name"))
        if want_cask:
            search_sources.append(("local_cask", "local casks", "token"))

    if args.taps:
        taps.ensure_cache(force=force_refresh)
        search_sources.append(("tap", "taps", "slug"))

    # Default: remote API (only if no source flags set)
    if not has_source_flag:
        api_kinds = []
        if want_formula:
            api_kinds.append(("formula", api.FORMULA_URL))
        if want_cask:
            api_kinds.append(("cask", api.CASK_URL))

        for kind, url in api_kinds:
            if not api.ensure_cache(kind, url, force_refresh, stale, fresh):
                print(red(f"No cache for {kind} and fetch failed."), file=sys.stderr)
                sys.exit(1)
            pk = "name" if kind == "formula" else "token"
            search_sources.append((kind, kind, pk))

    # ── search ──
    db = get_db()
    all_results = []
    total_matched = 0
    for kind, label, pk_col in search_sources:
        if not table_exists(db, kind):
            continue
        age = table_age(db, kind)
        source_count = table_count(db, kind) or 0
        if verbose >= 2:
            print(dim(f"  [{kind}] searching {source_count} entries (cache {fmt_duration(age)} old)"), file=sys.stderr)
        # Fetch limit+1 to detect truncation
        results = search(db, kind, query, limit + 1, pk_col=pk_col, offset=offset)
        truncated = len(results) > limit
        if truncated:
            results = results[:limit]
        total_matched += source_count if truncated else len(results)
        all_results.append((kind, results, age, source_count))

    # ── output ──
    if args.json:
        output_json(all_results)
        return

    if args.grep:
        output_grep(all_results)
        return

    if verbose >= 1 and not quiet:
        # Cache age header — only shown with -v
        ages = [age for _, _, age, _ in all_results if age != float("inf")]
        min_age = min(ages) if ages else 0
        age_str = "just fetched" if min_age < 60 else fmt_duration(min_age) + " old"
        source_labels = []
        for kind, _, _, _ in all_results:
            if kind.startswith("installed"):
                sub = "formula" if "formula" in kind else "cask"
                source_labels.append(f"{green('installed')}:{green(sub) if sub == 'formula' else yellow(sub)}")
            elif kind.startswith("local"):
                sub = "formula" if "formula" in kind else "cask"
                source_labels.append(f"{cyan('local')}:{green(sub) if sub == 'formula' else yellow(sub)}")
            elif kind == "tap":
                source_labels.append(magenta("taps"))
            elif kind == "cask":
                source_labels.append(yellow("cask"))
            else:
                source_labels.append(green("formula"))
        seen = set()
        unique_labels = []
        for l in source_labels:
            if l not in seen:
                seen.add(l)
                unique_labels.append(l)
        searching = " + ".join(unique_labels)
        print(dim(f"  -- cache: {age_str}   searching {searching}"))

    total = 0
    first_name = None
    for kind, results, _, src_count in all_results:
        if kind == "tap":
            display_tap_section(results, quiet=quiet, total=src_count)
        elif kind.startswith("installed"):
            sub_kind = "cask" if "cask" in kind else "formula"
            display_installed_section(results, sub_kind, quiet=quiet, total=src_count)
        elif kind.startswith("local"):
            sub_kind = "cask" if "cask" in kind else "formula"
            label = cyan("local casks") if sub_kind == "cask" else cyan("local formulae")
            display_section(results, sub_kind, label=label, quiet=quiet, total=src_count)
        else:
            display_section(results, kind, quiet=quiet, total=src_count)
        total += len(results)

    if not quiet and total == 0:
        print(dim(f"  no results{f' for {query!r}' if query else ''}"))


if __name__ == "__main__":
    main()
