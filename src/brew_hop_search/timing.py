# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Per-command timing footer.

A one-line `# [time] <felt>` stderr footer written at end of `cli.main()`
so users can see whether a command was fast (cache hit, sub-100ms) or
doing real work (cold cache, subprocess, network fetch). See
`docs/specs/drafts/timing.md` for the full design.

v1 here is intentionally narrow: total foreground wall-clock only. Per-
source breakdown (`· installed:f 0.012s …`) and the bg-refresh
parenthetical (`(+5.7s refresh)`) are followups; the Timer/record
scaffolding below is here so they slot in without a rewrite.
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

from brew_hop_search.display import dim


# Module-level recording — populated by Timer / record() during the
# command, drained by emit_footer().
_records: list[tuple[str, float]] = []
_api: list[float] = []          # one entry per foreground HTTP request
_refresh: str | None = None     # "bg", "1.9s", or None


def record(label: str, elapsed_sec: float) -> None:
    """Append a (label, duration) tuple for inclusion in the footer."""
    _records.append((label, elapsed_sec))


def record_api(elapsed_sec: float) -> None:
    """One foreground HTTP request took this long (index fetch, PyPI check)."""
    _api.append(elapsed_sec)


def note_refresh(state: str | None) -> None:
    """Background refresh state for the footer: "bg" when one was started and
    left running, "<secs>s" when the grace poll saw it finish, None if none."""
    global _refresh
    _refresh = state


def process_start() -> float:
    """Monotonic instant of the package's first import (see __init__._T0).
    Falls back to now if the package was imported some other way."""
    import brew_hop_search
    return getattr(brew_hop_search, "_T0", time.monotonic())


def summary() -> dict:
    """What the footer reports besides total: cache seconds, (api count,
    api seconds), refresh state."""
    cache = sum(d for label, d in _records if label == "cache")
    return {"cache": cache, "api": (len(_api), sum(_api)), "refresh": _refresh}


def reset() -> None:
    """Test helper: clear every recorder."""
    _records.clear()
    _api.clear()
    note_refresh(None)


class Timer:
    """Context manager that records its scope's wall-clock time.

        with Timer("installed:f"):
            ...

    The `(label, elapsed)` tuple lands in the module recorder via
    `record()`. Cheap — adds <10µs per scope.
    """
    def __init__(self, label: str):
        self.label = label
        self.start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.monotonic()
        return self

    def __exit__(self, *exc: Any) -> bool:
        self.elapsed = time.monotonic() - self.start
        record(self.label, self.elapsed)
        return False  # don't swallow exceptions


def _fmt_secs(s: float) -> str:
    """Compact duration: 0.034s, 1.234s, 12.3s, 1m02s."""
    if s < 60:
        return f"{s:.3f}s" if s < 10 else f"{s:.2f}s"
    m, rem = divmod(s, 60)
    return f"{int(m)}m{int(rem):02d}s"


def should_emit(args: Any) -> bool:
    """Policy: whether to print the `# [time]` line for this invocation.

    See `docs/specs/drafts/timing.md` for the table; this function is
    the executable spec.
    """
    if getattr(args, "quiet", False):
        return False
    if getattr(args, "no_timing", False):
        return False
    if os.environ.get("BREW_HOP_SEARCH_NO_TIMING"):
        return False
    # Help and version paths are info-only; the wall-clock isn't
    # interesting and would clutter the help screen.
    if getattr(args, "help_full", None) is not None:
        return False
    if getattr(args, "help_short", None) is not None:
        return False
    if getattr(args, "man", False):
        return False
    if getattr(args, "version", 0):
        return False
    # Background refresh subprocess (-bg-refresh) writes its own sentinel;
    # no footer needed there.
    if getattr(args, "_bg_refresh", None):
        return False
    verbose = getattr(args, "verbose", 0)
    if verbose >= 1:
        return True  # `-v` and up: always show
    # Default level: only on a TTY stderr (script logs stay clean).
    return sys.stderr.isatty()


def render_footer(*, total: float, cache: float, api: tuple[int, float],
                  refresh: str | None) -> str:
    """Build the footer line. Color is applied by the caller.

        # [time] total 0.213s · cache 0.012s · api(0) —
        # [time] total 3.321s · cache 0.512s · api(1) 2.503s · refresh bg

    `total` is wall clock from the first import; `cache` the time inside
    the local database; `api(n)` the count and summed time of foreground
    HTTP requests; `refresh` present only when a background refresh ran.
    """
    n, secs = api
    api_part = f"api({n}) {_fmt_secs(secs)}" if n else "api(0) —"
    parts = [f"total {_fmt_secs(total)}", f"cache {_fmt_secs(cache)}", api_part]
    if refresh:
        parts.append(f"refresh {refresh}")
    return "# [time] " + " · ".join(parts)


def emit_footer(args: Any, total_sec: float, stream=None) -> None:
    """Print the footer to stderr if policy allows."""
    if not should_emit(args):
        return
    s = summary()
    line = render_footer(total=total_sec, cache=s["cache"], api=s["api"],
                         refresh=s["refresh"])
    target = stream if stream is not None else sys.stderr
    print(dim(f"  {line}"), file=target)
