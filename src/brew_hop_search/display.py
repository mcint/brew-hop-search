# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Output formatters: TTY, grep, JSON."""
from __future__ import annotations

import json
import sys
import time


# ── duration formatting ──────────────────────────────────────────────────────

def fmt_duration(seconds: float, sub_minute: bool = False) -> str:
    """Format seconds as a compact duration.

    By default, sub-minute values render as '<1m' since "freshness ages"
    rarely care about seconds. Pass `sub_minute=True` for TTL displays
    where the exact seconds matter (e.g. 12-factor short-timeout testing
    with `BREW_HOP_SEARCH_STALE_API=2s`).
    """
    if seconds == float("inf"):
        return "never"
    s = int(seconds)
    if s < 60:
        return f"{s}s" if sub_minute else "<1m"
    if s < 3600:
        return f"{s // 60}m"
    h, rem = divmod(s, 3600)
    m = rem // 60
    if h < 24:
        return f"{h}h{m}m" if m else f"{h}h"
    d, h = divmod(h, 24)
    return f"{d}d{h}h" if h else f"{d}d"

# ── colour helpers ───────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty()


def c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


bold = lambda t: c("1", t)
dim = lambda t: c("2", t)
green = lambda t: c("32", t)
yellow = lambda t: c("33", t)
cyan = lambda t: c("36", t)
red = lambda t: c("31", t)
magenta = lambda t: c("35", t)
USE_COLOR_STDERR = sys.stderr.isatty()


def status_line(msg: str, done: bool = False) -> None:
    """Write an in-place status line to stderr (overwrites previous on TTY)."""
    if USE_COLOR_STDERR:
        if done:
            print(f"\r\033[K{msg}", file=sys.stderr)
        else:
            print(f"\r\033[K{msg}", end="", file=sys.stderr, flush=True)
    else:
        if done:
            print(msg, file=sys.stderr)


def trailing_refresh_status(*, verbose: int = 1, max_wait: float = 2.0,
                            poll: float = 0.1) -> None:
    """Briefly poll pending bg refreshes (or ^C). TTY+stderr only.

    Called at the end of main() — after results are printed and stdout
    flushed — when there are background refreshes in flight. Prints an
    "updating …" line, polls each sentinel for up to ``max_wait`` seconds.
    Fast refreshes (typical for `index`, warm `installed`) finish inside
    the grace window and get a ✓/✗ + duration line. Slow ones (cold
    `brew info --json=v2 --installed`) leave a "still updating in
    background" footer and we return to the shell — the bg process owns
    its own session and runs to completion regardless. ^C is also
    treated as "still updating in background".
    """
    from brew_hop_search.cache import pending_refreshes, read_sentinel
    pending = pending_refreshes()
    if not pending:
        return
    if not USE_COLOR_STDERR:
        return  # Non-TTY: don't block pipelines on bg refresh.

    kinds = sorted({k for k, _, _ in pending})
    kinds_str = ",".join(kinds)
    status_line(dim(f"  # [cache] updating {kinds_str} … (^C to skip)"))

    deadline = time.time() + max_wait
    remaining = list(pending)
    results: list[tuple[str, int, bool, str]] = []
    try:
        while remaining and time.time() < deadline:
            still: list[tuple[str, "Path", float]] = []
            for kind, spath, started in remaining:
                r = read_sentinel(spath)
                if r is None:
                    still.append((kind, spath, started))
                else:
                    duration_ms, ok, msg = r
                    results.append((kind, duration_ms, ok, msg))
                    try:
                        spath.unlink()
                    except FileNotFoundError:
                        pass
            remaining = still
            if remaining:
                time.sleep(poll)
    except KeyboardInterrupt:
        status_line(dim(f"  # [cache] {kinds_str} still updating in background"),
                    done=True)
        return

    if remaining:
        # Timed out
        names = ",".join(k for k, _, _ in remaining)
        status_line(dim(f"  # [cache] {names} still updating "
                        f"(>{int(max_wait)}s)"), done=True)
        return

    # All complete — render one final line per kind, in original order.
    by_kind = {k: (d, ok, msg) for k, d, ok, msg in results}
    parts = []
    for k in kinds:
        d, ok, msg = by_kind[k]
        secs = d / 1000.0
        if ok:
            parts.append(f"{k} {green('✓')} {secs:.1f}s")
        else:
            err = f" — {msg}" if msg else ""
            parts.append(f"{k} {red('✗')}{err} {secs:.1f}s")
    status_line(dim(f"  # [cache] {' · '.join(parts)}"), done=True)


