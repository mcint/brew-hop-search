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

import sys
import time
from typing import Any

from brew_hop_search.display import dim


# Module-level recording — populated by Timer / record() during the
# command, drained by render_footer().
_records: list[tuple[str, float]] = []


def record(label: str, elapsed_sec: float) -> None:
    """Append a (label, duration) tuple for inclusion in the footer."""
    _records.append((label, elapsed_sec))


def reset() -> None:
    """Test helper: clear the recorded tuples."""
    _records.clear()


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
    from brew_hop_search.settings import get
    if not get("timing", tool="search"):   # NO_TIMING env / [hop] timing = false
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


def render_footer(elapsed_sec: float) -> str:
    """Build the `# [time] <felt>` line. Color is applied by the caller."""
    return f"# [time] {_fmt_secs(elapsed_sec)}"


def emit_footer(args: Any, elapsed_sec: float, stream=None) -> None:
    """Print the footer to stderr if policy allows."""
    if not should_emit(args):
        return
    line = render_footer(elapsed_sec)
    target = stream if stream is not None else sys.stderr
    print(dim(f"  {line}"), file=target)
