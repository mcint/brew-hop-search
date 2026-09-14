# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""CLI entry point for brew-hop-search."""
from __future__ import annotations

import argparse
import os
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
    output_grep, output_json, output_csv, output_tsv, output_table,
    output_sql_insert, output_multi, fmt_duration, status_line,
)
from brew_hop_search.search import search
from brew_hop_search.sources import api, installed, taps, local

from brew_hop_search.defaults import (
    parse_duration as _parse_duration_seconds,
    stale_api_seconds,
)


# ── duration parsing ─────────────────────────────────────────────────────────

def parse_duration(s: str) -> int:
    """argparse type adapter around defaults.parse_duration."""
    try:
        return _parse_duration_seconds(s)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(
            f"invalid duration: {s!r}  (examples: 30m, 6h, 1d, 1h30m)"
        )


# ── --refresh / --fresh value parsing ────────────────────────────────────────

REFRESH_KINDS = frozenset({"index", "installed", "outdated",
                           "taps", "local", "all"})

# Single-letter (and one tolerant alias) shorthand for refresh kinds.
# `x` covers index since `i` belongs to installed. `all` is spelled out
# to avoid future ambiguity with a hypothetical `api` kind.
_REFRESH_SHORT = {
    "x": "index",
    "i": "installed",
    "t": "taps",
    "tap": "taps",
    "l": "local",
}


def force_refresh_for(args, kind: str) -> bool:
    """Should source `kind` be force-refreshed for this invocation?

    Inspects `args.refresh`:
      - frozenset    → kind in set
      - 0 (bare)     → True for everything
      - else         → False
    """
    r = getattr(args, "refresh", None)
    if isinstance(r, frozenset):
        return kind in r
    return r == 0


def conditional_refresh_secs(args) -> int | None:
    """`--refresh=DUR` form returns DUR seconds; otherwise None."""
    r = getattr(args, "refresh", None)
    if isinstance(r, int) and r > 0:
        return r
    return None


def parse_refresh(s: str):
    """Accept a duration ('6h') or a comma-separated KIND list ('index,installed').

    Returns:
      - int seconds (≥0)        for duration form
      - frozenset[str] of kinds for selector form (always force-refresh)

    Raises ArgumentTypeError on unknown kinds or unparseable input.
    Mixing (e.g. 'installed,6h') is rejected — '6h' isn't a kind.
    """
    s = (s or "").strip()
    if not s:
        raise argparse.ArgumentTypeError("--refresh: empty value")
    looks_like_kinds = ("," in s) or (s.lower() in REFRESH_KINDS) \
        or (s.lower() in _REFRESH_SHORT)
    if looks_like_kinds:
        kinds = [tok.strip().lower() for tok in s.split(",") if tok.strip()]
        # Expand shorthand (x, i, t, l, tap) before validation.
        kinds = [_REFRESH_SHORT.get(k, k) for k in kinds]
        bad = [k for k in kinds if k not in REFRESH_KINDS]
        if bad:
            raise argparse.ArgumentTypeError(
                f"--refresh: unknown kind(s): {', '.join(bad)}  "
                f"(known: {', '.join(sorted(REFRESH_KINDS))})"
            )
        if "all" in kinds:
            kinds = ["index", "installed", "taps", "local"]
        # 'outdated' = derived from index+installed; expand for downstream.
        if "outdated" in kinds:
            kinds = [k for k in kinds if k != "outdated"]
            for k in ("index", "installed"):
                if k not in kinds:
                    kinds.append(k)
        return frozenset(kinds)
    # Duration form
    try:
        return _parse_duration_seconds(s)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(
            f"--refresh: not a duration or kind list: {s!r}  "
            f"(durations: 30m, 6h, 1d; kinds: {', '.join(sorted(REFRESH_KINDS))})"
        )


# ── standalone --refresh=KIND command ────────────────────────────────────────

