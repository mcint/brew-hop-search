"""Output formatters: TTY, grep, JSON."""
from __future__ import annotations

import json
import sys


# ── duration formatting ──────────────────────────────────────────────────────

def fmt_duration(seconds: float) -> str:
    if seconds == float("inf"):
        return "never"
    s = int(seconds)
    if s < 60:
        return "<1m"
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


def fmt_tap_formula(f: dict, show_date: bool = False) -> str:
    extra_parts = [dim(f.get("tap", ""))]
    if show_date and f.get("modified_at"):
        from datetime import datetime
        ts = datetime.fromtimestamp(f["modified_at"]).strftime("%Y-%m-%d")
        extra_parts.append(dim(ts))
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
        print(f"{prefix}{fmt_tap_formula(item, show_date=show_date)}")


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
    """Extract a flat row from a search result item."""
    if "token" in item:
        name = item["token"]
    else:
        name = item.get("name", "")
    if kind == "cask":
        ver = str(item.get("version", ""))
    else:
        ver = (item.get("versions") or {}).get("stable", item.get("version", ""))
    return {
        "source": kind.split("_")[-1][0] if "_" in kind else kind[0],
        "name": name,
        "version": ver,
        "description": item.get("desc", ""),
        "homepage": item.get("homepage", ""),
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
