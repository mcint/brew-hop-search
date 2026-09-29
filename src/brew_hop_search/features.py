# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Experimental surfaces, off by default, outside the 1.0 promise.

    BREW_HOP_FEATURES=peek,clock       # the list (family scope; HOMEBREW_HOP_ twin)
    BREW_HOP_FEATURE_PEEK=1            # per-feature alias, brew's one-var shape
    [hop] features = ["peek"]          # config

Brew itself has no feature list (one var per feature); the list is a
deliberate departure — one string to paste, quote, and diff — with the
per-feature alias kept for people who prefer brew's shape.
Spec: docs/specs/drafts/config-layers.md § Features.
"""
from __future__ import annotations

import os
import sys

from brew_hop_search.settings import FALSY, resolve

KNOWN_FEATURES: dict[str, str] = {
    "clock": "clock-style durations: `updated -0:40:12 ttl +5:19:48` (same as duration=clock)",
    "peek": "brew hop peek — list an untapped tap from GitHub (brew-hop-peek)",
}

_ALIAS_PREFIXES = ("BREW_HOP_FEATURE_", "HOMEBREW_HOP_FEATURE_")


def _from_aliases() -> set[str]:
    out: set[str] = set()
    for name, val in os.environ.items():
        for p in _ALIAS_PREFIXES:
            if name.startswith(p) and val and val.strip().lower() not in FALSY:
                out.add(name[len(p):].lower())
    return out


def features_enabled(tool: str = "search") -> set[str]:
    listed = {f.lower() for f in resolve("features", tool).value}
    return listed | _from_aliases()


def unknown_features(tool: str = "search") -> list[str]:
    return sorted(f for f in features_enabled(tool) if f not in KNOWN_FEATURES)


def feature_on(name: str, tool: str = "search") -> bool:
    return name.lower() in features_enabled(tool)


def enable_hint(name: str) -> str:
    return (f"{name} is experimental — enable it with BREW_HOP_FEATURES={name}\n"
            f"(under `brew hop`: HOMEBREW_HOP_FEATURES={name}; or [hop] features in config)")


def require_feature(name: str, tool: str = "search", prog: str = "") -> None:
    if feature_on(name, tool):
        return
    prefix = f"{prog}: " if prog else ""
    print(prefix + enable_hint(name), file=sys.stderr)
    sys.exit(2)
