# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Witness mtimes: a cheap hint that brew changed something since we indexed.

Every offline source names a handful of *witness paths* — directories (or
one file) whose mtime moves whenever brew mutates that source:

  installed  <prefix>/opt, Cellar, Caskroom    install/upgrade/remove relink
                                               under opt/; casks land in Caskroom/
  taps       Library/Taps, each user/tap dir,  `brew tap`/`untap` touch the
             each tap's .git/FETCH_HEAD        parents; `brew update` touches
                                               FETCH_HEAD
  local      <cache>/api, api/formula, api/cask  brew writes per-formula JSON there
  index      (none — remote; TTL only)

The max mtime over the existing witnesses is stamped into `_meta.witness`
at index time. A later read stats the same paths (~1–100 stats, no
subprocess) and, if the live max is newer than the stamp, treats the
source as stale — which takes the normal *background* refresh path, never
a blocking one. TTL remains the fallback for anything a witness can't see.

Roots come from HOMEBREW_PREFIX / HOMEBREW_REPOSITORY / HOMEBREW_CACHE when
set, else from the location of the `brew` binary and platform defaults.
No `brew` subprocess is ever spawned here: the whole point is to be cheaper
than asking brew.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import sqlite_utils

# DB table → witness kind. Tables not listed (formula, cask) have no witness.
TABLE_KIND: dict[str, str] = {
    "installed_formula": "installed",
    "installed_cask": "installed",
    "tap": "taps",
    "local_formula": "local",
    "local_cask": "local",
}


# ── root discovery ─────────────────────────────────────────────────────────

def _prefix() -> Path | None:
    env = os.environ.get("HOMEBREW_PREFIX")
    if env:
        return Path(env)
    brew = shutil.which("brew")
    if brew:
        return Path(brew).resolve().parent.parent
    for cand in ("/opt/homebrew", "/usr/local", "/home/linuxbrew/.linuxbrew"):
        if Path(cand, "bin", "brew").exists():
            return Path(cand)
    return None


def _repository() -> Path | None:
    env = os.environ.get("HOMEBREW_REPOSITORY")
    if env:
        return Path(env)
    prefix = _prefix()
    if prefix is None:
        return None
    # Apple Silicon: repo == prefix. Intel / Linux: prefix/Homebrew.
    if (prefix / "Library" / "Taps").is_dir():
        return prefix
    return prefix / "Homebrew"


def _cache() -> Path:
    env = os.environ.get("HOMEBREW_CACHE")
    if env:
        return Path(env)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "Homebrew"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg) / "Homebrew" if xdg else Path.home() / ".cache" / "Homebrew"


# ── witness paths ──────────────────────────────────────────────────────────

def witness_paths(kind: str) -> list[Path]:
    """The paths whose mtimes stand witness for `kind`. May include paths
    that don't exist yet (e.g. no Caskroom on a formula-only install)."""
    if kind == "installed":
        p = _prefix()
        return [] if p is None else [p / "opt", p / "Cellar", p / "Caskroom"]
    if kind == "local":
        api = _cache() / "api"
        return [api, api / "formula", api / "cask"]
    if kind == "taps":
        repo = _repository()
        if repo is None:
            return []
        taps = repo / "Library" / "Taps"
        out = [taps]
        if taps.is_dir():
            for user in sorted(taps.iterdir()):
                if not user.is_dir():
                    continue
                for tap in sorted(user.iterdir()):
                    if not tap.is_dir():
                        continue
                    out.append(tap)
                    fh = tap / ".git" / "FETCH_HEAD"
                    if fh.exists():
                        out.append(fh)
        return out
    return []


def witness_mtime(kind: str) -> float | None:
    """Max st_mtime over the existing witness paths; None if none exist."""
    best: float | None = None
    for p in witness_paths(kind):
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if best is None or m > best:
            best = m
    return best


# ── DB side ────────────────────────────────────────────────────────────────

def stored_witness(db: sqlite_utils.Database, table: str) -> float | None:
    """The witness stamped into `_meta` when `table` was last imported."""
    if "_meta" not in db.table_names():
        return None
    try:
        row = db["_meta"].get(table)
    except Exception:
        return None
    val = row.get("witness")
    return float(val) if val is not None else None


def changed(db: sqlite_utils.Database, table: str) -> bool:
    """True iff a witness moved since `table` was indexed.

    Unknown is not changed: a NULL stamp (pre-witness DB, or a source with
    no discoverable roots) and a vanished witness both return False, so we
    never thrash on a refresh that can't learn anything new.
    """
    kind = TABLE_KIND.get(table)
    if kind is None:
        return False
    stored = stored_witness(db, table)
    if stored is None:
        return False
    current = witness_mtime(kind)
    if current is None:
        return False
    # Millisecond resolution: brew never mutates twice within 1ms, and it
    # shields the compare from any float→text→float drift in storage.
    return current - stored > 1e-3


def state(db: sqlite_utils.Database, table: str) -> dict:
    """Everything -C / the JSON envelope want to say about a table's witness."""
    kind = TABLE_KIND.get(table)
    if kind is None:
        return {"kind": None, "stored": None, "current": None,
                "changed": False, "paths": []}
    return {
        "kind": kind,
        "stored": stored_witness(db, table),
        "current": witness_mtime(kind),
        "changed": changed(db, table),
        "paths": [str(p) for p in witness_paths(kind)],
    }