def _run_refresh_only(kinds: frozenset, verbose: int = 1) -> None:
    """Force-refresh the listed kinds, print one summary line per kind, exit.

    Used when `--refresh=KIND[,...]` is given with no query and no source
    flag — the invocation's whole purpose is to warm caches. Sequential
    and blocking; per-kind wall-clock at default verbosity, with a total
    line at -v.
    """
    monotonic_start = time.monotonic()
    # Order: cheapest/most-local first so the user sees something
    # immediately even if a later network step blocks.
    order = ["local", "taps", "installed", "index"]
    selected = [k for k in order if k in kinds]

    for kind in selected:
        t0 = time.monotonic()
        if kind == "index":
            ok_f = api.ensure_cache("formula", api.FORMULA_URL, force=True)
            ok_c = api.ensure_cache("cask", api.CASK_URL, force=True)
            ok = ok_f and ok_c
        elif kind == "installed":
            ok = installed.ensure_cache(force=True)
        elif kind == "taps":
            ok = taps.ensure_cache(force=True)
        elif kind == "local":
            ok = local.ensure_cache(force=True)
        else:
            continue
        dt = time.monotonic() - t0
        if verbose >= 1:
            mark = green("✓") if ok else red("✗")
            print(f"  # [cache] {kind:<10} {mark} {dt:.2f}s", file=sys.stderr)

    if verbose >= 2:
        total = time.monotonic() - monotonic_start
        print(f"  # [cache] {'total':<10}   {total:.2f}s", file=sys.stderr)


# ── cache status ─────────────────────────────────────────────────────────────

def _ttl_for(kind: str) -> tuple[int, str, str]:
    """Resolve (ttl_seconds, source_layer, env_var_name) for a cache kind.

    source_layer ∈ {"default", "env"}; env_var_name is the BREW_HOP_SEARCH_*
    name that *would* override (always populated, even when source_layer is
    "default", so -v can advertise the override knob).
    """
    from brew_hop_search.defaults import (
        stale_api_seconds, stale_installed_seconds,
        stale_taps_seconds, stale_local_seconds,
    )
    table = {
        "formula": ("STALE_API", stale_api_seconds),
        "cask": ("STALE_API", stale_api_seconds),
        "installed_formula": ("STALE_INSTALLED", stale_installed_seconds),
        "installed_cask": ("STALE_INSTALLED", stale_installed_seconds),
        "tap": ("STALE_TAPS", stale_taps_seconds),
        "local_formula": ("STALE_LOCAL", stale_local_seconds),
        "local_cask": ("STALE_LOCAL", stale_local_seconds),
    }
    env_name, fn = table.get(kind, ("", lambda: 0))
    val = fn()
    src = "env" if env_name and os.environ.get(f"BREW_HOP_SEARCH_{env_name}") else "default"
    return val, src, env_name


def _show_brew_version(verbose: int, force: bool = False) -> None:
    """`brew  7.0.1` line; at -v, one line per version-gated feature."""
    from brew_hop_search import brewver
    have = brewver.brew_version(force=force)
    print(f"  {bold('brew')}  {brewver.format_version(have)}")
    if verbose >= 2:
        for feat, needs in brewver.FEATURES.items():
            ok = have is not None and have >= needs
            mark = green("✓") if ok else red("✗")
            tail = "" if ok else dim(f"  needs {brewver.format_version(needs)}")
            print(f"    {mark} {feat}{tail}")


