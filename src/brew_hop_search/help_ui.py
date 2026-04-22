# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Help UI: terse -h, full --help, --man, and -h/--help=MODE scoped help.

See `docs/specs/drafts/help-modes.md` for the surface + `claude-collab/help-ux.md`
for the cross-project pattern rationale.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from brew_hop_search.display import bold, dim


# ── man page rendering ──────────────────────────────────────────────────────

def _man_markdown_path() -> Path | None:
    """Locate the packaged man-page markdown, or the dev-tree copy."""
    try:
        from importlib.resources import files
        p = files("brew_hop_search").joinpath("data", "brew-hop-search.1.md")
        if p.is_file():
            return Path(str(p))
    except Exception:
        pass
    # Dev-tree fallback: running from the repo without a build.
    here = Path(__file__).resolve().parent
    for candidate in (
        here / "data" / "brew-hop-search.1.md",
        here.parent.parent.parent / "docs" / "brew-hop-search.1.md",
    ):
        if candidate.is_file():
            return candidate
    return None


def show_man() -> int:
    """Render the packaged man-page markdown via $PAGER (TTY) or stdout (pipe)."""
    path = _man_markdown_path()
    if path is None:
        print("✗ man page not found — install may be incomplete", file=sys.stderr)
        return 1
    content = path.read_text()
    if not sys.stdout.isatty():
        sys.stdout.write(content)
        return 0
    pager = os.environ.get("MANPAGER") or os.environ.get("PAGER") or "less -R"
    try:
        p = subprocess.Popen(pager, shell=True, stdin=subprocess.PIPE, text=True)
        assert p.stdin is not None
        p.stdin.write(content)
        p.stdin.close()
        return p.wait()
    except Exception:
        sys.stdout.write(content)
        return 0


# ── terse help ──────────────────────────────────────────────────────────────

def _usage_header(parser: argparse.ArgumentParser) -> None:
    """Shared top block: usage, --help pointer (aligned), description."""
    usage = parser.format_usage().strip().replace("usage: ", "")
    # Align the --help hint's command under the command in the usage line.
    indent = " " * len("  usage: ")
    print(f"  usage: {usage}")
    print(f"{indent}brew-hop-search --help      {dim('(for full help)')}")
    print(f"  {dim(parser.description or '')}")


def show_terse(parser: argparse.ArgumentParser) -> None:
    """Compact synopsis + top examples + pointers to richer help."""
    _usage_header(parser)
    print()
    print(f"  {bold('quick examples:')}")
    print(f"    brew-hop-search python               {dim('# formulae + casks (top 20)')}")
    print(f"    brew-hop-search python -n 50         {dim('# top 50; -n 0 = all, -n 20+20 = page 2')}")
    print(f"    brew-hop-search -i                   {dim('# installed packages')}")
    print(f"    brew-hop-search -O                   {dim('# outdated')}")
    print(f"    brew-hop-search -q foo | fzf        {dim('# pipe to fzf')}")
    print()
    print(f"  {bold('info:')}    -C {dim('cache status')}  ·  -V {dim('version')}  ·  -VV {dim('verbose & latest')}")
    print()
    print(f"  {bold('more help:')}")
    print(f"    --help={dim('<section>')}      e.g. --help=sources, --help=output")
    print(f"    --help={dim('<flag>')}          e.g. --help=-c, --help=outdated")
    print(f"    --man                  offline man page")


def show_contextual(parser: argparse.ArgumentParser, flag_tokens: list[str]) -> int:
    """Echo the flags in use and explain each one.

    Triggered by `brew-hop-search -h <flag> [<flag>...]`. Reuses the terse
    header; replaces quick examples with line-per-flag explanations.
    """
    _usage_header(parser)
    print(f"  {bold('parsed:')} {' '.join(flag_tokens)}")
    print()

    # Resolve each token to an action, in the order the user typed them.
    # Accepts `-n0`, `--limit=50`, and `-VV` by stripping the value/repeat
    # suffix and matching the flag stem.
    rows: list[tuple[str, str]] = []
    for tok in flag_tokens:
        match = _find_flag_action(parser, tok)
        if match is None:
            rows.append((tok, dim("(unknown flag)")))
        else:
            opts = ", ".join(match.option_strings) or match.dest
            rows.append((opts, match.help or ""))

    width = max((len(opts) for opts, _ in rows), default=0)
    for opts, desc in rows:
        print(f"    {bold(opts.ljust(width))}  {desc}")

    print()
    print(f"  {bold('more help:')}")
    print(f"    --help={dim('<section>')}      e.g. --help=sources, --help=output")
    print(f"    --man                  offline man page")
    return 0


