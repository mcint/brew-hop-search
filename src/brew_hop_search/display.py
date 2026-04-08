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


def fmt_tap_formula(f: dict) -> str:
    return _fmt_entry(
        bold(magenta(f["name"])),
        f.get("version", ""),
        f.get("desc", ""),
        f.get("homepage", ""),
        extra=dim(f.get("tap", "")),
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
                    quiet: bool = False, total: int | None = None) -> None:
    if not results:
        return
    tag = _source_tag(kind)
    if not quiet:
        if label is None:
            label = yellow("casks") if kind == "cask" else green("formulae")
        print(_section_header(label, len(results), total, _install_cmd(results, kind)))
    fmt = fmt_cask if kind == "cask" else fmt_formula
    prefix = "" if quiet else f"  {tag} "
    for item in results:
        print(f"{prefix}{fmt(item)}")


def display_tap_section(results: list, quiet: bool = False,
                        total: int | None = None) -> None:
    if not results:
        return
    tag = _source_tag("tap")
    if not quiet:
        r = results[0]
        tap = r.get("tap", "")
        name = r.get("name", "")
        hint = f"brew install {tap}/{name}" if tap else ""
        print(_section_header(magenta('taps'), len(results), total, hint))
    prefix = "" if quiet else f"  {tag} "
    for item in results:
        print(f"{prefix}{fmt_tap_formula(item)}")


def display_installed_section(results: list, kind: str, quiet: bool = False,
                              total: int | None = None) -> None:
    if not results:
        return
    full_kind = f"installed_{kind}"
    tag = _source_tag(full_kind)
    if not quiet:
        label = yellow("installed casks") if kind == "cask" else green("installed formulae")
        print(_section_header(label, len(results), total, _install_cmd(results, kind)))
    prefix = "" if quiet else f"  {tag} "
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


def output_json(all_results: list[tuple]) -> None:
    combined = {}
    for kind, results, *_ in all_results:
        combined[kind] = results
    if len(all_results) == 1:
        combined = combined[all_results[0][0]]
    print(json.dumps(combined, indent=2))