def show_cache_status(verbose: int = 1, refresh_brew: bool = False) -> None:
    db_exists = DB_PATH.exists()
    size_str = ""
    if db_exists:
        size_mb = DB_PATH.stat().st_size / (1024 * 1024)
        size_str = f"  {dim(f'{size_mb:.1f} MB')}"
    print(f"  {bold('db')}  {CACHE_DIR.name}/{DB_PATH.name}{size_str}")
    _show_brew_version(verbose, force=refresh_brew)

    if not db_exists:
        print(dim("  no database — run a search to build the index"))
        return

    db = get_db()

    sources = [
        ("formula", green, True),
        ("cask", yellow, True),
        ("installed_formula", green, False),
        ("installed_cask", yellow, False),
        ("tap", magenta, False),
        ("local_formula", cyan, False),
        ("local_cask", cyan, False),
    ]

    _LABELS = {
        "formula": "formula",
        "cask": "cask",
        "installed_formula": "installed:f",
        "installed_cask": "installed:c",
        "tap": "taps",
        "local_formula": "local:f",
        "local_cask": "local:c",
    }

    for kind, color_fn, check_fts in sources:
        if not table_exists(db, kind):
            continue
        count = table_count(db, kind) or 0
        age = table_age(db, kind)
        label = color_fn(_LABELS[kind])
        age_str = fmt_duration(age)
        ttl_s, src_layer, env_name = _ttl_for(kind)
        ttl_str = f"ttl {fmt_duration(ttl_s, sub_minute=True)}"
        if verbose >= 2:
            if src_layer == "env":
                ttl_str += f" {dim(f'(env: BREW_HOP_SEARCH_{env_name})')}"
            else:
                ttl_str += f" {dim('(default)')}"
        parts = [
            f"  {label}",
            f"{count:>6}",
            f"{dim(age_str + ' ago')}",
            dim(ttl_str),
        ]
        if verbose >= 3 and ttl_s > 0:
            remaining = max(0, ttl_s - int(age))
            parts.append(dim(f"fresh for {fmt_duration(remaining, sub_minute=True)}")
                         if remaining else dim("stale"))
        if check_fts:
            fts_name = f"{kind}_fts"
            has_fts = fts_name in db.table_names()
            parts.append(green("fts") if has_fts else red("no fts"))
            jp = json_path(kind)
            if jp.exists():
                jp_mb = jp.stat().st_size / (1024 * 1024)
                parts.append(dim(f"{jp_mb:.0f}MB json"))
        print("  ".join(parts))


def show_cache_status_json() -> None:
    """Machine-readable cache status with meta envelope."""
    import json as json_mod
    from brew_hop_search.display import _envelope
    from brew_hop_search import brewver
    db_exists = DB_PATH.exists()
    have = brewver.brew_version()
    info = {
        "cache_dir": str(CACHE_DIR),
        "db_path": str(DB_PATH),
        "db_exists": db_exists,
        "db_size_bytes": DB_PATH.stat().st_size if db_exists else 0,
        "brew": {
            "version": brewver.format_version(have) if have else None,
            "features": brewver.feature_table(have),
        },
        "sources": {},
    }
    source_count = 0
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
                ttl_s, src_layer, env_name = _ttl_for(kind)
                info["sources"][kind] = {
                    "count": table_count(db, kind),
                    "age_seconds": round(table_age(db, kind), 1),
                    "updated_at": table_updated_at(db, kind),
                    "fts": f"{kind}_fts" in db.table_names(),
                    "ttl_seconds": ttl_s,
                    "ttl_source": src_layer,
                    "ttl_env_var": f"BREW_HOP_SEARCH_{env_name}" if env_name else None,
                }
                source_count += 1
    env = _envelope("cache-status", info, count=source_count)
    print(json_mod.dumps(env, indent=2))


# ── history display ─────────────────────────────────────────────────────────

