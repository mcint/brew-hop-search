# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Brew version detection and feature gating.

Homebrew grows new surface every major (tap trust JSON in 6.0, `brew
vulns` / `brew doctor --json` / `brew list --no-installed-on-request` in
7.0). Features built on that surface must degrade *visibly* on older
installs — skipped, and said so — rather than fail or silently no-op.

Resolution order for the version, cheapest first:

    $BREW_HOP_SEARCH_BREW_VERSION  →  _meta cache (TTL)  →  `brew --version`

The env override is the 12-factor test hook, matching `STALE_*`. The
cache lives in the `_meta` table under kind ``brew_version`` so a single
`brew --version` subprocess (~150 ms) is amortized across invocations.

The FEATURES table is the seed of a brew-operations model: one place that
says which brew capability needs which version. Keep it a dict until a
third consumer wants a schema (see sessions/2026-09-13-requests.md § C3).
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass

Version = "tuple[int, int, int]"

# Feature name → minimum brew version. Sources:
# docs/research/2026-09-13-brew-7-features.md § 2.
FEATURES: dict[str, tuple[int, int, int]] = {
    "tap-info-trusted": (6, 0, 0),            # `brew tap-info --json=v1` has `trusted`
    "trust-json": (6, 0, 0),                  # `brew trust --json=v1`
    "list-no-installed-on-request": (7, 0, 0),
    "doctor-json": (7, 0, 0),
    "vulns": (7, 0, 0),
    "deps-brewfile": (7, 0, 0),
    "advisories-json": (7, 0, 0),             # formulae.brew.sh/api/advisories.json
}

_META_KIND = "brew_version"
_CACHE_TTL = 6 * 3600  # brew upgrades itself rarely; -C --refresh forces
_VERSION_RE = re.compile(r"Homebrew\s+>?=?\s*(\d+)\.(\d+)\.(\d+)")


def parse_brew_version(text: str) -> tuple[int, int, int] | None:
    """'Homebrew 7.0.1-3-g67f689a\\n…' → (7, 0, 1). None if unparseable."""
    m = _VERSION_RE.search(text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def format_version(v: tuple[int, int, int] | None) -> str:
    return ".".join(str(n) for n in v) if v else "unknown"


def _from_env() -> tuple[int, int, int] | None:
    raw = os.environ.get("BREW_HOP_SEARCH_BREW_VERSION")
    if not raw:
        return None
    return parse_brew_version(f"Homebrew {raw.strip()}")


def _run_brew_version() -> tuple[int, int, int] | None:
    try:
        r = subprocess.run(["brew", "--version"], capture_output=True,
                           text=True, timeout=10)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return parse_brew_version(r.stdout)


def _read_cache():
    from brew_hop_search.cache import get_db
    db = get_db()
    if "_meta" not in db.table_names():
        return None
    try:
        row = db["_meta"].get(_META_KIND)
    except Exception:
        return None
    if time.time() - float(row.get("updated_at") or 0) > _CACHE_TTL:
        return None
    return parse_brew_version(f"Homebrew {row.get('value') or ''}")


def _write_cache(v: tuple[int, int, int] | None) -> None:
    from brew_hop_search.cache import get_db
    try:
        get_db()["_meta"].insert(
            {"kind": _META_KIND, "updated_at": time.time(), "count": 0,
             "value": format_version(v) if v else ""},
            pk="kind", replace=True, alter=True,
        )
    except Exception:
        pass  # a cache miss is never worth failing the command


def brew_version(force: bool = False) -> tuple[int, int, int] | None:
    """Installed brew version as a tuple, or None when brew is unavailable.

    `force=True` bypasses the _meta cache (used by `-C --refresh`).
    """
    env_v = _from_env()
    if env_v is not None:
        return env_v
    if not force:
        cached = _read_cache()
        if cached is not None:
            return cached
    v = _run_brew_version()
    if v is not None:
        _write_cache(v)
    return v


# ── feature gate + skip registry ───────────────────────────────────────────

@dataclass(frozen=True)
class Skipped:
    feature: str
    needs: tuple[int, int, int]
    have: tuple[int, int, int] | None

    def line(self) -> str:
        return (f"skipped {self.feature}: needs brew {format_version(self.needs)}, "
                f"have {format_version(self.have)}")


_skipped: list[Skipped] = []


def supports(feature: str) -> bool:
    """True when the installed brew is new enough for `feature`.

    Unknown feature names raise KeyError — that is a programming error, not
    a runtime condition. A False result is recorded so the CLI can report
    what was skipped at the end of the run (`skipped_report()`).
    """
    needs = FEATURES[feature]
    have = brew_version()
    if have is not None and have >= needs:
        return True
    entry = Skipped(feature, needs, have)
    if entry not in _skipped:
        _skipped.append(entry)
    return False


def skipped() -> list[Skipped]:
    return list(_skipped)


def skipped_report() -> list[str]:
    return [s.line() for s in _skipped]


def reset_skipped() -> None:
    _skipped.clear()


def feature_table(have: tuple[int, int, int] | None = None) -> dict[str, bool]:
    """{feature: available?} for every known feature, without recording skips."""
    if have is None:
        have = brew_version()
    return {f: (have is not None and have >= needs) for f, needs in FEATURES.items()}