def _fmt_entry(name_styled: str, ver: str, desc: str, homepage: str,
               extra: str = "") -> str:
    """Compact one-line format: name  ver  desc  │ url."""
    parts = [name_styled]
    if ver:
        parts.append(dim(ver))
    if extra:
        parts.append(extra)
    if desc:
        parts.append(desc)
    line = "  ".join(parts)
    if homepage:
        line += f"  {dim('│')} {dim(homepage)}"
    return line


def fmt_formula(f: dict) -> str:
    return _fmt_entry(
        bold(green(f["name"])),
        f.get("versions", {}).get("stable", ""),
        f.get("desc", ""),
        f.get("homepage", ""),
    )


def fmt_cask(f: dict) -> str:
    return _fmt_entry(
        bold(cyan(f.get("token", ""))),
        str(f.get("version", "")),
        f.get("desc", ""),
        f.get("homepage", ""),
    )


def fmt_tap_formula(f: dict, show_date: bool = False,
                    show_trust: bool = False) -> str:
    extra_parts = [dim(f.get("tap", ""))]
    if show_date and f.get("modified_at"):
        from datetime import datetime
        ts = datetime.fromtimestamp(f["modified_at"]).strftime("%Y-%m-%d")
        extra_parts.append(dim(ts))
    if show_trust and f.get("trusted") is not None:
        # brew ≥ 6.0 tap trust (sources/taps.fetch_tap_meta). None = unknown
        # (older brew, or tap gone between scan and tap-info) → say nothing.
        if f.get("official"):
            extra_parts.append(dim("official"))
        elif f.get("trusted"):
            extra_parts.append(dim("trusted"))
        else:
            extra_parts.append(red("untrusted"))
    return _fmt_entry(
        bold(magenta(f["name"])),
        f.get("version", ""),
        f.get("desc", ""),
        f.get("homepage", ""),
        extra="  ".join(extra_parts),
    )


def fmt_installed(f: dict, kind: str) -> str:
    """Format an installed formula/cask — same as regular but with installed marker."""
    if kind == "cask":
        base = fmt_cask(f)
    else:
        base = fmt_formula(f)
    return base


def _section_header(label: str, shown: int, total: int | None,
                    install_hint: str = "") -> str:
    """Format a section header: # label (count) • brew install ..."""
    count = f"{shown}/{total}" if total is not None and total > shown else str(shown)
    parts = [f"  {dim('#')} {label} {dim(f'({count})')}"]
    if install_hint:
        parts.append(dim(f"• {install_hint}"))
    return "  ".join(parts)


def _install_cmd(results: list, kind: str) -> str:
    """Derive the install hint from the first result."""
    if not results:
        return ""
    r = results[0]
    name = r.get("token") or r.get("name", "")
    if kind == "cask":
        return f"brew install --cask {name}"
    return f"brew install {name}"


# ── source indicator column ─────────────────────────────────────────────────

_SOURCE_CHARS = {
    "formula": ("f", green),
    "cask": ("c", yellow),
    "tap": ("t", magenta),
    "installed_formula": ("i", green),
    "installed_cask": ("i", yellow),
    "local_formula": ("f", cyan),
    "local_cask": ("c", cyan),
}


def _source_tag(kind: str) -> str:
    """Single-char colored source indicator, or space if unknown."""
    ch, color_fn = _SOURCE_CHARS.get(kind, (" ", lambda x: x))
    if USE_COLOR:
        return color_fn(ch)
    return ch