def _show_history(name: str, as_json: bool = False) -> None:
    from brew_hop_search.history import get_history
    from brew_hop_search.display import _envelope
    import json as json_mod
    rows = get_history(name)
    if not rows:
        print(dim(f"  no history for {name!r} — run with -i first to build the log"), file=sys.stderr)
        return
    if as_json:
        env = _envelope("history", {"versions": rows}, query=name, count=len(rows))
        print(json_mod.dumps(env, indent=2, default=str))
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
    from brew_hop_search import (
        __version__, commit_hash, install_source, user_agent, version_info,
        PYPI_URL, GITHUB_URL, BREW_TAP_URL,
    )
    src = install_source()
    v = version_info()
    print(f"brew-hop-search {v}")
    if level < 2:
        return
    if level >= 2:
        h = commit_hash()
        print(f"  {bold('version')}     {v}")
        if h:
            print(f"  {bold('commit')}      {h}")
        print(f"  {bold('install')}     {src}")
        print(f"  {bold('user-agent')}  {user_agent()}")
        print(f"  {bold('pypi')}        {PYPI_URL}")
        print(f"  {bold('github')}      {GITHUB_URL}")
        if BREW_TAP_URL:
            print(f"  {bold('tap')}         {BREW_TAP_URL}")
        # Show git commit log
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
            from brew_hop_search.version_check import _parse_version
            from urllib.request import Request, urlopen
            import json as json_mod
            pypi_json = "https://pypi.org/pypi/brew-hop-search/json"
            req = Request(pypi_json, headers={"User-Agent": user_agent()})
            with urlopen(req, timeout=5) as r:
                data = json_mod.loads(r.read())
            latest = data.get("info", {}).get("version", "")
            if latest:
                cur_v = _parse_version(v)
                latest_v = _parse_version(latest)
                if cur_v and latest_v and latest_v > cur_v:
                    print(f"{bold('pypi')}  {yellow(latest)} available (current: {v})")
                    print(dim(f"  pip install -U brew-hop-search"))
                else:
                    print(f"{bold('pypi')}  {green('up to date')} ({latest})")
            else:
                print(f"{bold('pypi')}  {dim('could not determine latest version')}")
        except Exception as e:
            print(f"{bold('pypi')}  {dim(f'check failed: {e}')}")


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    _t0 = time.monotonic()
    _args_holder: list = []  # populated post-parse so the finally can read it
    try:
        return _main_inner(argv, _args_holder)
    finally:
        if _args_holder:
            from brew_hop_search.timing import emit_footer
            emit_footer(_args_holder[0], time.monotonic() - _t0)