# ── scoped help: sections + individual flags ────────────────────────────────

def _group_by_title(parser: argparse.ArgumentParser, title: str):
    """Find an argparse group whose title starts with `title` (case-insensitive)."""
    want = title.lower()
    for g in parser._action_groups:
        gt = (g.title or "").lower()
        if gt.startswith(want) or want in gt:
            return g
    return None


def _find_flag_action(parser: argparse.ArgumentParser, tok: str):
    """Resolve an argv flag token to its argparse Action.

    Handles `--long=value`, `-xVALUE` (e.g. `-n0`), and repeated short flags
    (e.g. `-VV` matches `-V`). Returns None if no action matches.
    """
    def _visible_actions():
        return [a for a in parser._actions if a.help != argparse.SUPPRESS]

    # Exact match
    for a in _visible_actions():
        if tok in a.option_strings:
            return a
    # --long=value → --long
    if "=" in tok:
        head = tok.split("=", 1)[0]
        for a in _visible_actions():
            if head in a.option_strings:
                return a
    # -xVALUE or -xx… → -x (short flag with appended value or repetition)
    if len(tok) > 2 and tok.startswith("-") and not tok.startswith("--"):
        short = tok[:2]
        for a in _visible_actions():
            if short in a.option_strings:
                return a
    return None


def _action_matches(action, key: str) -> bool:
    """Does an argparse action's option-strings or dest match `key`?"""
    key = key.lstrip("-")
    for s in action.option_strings:
        if s.lstrip("-") == key:
            return True
    if action.dest == key:
        return True
    return False


def show_scoped(parser: argparse.ArgumentParser, mode: str) -> int:
    """Show help scoped to `mode` (section name or flag letter/name).

    Resolution order: section title → flag option-string / dest →
    error with did-you-mean.
    """
    # Section?
    group = _group_by_title(parser, mode)
    if group is not None:
        print(f"  {bold(group.title or mode)}")
        if group.description:
            print(f"  {dim(group.description)}")
        print()
        for action in group._group_actions:
            if action.help == argparse.SUPPRESS:
                continue
            opts = ", ".join(action.option_strings) or action.dest
            help_text = action.help or ""
            print(f"    {bold(opts)}")
            if help_text:
                print(f"      {help_text}")
        return 0

    # Flag?
    for action in parser._actions:
        if action.help == argparse.SUPPRESS:
            continue
        if _action_matches(action, mode):
            opts = ", ".join(action.option_strings) or action.dest
            print(f"  {bold(opts)}")
            if action.help:
                print(f"    {action.help}")
            # Hint at related group
            for g in parser._action_groups:
                if action in g._group_actions and g.title:
                    print(f"    {dim(f'(in section: {g.title})')}")
                    break
            return 0

    # Neither — suggest
    sections = {(g.title or "").split()[0].lower()
                for g in parser._action_groups if g.title}
    sections.discard("")
    print(f"✗ unknown help mode: {mode!r}", file=sys.stderr)
    print(f"  known sections: {', '.join(sorted(sections))}", file=sys.stderr)
    print(f"  or pass a flag letter/name (e.g. -c, cask, outdated, --help)",
          file=sys.stderr)
    return 2


# ── argv preprocessing ──────────────────────────────────────────────────────

def normalize_argv(argv: list[str]) -> list[str]:
    """Rewrite `-h=X` → `-h X` so argparse's nargs='?' picks up the value.

    `--help=X` passes through — argparse handles long-form = natively.
    """
    out: list[str] = []
    for a in argv:
        if a.startswith("-h=") and len(a) > 3:
            out.extend(["-h", a[3:]])
        else:
            out.append(a)
    return out