def display_section(results: list, kind: str, label: str | None = None,
                    quiet: bool = False, total: int | None = None,
                    verbose: int = 1) -> None:
    if not results:
        return
    tag = _source_tag(kind)
    if not quiet:
        if label is None:
            label = yellow("casks") if kind == "cask" else green("formulae")
        print(_section_header(label, len(results), total, _install_cmd(results, kind)))
    fmt = fmt_cask if kind == "cask" else fmt_formula
    if quiet:
        prefix = ""
    elif verbose >= 2:
        prefix = f"  {tag} "
    else:
        prefix = "    "
    for item in results:
        print(f"{prefix}{fmt(item)}")


def display_tap_section(results: list, quiet: bool = False,
                        total: int | None = None,
                        verbose: int = 1) -> None:
    if not results:
        return
    tag = _source_tag("tap")
    if not quiet:
        r = results[0]
        tap = r.get("tap", "")
        name = r.get("name", "")
        hint = f"brew install {tap}/{name}" if tap else ""
        print(_section_header(magenta('taps'), len(results), total, hint))
    if quiet:
        prefix = ""
    elif verbose >= 2:
        prefix = f"  {tag} "
    else:
        prefix = "    "
    show_date = verbose >= 2
    for item in results:
        print(f"{prefix}{fmt_tap_formula(item, show_date=show_date, show_trust=show_date)}")


def display_installed_section(results: list, kind: str, quiet: bool = False,
                              total: int | None = None,
                              verbose: int = 1) -> None:
    if not results:
        return
    full_kind = f"installed_{kind}"
    tag = _source_tag(full_kind)
    if not quiet:
        label = yellow("installed casks") if kind == "cask" else green("installed formulae")
        print(_section_header(label, len(results), total, _install_cmd(results, kind)))
    if quiet:
        prefix = ""
    elif verbose >= 2:
        prefix = f"  {tag} "
    else:
        prefix = "    "
    for item in results:
        print(f"{prefix}{fmt_installed(item, kind)}")


def output_grep(all_results: list[tuple]) -> None:
    for kind, results, *_ in all_results:
        for item in results:
            slug = item.get("token") or item.get("name", "")
            ver = (
                str(item.get("version", ""))
                if kind == "cask"
                else (item.get("versions") or {}).get("stable", "")
            )
            url = item.get("homepage", "")
            desc = item.get("desc") or ""
            print(f"{slug}\t{ver}\t{url}")
            print(f"  {desc}")


# ── multi-line (long) output ─────────────────────────────────────────────────

def output_multi(all_results: list[tuple]) -> None:
    """Multi-line per-result, labeled fields. Reads naturally; greppable.

        formula  python@3.13
          version  3.13.2
          desc     Interpreted, interactive, object-oriented programming language
          url      https://www.python.org/

    Labels are aligned to the widest label across rows. A blank line
    separates entries. Pipes through `grep -A` cleanly.
    """
    rows = _all_rows(all_results)
    if not rows:
        return
    # Per-row: kind label, then fields. Label width is uniform.
    field_order = ("version", "desc", "url")
    label_w = max(len(f) for f in field_order)
    first = True
    for kind, results, *_ in all_results:
        for item in results:
            row = _extract_row(kind, item)
            if not first:
                print()
            first = False
            head_label = (
                "cask" if "cask" in kind else
                "tap" if kind == "tap" else
                "formula"
            )
            print(f"{bold(head_label)}  {bold(row['name'])}")
            for field, val in (
                ("version", row["version"]),
                ("desc", row["description"]),
                ("url", row["homepage"]),
            ):
                if val:
                    print(f"  {dim(field.ljust(label_w))}  {val}")