def _main_inner(argv, _args_holder):
    ap = argparse.ArgumentParser(
        prog="brew-hop-search",
        usage="%(prog)s [-fcitl] [-VCOH] [-gqT|--json[=MODE]|--csv|--tsv|--sql] [-n N[+OFF]] [--refresh[=DUR]] [query ...]",
        description="Fast offline-first Homebrew formula/cask search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    ap.add_argument("query", nargs="*",
                    help="search terms (AND-matched). Supports ^prefix, suffix$, "
                         "^exact$, \"quoted phrase\", name:/desc: scope, !negate. "
                         "See --help=query or man page for the full grammar.")

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
    src.add_argument("-l", "--local", action="store_true",
                     help="local API cache (offline)")
    # -L was the pre-0.4 spelling. Lowercase = source (cli-vocabulary
    # capitalization rule). Hidden alias for one release; hint on use.
    src.add_argument("-L", dest="local_legacy", action="store_true",
                     help=argparse.SUPPRESS)

    # ── info ──
    info = ap.add_argument_group("info")
    info.add_argument("-h", dest="help_short", nargs="?", const="",
                      default=None, metavar="MODE",
                      help="terse help (or MODE: man, <section>, <flag>)")
    info.add_argument("--help", dest="help_full", nargs="?", const="",
                      default=None, metavar="MODE",
                      help="full help (or MODE: man, <section>, <flag>)")
    info.add_argument("--man", action="store_true",
                      help="offline man page (same as --help=man)")
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

    # ── cache ──
    cache = ap.add_argument_group("cache")
    cache.add_argument("--refresh", "--fresh", nargs="?", type=parse_refresh,
                       const=0, default=None, metavar="DUR|KIND[,KIND...]",
                       help="sync refresh: bare=force, =DUR=if older, "
                            "=KIND[,KIND...] (kinds: index,installed,outdated,"
                            "taps,local,all). --fresh is an alias")
    cache.add_argument("--stale", nargs="?", type=parse_duration,
                       const=stale_api_seconds(), default=None, metavar="DUR",
                       help="background refresh threshold (default: 6h, "
                            "$BREW_HOP_SEARCH_STALE_API to override)")

    # ── output ──
    fmt = ap.add_argument_group("output")
    fmt.add_argument("-g", "--grep", action="store_true",
                     help="tab-separated for piping")
    fmt.add_argument("-q", "--quiet", action="store_true",
                     help="results only (for grep/fzf)")
    fmt.add_argument("--json", nargs="?", const="full", default=None,
                     choices=["full", "short"], metavar="MODE",
                     help="JSON output; MODE=full (default) or short (compact row fields)")
    fmt.add_argument("--csv", action="store_true",
                     help="CSV output")
    fmt.add_argument("--tsv", action="store_true",
                     help="tab-separated with header")
    fmt.add_argument("-T", "--table", action="store_true",
                     help="aligned columns (like sqlite3 -column)")
    fmt.add_argument("--sql", action="store_true",
                     help="SQLite INSERT statements")
    fmt.add_argument("--multi", "--long", action="store_true",
                     help="multi-line per-result with labeled fields")
    from brew_hop_search.defaults import LIMIT as DEFAULT_LIMIT
    fmt.add_argument("-n", "--limit", type=str,
                     default=os.environ.get("BREW_HOP_SEARCH_LIMIT", DEFAULT_LIMIT),
                     metavar="N[+OFF]",
                     help=f"max results [+offset], 0=all (default: {DEFAULT_LIMIT}, or $BREW_HOP_SEARCH_LIMIT)")
    fmt.add_argument("-v", "--verbose", action="count", default=0,
                     help="source tags, cache info (-vv per-source detail)")
    fmt.add_argument("--no-timing", action="store_true",
                     help="suppress the `# [time]` footer "
                          "($BREW_HOP_SEARCH_NO_TIMING also works)")

    ap.add_argument("--_bg-refresh", nargs=2, metavar=("KIND", "URL"),
                    help=argparse.SUPPRESS)

    # Normalize bare '--json' → '--json=full' so it doesn't swallow the
    # following positional as its value. '--json=short' / '--json=full' pass
    # through untouched. Also rewrite '-h=MODE' → '-h MODE'.
    from brew_hop_search.help_ui import normalize_argv
    raw = list(sys.argv[1:] if argv is None else argv)

    # Contextual -h: if -h is present alongside any flag-like token, route
    # to a renderer that echoes what was passed and explains each flag. This
    # pre-empts argparse, which otherwise consumes the next token as -h's MODE.
    if "-h" in raw:
        others = [a for a in raw if a != "-h"]
        flag_others = [a for a in others if a.startswith("-")]
        if flag_others:
            from brew_hop_search.help_ui import show_contextual
            sys.exit(show_contextual(ap, flag_others))

    normalized = normalize_argv(
        ["--json=full" if a == "--json" else a for a in raw]
    )
    args = ap.parse_args(normalized)
    _args_holder.append(args)  # for the timing-footer finally in main()

    # Legacy -L → -l. Fold into args.local; hint once unless quiet.
    if getattr(args, "local_legacy", False):
        args.local = True
        if not args.quiet:
            print(dim("  -L is now -l (lowercase = source); -L kept as an alias for one release"),
                  file=sys.stderr)

    # Apply user-configured default output format only when no CLI format
    # flag was passed. Priority: CLI flag > env var > TOML config > built-in
    # TTY default. (See docs/specs/features/cache-flow.md and _config.py.)
    _user_set_a_format_flag = bool(
        args.json or args.csv or args.tsv or args.table
        or args.sql or args.grep or args.multi or args.quiet
    )
    if not _user_set_a_format_flag:
        from brew_hop_search._config import resolve_output_format
        fmt_default = resolve_output_format()
        if fmt_default == "json":
            args.json = "full"
        elif fmt_default == "json:short":
            args.json = "short"
        elif fmt_default == "csv":
            args.csv = True
        elif fmt_default == "tsv":
            args.tsv = True
        elif fmt_default == "table":
            args.table = True
        elif fmt_default == "sql":
            args.sql = True
        elif fmt_default == "grep":
            args.grep = True
        elif fmt_default == "multi":
            args.multi = True
        elif fmt_default == "quiet":
            args.quiet = True
        # "default" or None: leave args alone

    # ── help modes ──
    # -h / --help / -h=MODE / --help=MODE / --man all land here before
    # any other mode (no DB access, no network).
    help_mode = None
    help_form = None  # "terse" | "full"
    if args.help_full is not None:
        help_mode = args.help_full
        help_form = "full"
    elif args.help_short is not None:
        help_mode = args.help_short
        help_form = "terse"

    if args.man or help_mode == "man":
        from brew_hop_search.help_ui import show_man
        sys.exit(show_man())

    if help_mode is not None:
        from brew_hop_search.help_ui import show_terse, show_scoped
        if help_mode == "":
            if help_form == "terse":
                show_terse(ap)
            else:
                ap.print_help()
            return
        sys.exit(show_scoped(ap, help_mode))

    # ── background refresh mode ──
    if getattr(args, "_bg_refresh", None):
        kind, url = args._bg_refresh
        from brew_hop_search.cache import write_sentinel, append_refresh_log
        sentinel = os.environ.get("BHS_REFRESH_SENTINEL")
        start = time.time()
        err = ""
        try:
            ok = api.refresh(kind, url, silent=True)
        except Exception as e:
            ok = False
            err = str(e)[:200]
        duration_ms = int((time.time() - start) * 1000)
        if sentinel:
            try:
                write_sentinel(Path(sentinel), duration_ms, ok, err)
            except Exception:
                pass
        append_refresh_log(kind, duration_ms, ok)
        return

    # ── version mode ──
    if args.version:
        _show_version(args.version)
        return

    # ── cache status ──
    if args.cache:
        c_verbose = 0 if args.quiet else 1 + args.verbose
        if args.json:
            show_cache_status_json()
        else:
            # Bare --refresh on -C re-probes `brew --version` too.
            show_cache_status(verbose=c_verbose,
                              refresh_brew=(args.refresh == 0))
        return

    # ── outdated mode ──
    if args.outdated:
        from brew_hop_search.outdated import (
            collect_outdated_fast, collect_outdated_brew,
            display_outdated, _filter_kinds,
        )
        # Verbosity: same scale as search (0=quiet, 1=default, 2=-v, 3=-vv).
        if args.quiet:
            o_verbose = 0
        else:
            o_verbose = 1 + args.verbose
        kinds = _filter_kinds(args.formulae, args.casks)
        # Format flag priority: json > csv > tsv > table > sql > grep > default.
        fmt = None
        if args.csv:
            fmt = "csv"
        elif args.tsv:
            fmt = "tsv"
        elif args.table:
            fmt = "table"
        elif args.sql:
            fmt = "sql"
        elif args.grep:
            fmt = "grep"
        # Suppress progress stderr when output must be silent
        silent_progress = (o_verbose == 0) or bool(args.json) or (fmt is not None)

        # Cache-first: -O reads from existing tables and bg-refreshes any stale
        # dependencies. -l skips network. --refresh promotes to sync.
        if not args.local:
            o_stale_api = args.stale if args.stale is not None else stale_api_seconds()
            for k, url in [("formula", api.FORMULA_URL), ("cask", api.CASK_URL)]:
                api.ensure_cache(k, url, force=force_refresh_for(args, "index"),
                                 stale=o_stale_api,
                                 fresh=conditional_refresh_secs(args))
            installed.ensure_cache(force=force_refresh_for(args, "installed"))

        if args.brew_verify:
            fast_data = collect_outdated_fast()
            brew_data = collect_outdated_brew(silent=silent_progress)
            display_outdated(fast_data, kinds=kinds, verbose=o_verbose,
                             as_json=args.json, fmt=fmt, diff_data=brew_data)
        else:
            from brew_hop_search.outdated import collect_outdated
            data = collect_outdated(silent=silent_progress)
            display_outdated(data, kinds=kinds, verbose=o_verbose,
                             as_json=args.json, fmt=fmt)

        # Trailing status: hold for any bg refresh kicked off above. Skipped
        # when output is non-TTY or the user asked for machine-readable.
        sys.stdout.flush()
        if not args.quiet and not args.json and fmt is None:
            from brew_hop_search.display import trailing_refresh_status
            trailing_refresh_status(verbose=o_verbose)
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
    # --refresh=KIND with no query is a standalone "load these caches"
    # command. Bare --refresh and --refresh=DUR are modifiers and stay
    # on their existing usage-hint behavior.
    if not query and not has_source_flag and isinstance(args.refresh, frozenset):
        _run_refresh_only(args.refresh, verbose=1 + args.verbose - int(args.quiet))
        return
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

    stale = args.stale if args.stale is not None else stale_api_seconds()
    fresh = conditional_refresh_secs(args)

    def _force(kind: str) -> bool:
        return force_refresh_for(args, kind)

    quiet = args.quiet
    # Verbosity levels: 0=quiet, 1=default, 2=-v, 3=-vv
    if quiet:
        verbose = 0
    else:
        verbose = 1 + args.verbose  # default=1, -v=2, -vv=3
    silent = verbose <= 1

    # Show app name on first run (no DB yet)
    if not effective_db_path().exists() and verbose >= 2:
        from brew_hop_search import __version__
        status_line(dim(f"  brew-hop-search v{__version__} — first run, building index \u2026"), done=True)

    # ── determine search sources ──
    # -f/-c filter which kinds. -i/-t/-l select which data sources.
    # Sources are additive: -i -t searches installed + taps.
    # Default (no source flags): remote API.
    want_formula = not args.casks  # True unless -c only
    want_cask = not args.formulae  # True unless -f only

    search_sources = []  # (kind, label, pk_col)

    # Honor --refresh=KIND even when the corresponding source flag isn't set.
    # Without this, `bhs --refresh=taps foo` parses correctly but never
    # actually refreshes the tap cache (taps.ensure_cache only ran inside
    # `if args.taps:`). Search results still come from whichever sources the
    # source flags select; --refresh just guarantees that cache is current.
    if isinstance(args.refresh, frozenset):
        if "taps" in args.refresh and not args.taps:
            taps.ensure_cache(force=True)
        if "local" in args.refresh and not args.local:
            local.ensure_cache(force=True)
        if "installed" in args.refresh and not args.installed:
            installed.ensure_cache(force=True)

    if args.installed:
        installed.ensure_cache(force=_force("installed"))
        if want_formula:
            search_sources.append(("installed_formula", "installed formulae", "name"))
        if want_cask:
            search_sources.append(("installed_cask", "installed casks", "token"))

    if args.local:
        local.ensure_cache(force=_force("local"))
        if want_formula:
            search_sources.append(("local_formula", "local formulae", "name"))
        if want_cask:
            search_sources.append(("local_cask", "local casks", "token"))

    if args.taps:
        taps.ensure_cache(force=_force("taps"))
        search_sources.append(("tap", "taps", "slug"))

    # Default: remote API (only if no source flags set)
    if not has_source_flag:
        api_kinds = []
        if want_formula:
            api_kinds.append(("formula", api.FORMULA_URL))
        if want_cask:
            api_kinds.append(("cask", api.CASK_URL))

        for kind, url in api_kinds:
            if not api.ensure_cache(kind, url, _force("index"), stale, fresh):
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
        if verbose >= 3:
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
        output_json(all_results, query=query, limit=limit, offset=offset,
                    mode=args.json)
        return
    if args.csv:
        output_csv(all_results)
        return
    if args.tsv:
        output_tsv(all_results)
        return
    if args.table:
        output_table(all_results)
        return
    if args.sql:
        output_sql_insert(all_results)
        return
    if args.multi:
        output_multi(all_results)
        return

    if args.grep:
        output_grep(all_results)
        return

    if verbose >= 2:
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
            display_tap_section(results, quiet=quiet, total=src_count, verbose=verbose)
        elif kind.startswith("installed"):
            sub_kind = "cask" if "cask" in kind else "formula"
            display_installed_section(results, sub_kind, quiet=quiet, total=src_count, verbose=verbose)
        elif kind.startswith("local"):
            sub_kind = "cask" if "cask" in kind else "formula"
            label = cyan("local casks") if sub_kind == "cask" else cyan("local formulae")
            display_section(results, sub_kind, label=label, quiet=quiet, total=src_count, verbose=verbose)
        else:
            display_section(results, kind, quiet=quiet, total=src_count, verbose=verbose)
        total += len(results)

    if verbose >= 1 and total == 0:
        print(dim(f"  no results{f' for {query!r}' if query else ''}"))

    # Trailing status: hold the terminal until any in-flight bg refreshes
    # complete (or ^C). TTY-only — pipelines exit immediately.
    sys.stdout.flush()
    if not quiet:
        from brew_hop_search.display import trailing_refresh_status
        trailing_refresh_status(verbose=verbose)


if __name__ == "__main__":
    main()
