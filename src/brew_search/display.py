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
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60}s" if s % 60 else f"{s // 60}m"
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


def fmt_formula(f: dict) -> str:
    name = bold(green(f["name"]))
    ver = dim(f.get("versions", {}).get("stable", ""))
    desc = f.get("desc", "")
    homepage = dim(f.get("homepage", ""))
    line1 = f"{name}  {ver}"
    line2 = f"  {desc}"
    line3 = f"  {homepage}" if homepage else ""
    return "\n".join(x for x in [line1, line2, line3] if x)


def fmt_cask(f: dict) -> str:
    name = bold(cyan(f.get("token", "")))
    ver = dim(str(f.get("version", "")))
    desc = f.get("desc", "")
    homepage = dim(f.get("homepage", ""))
    line1 = f"{name}  {ver}"
    line2 = f"  {desc}"
    line3 = f"  {homepage}" if homepage else ""
    return "\n".join(x for x in [line1, line2, line3] if x)


def fmt_tap_formula(f: dict) -> str:
    tap = dim(f.get("tap", ""))
    name = bold(magenta(f["name"]))
    ver = dim(f.get("version", ""))
    desc = f.get("desc", "")
    homepage = dim(f.get("homepage", ""))
    line1 = f"{name}  {ver}  {tap}"
    line2 = f"  {desc}" if desc else ""
    line3 = f"  {homepage}" if homepage else ""
    return "\n".join(x for x in [line1, line2, line3] if x)


def fmt_installed(f: dict, kind: str) -> str:
    """Format an installed formula/cask — same as regular but with installed marker."""
    if kind == "cask":
        base = fmt_cask(f)
    else:
        base = fmt_formula(f)
    return base


def display_section(results: list, kind: str, label: str | None = None) -> None:
    if not results:
        return
    if label is None:
        label = yellow("casks") if kind == "cask" else green("formulae")
    fmt = fmt_cask if kind == "cask" else fmt_formula
    print(f"  {label}")
    print()
    for item in results:
        print(fmt(item))
        print()


def display_tap_section(results: list) -> None:
    if not results:
        return
    print(f"  {magenta('taps')}")
    print()
    for item in results:
        print(fmt_tap_formula(item))
        print()


def display_installed_section(results: list, kind: str) -> None:
    if not results:
        return
    label = yellow("installed casks") if kind == "cask" else green("installed formulae")
    print(f"  {label}")
    print()
    for item in results:
        print(fmt_installed(item, kind))
        print()


def output_grep(all_results: list[tuple]) -> None:
    for kind, results, _ in all_results:
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
    for kind, results, _ in all_results:
        combined[kind] = results
    if len(all_results) == 1:
        combined = combined[all_results[0][0]]
    print(json.dumps(combined, indent=2))
