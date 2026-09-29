# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""`brew-hop`: the git-style dispatcher behind `brew hop <verb>`.

Homebrew runs any `brew-<name>` on PATH as `brew <name>` (since 2010), so
`brew hop search python` reaches us with argv = ["search", "python"]. We
exec `brew-hop-<verb>` — next to this binary first, then PATH — with the
rest of argv untouched, falling back to importing the verb's entry point
in-process. Verbs are independent programs; this file only routes.

brew filters the environment to HOMEBREW_* before exec'ing us, so we
promote HOMEBREW_HOP_<X> to BREW_HOP_<X> (and back) for the child: a tool
may read either name and see the same value.
Spec: docs/specs/drafts/config-layers.md § `brew hop` dispatch.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Verb:
    name: str
    entry: str | None      # "pkg.module:function" for in-process fallback
    feature: str | None    # feature that must be on, or None
    doc: str


VERBS: tuple[Verb, ...] = (
    Verb("search", "brew_hop_search.cli:main", None, "search formulae, casks, taps, installed"),
    Verb("peek", None, "peek", "list an untapped tap from GitHub (brew-hop-peek)"),
)
_BY_NAME = {v.name: v for v in VERBS}


def promote_env(environ: dict) -> dict:
    """Copy each HOMEBREW_HOP_<X> to BREW_HOP_<X> when unset, and back."""
    env = dict(environ)
    for name, val in environ.items():
        if name.startswith("HOMEBREW_HOP_"):
            twin = "BREW_HOP_" + name[len("HOMEBREW_HOP_"):]
        elif name.startswith("BREW_HOP_"):
            twin = "HOMEBREW_HOP_" + name[len("BREW_HOP_"):]
        else:
            continue
        env.setdefault(twin, val)
    return env


def find_executable(verb: str, argv0_dir: str) -> str | None:
    name = f"brew-hop-{verb}"
    local = os.path.join(argv0_dir, name)
    if os.access(local, os.X_OK):
        return local
    return shutil.which(name)


def _import_entry(entry: str):
    mod, fn = entry.split(":")
    return getattr(importlib.import_module(mod), fn)


def _list_verbs(stream) -> None:
    from brew_hop_search.features import feature_on
    print("usage: brew hop <verb> [args…]      (or brew-hop, brew-hop-<verb>)", file=stream)
    print("", file=stream)
    width = max(len(v.name) for v in VERBS)
    for v in VERBS:
        tag = ""
        if v.feature:
            tag = f"  (experimental, {'on' if feature_on(v.feature) else 'off'})"
        print(f"  {v.name.ljust(width)}  {v.doc}{tag}", file=stream)
    print("", file=stream)
    print("  --help=features on any verb explains experiments", file=stream)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        _list_verbs(sys.stdout)
        return 0
    name, rest = argv[0], argv[1:]
    verb = _BY_NAME.get(name)
    if verb is None:
        print(f"brew hop: unknown verb: {name}", file=sys.stderr)
        _list_verbs(sys.stderr)
        return 2
    if verb.feature:
        from brew_hop_search.features import feature_on, enable_hint
        if not feature_on(verb.feature, tool=verb.name):
            print(f"brew hop {name}: " + enable_hint(verb.feature), file=sys.stderr)
            return 2
    env = promote_env(os.environ)
    exe = find_executable(name, os.path.dirname(os.path.abspath(sys.argv[0])))
    if exe:
        os.execve(exe, [exe, *rest], env)   # does not return
    if verb.entry is None:
        print(f"brew hop {name}: brew-hop-{name} is not installed", file=sys.stderr)
        return 2
    os.environ.update(env)
    fn = _import_entry(verb.entry)
    result = fn(rest)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
