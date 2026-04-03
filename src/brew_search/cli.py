"""CLI entry point for brew-search."""
from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from brew_search.cache import (
    DB_PATH, CACHE_DIR, get_db, json_path, table_age, table_count,
    table_exists, table_updated_at,
)
from brew_search.display import (
    bold, dim, green, yellow, cyan, magenta, red,
    display_section, display_tap_section, display_installed_section,
    output_grep, output_json, fmt_duration,
)
from brew_search.search import search
from brew_search.sources import api, installed, taps, local

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


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="brew-search",
        description="Fast offline-first Homebrew formula/cask search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("query", nargs="?", help="Search query")
    ap.add_argument("--refresh", action="store_true",
                    help="Force synchronous re-fetch before searching")
    ap.add_argument("-f", "--formulae", "--formula", action="store_true",
                    help="Search formulae only")
    ap.add_argument("-c", "--casks", "--cask", action="store_true",
                    help="Search casks only")
    ap.add_argument("-i", "--installed", action="store_true",
                    help="Search only installed packages")
    ap.add_argument("-t", "--taps", action="store_true",
                    help="Also search formulae/casks from tapped repos")
    ap.add_argument("-L", "--local", action="store_true",
                    help="Search brew's local API cache (offline)")
    ap.add_argument("-C", "--cache", action="store_true",
                    help="Show cache status and exit")
    ap.add_argument("--stale", type=parse_duration, default=None, metavar="DUR",
                    help="Background refresh if cache older than DUR (default: 6h)")
    ap.add_argument("--fresh", type=parse_duration, default=None, metavar="DUR",
                    help="Force synchronous refresh if cache older than DUR")
    ap.add_argument("-n", "--limit", type=int, default=20, metavar="N",
                    help="Max results per section (default 20)")
    ap.add_argument("--json", action="store_true", help="Output raw JSON")
    ap.add_argument("-g", "--grep", action="store_true",
                    help="Greppable output: slug\\tversion\\turl\\n  description")
    ap.add_argument("--_bg-refresh", nargs=2, metavar=("KIND", "URL"),
                    help=argparse.SUPPRESS)

    args = ap.parse_args(argv)

    # ── background refresh mode ──
    if getattr(args, "_bg_refresh", None):
        kind, url = args._bg_refresh
        api.refresh(kind, url, silent=True)
        return

    # ── cache status ──
    if args.cache:
        show_cache_status()
        return

    if not args.query:
        ap.print_help()
        sys.exit(0)

    stale = args.stale if args.stale is not None else DEFAULT_STALE
    fresh = args.fresh

    # ── determine search sources ──
    # Default: search remote API index (formula + cask)
    # --installed: search installed only
    # --taps: add taps to results
    # --local: use local brew cache instead of remote API

    search_sources = []  # (kind, label, pk_col)

    if args.installed:
        # Ensure installed cache
        installed.ensure_cache(force=args.refresh)
        if not args.casks:
            search_sources.append(("installed_formula", "installed formulae", "name"))
        if not args.formulae:
            search_sources.append(("installed_cask", "installed casks", "token"))
    elif args.local:
        # Use brew's local API cache
        local.ensure_cache(force=args.refresh)
        if not args.casks:
            search_sources.append(("local_formula", "local formulae", "name"))
        if not args.formulae:
            search_sources.append(("local_cask", "local casks", "token"))
    else:
        # Default: remote API
        api_kinds = []
        if args.formulae and not args.casks:
            api_kinds = [("formula", api.FORMULA_URL)]
        elif args.casks and not args.formulae:
            api_kinds = [("cask", api.CASK_URL)]
        else:
            api_kinds = [("formula", api.FORMULA_URL), ("cask", api.CASK_URL)]

        for kind, url in api_kinds:
            if not api.ensure_cache(kind, url, args.refresh, stale, fresh):
                print(red(f"No cache for {kind} and fetch failed."), file=sys.stderr)
                sys.exit(1)
            pk = "name" if kind == "formula" else "token"
            search_sources.append((kind, kind, pk))

    # Concurrently refresh taps/installed if requested alongside main search
    if args.taps:
        taps.ensure_cache(force=args.refresh)
        search_sources.append(("tap", "taps", "slug"))

    # If --installed used with non-installed search, also index installed async
    if not args.installed and not args.local:
        _maybe_async_installed_refresh()

    # ── search ──
    db = get_db()
    all_results = []
    for kind, label, pk_col in search_sources:
        if not table_exists(db, kind):
            continue
        age = table_age(db, kind)
        results = search(db, kind, args.query, args.limit, pk_col=pk_col)
        all_results.append((kind, results, age))

    # ── output ──
    if args.json:
        output_json(all_results)
        return

    if args.grep:
        output_grep(all_results)
        return

    # Cache age header
    ages = [age for _, _, age in all_results if age != float("inf")]
    min_age = min(ages) if ages else 0
    age_str = "just fetched" if min_age < 60 else fmt_duration(min_age) + " old"
    source_labels = []
    for kind, _, _ in all_results:
        if kind.startswith("installed"):
            source_labels.append(green("installed") if "formula" in kind else yellow("installed"))
        elif kind.startswith("local"):
            source_labels.append(cyan("local"))
        elif kind == "tap":
            source_labels.append(magenta("taps"))
        elif kind == "cask":
            source_labels.append(yellow("casks"))
        else:
            source_labels.append(green("formulae"))
    # Deduplicate labels while preserving order
    seen = set()
    unique_labels = []
    for l in source_labels:
        if l not in seen:
            seen.add(l)
            unique_labels.append(l)
    searching = " + ".join(unique_labels)
    print(dim(f"  cache: {age_str}   searching {searching}"))
    print()

    total = 0
    first_name = None
    for kind, results, _ in all_results:
        if kind == "tap":
            display_tap_section(results)
        elif kind.startswith("installed"):
            sub_kind = "cask" if "cask" in kind else "formula"
            display_installed_section(results, sub_kind)
        elif kind.startswith("local"):
            sub_kind = "cask" if "cask" in kind else "formula"
            label = cyan("local casks") if sub_kind == "cask" else cyan("local formulae")
            display_section(results, sub_kind, label=label)
        else:
            display_section(results, kind)
        total += len(results)
        if results and first_name is None:
            r = results[0]
            first_name = r.get("token") or r.get("name", "")

    if total == 0:
        print(dim(f"  no results for {args.query!r}"))
    elif first_name:
        print(dim(f"  {total} result(s)  \u2022  brew install {first_name}"))


def _maybe_async_installed_refresh():
    """Best-effort background refresh of installed index if stale."""
    try:
        db = get_db()
        if not table_exists(db, "installed_formula") or table_age(db, "installed_formula") > installed.DEFAULT_STALE:
            import subprocess
            subprocess.Popen(
                [sys.executable, "-m", "brew_search._bg_installed"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except Exception:
        pass


if __name__ == "__main__":
    main()