def _envelope(command: str, results, **meta_fields) -> dict:
    """Wrap results in a self-describing meta envelope.

    Fields with None values are omitted.
    """
    from datetime import datetime, timezone
    meta = {"command": command}
    for k, v in meta_fields.items():
        if v is not None:
            meta[k] = v
    meta["date"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    out = {"meta": meta}
    if isinstance(results, dict):
        out.update(results)
    else:
        out["results"] = results
    return out


def output_json(all_results: list[tuple], *,
                query: str = "", limit: int = 20, offset: int = 0,
                mode: str = "full") -> None:
    count = 0
    sources = []
    total = 0
    for kind, items, *rest in all_results:
        count += len(items)
        sources.append(kind)
        if rest:
            total += rest[-1] or 0  # source_count is last element
    if mode == "short":
        payload = {"results": _all_rows(all_results)}
    else:
        grouped: dict = {}
        for kind, items, *_ in all_results:
            grouped[kind] = items
        payload = {"results": grouped}
    env = _envelope(
        "search",
        payload,
        query=query or None,
        sources=sources,
        mode=mode if mode != "full" else None,
        limit=limit if limit < 999999 else None,
        offset=offset if offset else None,
        total=total if total else None,
        count=count,
    )
    print(json.dumps(env, indent=2))


# ── tabular output formats ─────────────────────────────────────────────────

def _extract_row(kind: str, item: dict) -> dict:
    """Extract a flat row from a search result item.

    Coerces None → "" so downstream formatters (table width, csv, sql)
    never see a null string.
    """
    if "token" in item:
        name = item["token"]
    else:
        name = item.get("name") or ""
    if kind == "cask":
        ver = str(item.get("version") or "")
    else:
        versions = item.get("versions") or {}
        ver = versions.get("stable") or item.get("version") or ""
    return {
        "source": kind.split("_")[-1][0] if "_" in kind else kind[0],
        "name": name or "",
        "version": ver or "",
        "description": item.get("desc") or "",
        "homepage": item.get("homepage") or "",
    }


def _all_rows(all_results: list[tuple]) -> list[dict]:
    rows = []
    for kind, results, *_ in all_results:
        for item in results:
            rows.append(_extract_row(kind, item))
    return rows


def output_csv(all_results: list[tuple]) -> None:
    import csv
    import io
    rows = _all_rows(all_results)
    if not rows:
        return
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["source", "name", "version", "description", "homepage"])
    w.writeheader()
    w.writerows(rows)
    print(buf.getvalue(), end="")


def output_tsv(all_results: list[tuple]) -> None:
    rows = _all_rows(all_results)
    if not rows:
        return
    cols = ["source", "name", "version", "description", "homepage"]
    print("\t".join(cols))
    for r in rows:
        print("\t".join(r.get(c, "") for c in cols))


def output_table(all_results: list[tuple]) -> None:
    """Aligned columns table (like sqlite3 -column)."""
    rows = _all_rows(all_results)
    if not rows:
        return
    cols = ["source", "name", "version", "description", "homepage"]
    headers = {"source": "S", "name": "Name", "version": "Ver",
               "description": "Description", "homepage": "Homepage"}
    # Compute column widths (cap description at 50, homepage at 40)
    caps = {"description": 50, "homepage": 40}
    widths = {}
    for col in cols:
        cap = caps.get(col, 999)
        w = len(headers[col])
        for r in rows:
            w = max(w, min(len(r.get(col, "")), cap))
        widths[col] = w

    def _trunc(s: str, w: int) -> str:
        return s[:w-1] + "…" if len(s) > w else s

    # Header
    hdr = "  ".join(headers[c].ljust(widths[c]) for c in cols)
    sep = "  ".join("-" * widths[c] for c in cols)
    print(hdr)
    print(sep)
    for r in rows:
        line = "  ".join(_trunc(r.get(c, ""), widths[c]).ljust(widths[c]) for c in cols)
        print(line)


def output_sql_insert(all_results: list[tuple]) -> None:
    """SQLite-friendly INSERT statements."""
    rows = _all_rows(all_results)
    if not rows:
        return
    print("CREATE TABLE IF NOT EXISTS results (source TEXT, name TEXT, version TEXT, description TEXT, homepage TEXT);")
    for r in rows:
        vals = ", ".join(
            "'" + r.get(c, "").replace("'", "''") + "'"
            for c in ["source", "name", "version", "description", "homepage"]
        )
        print(f"INSERT INTO results VALUES ({vals});")
