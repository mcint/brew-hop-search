# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Detached background refresh for the offline sources (installed, taps, local).

One runner for all three so a stale source — by TTL *or* by a moved
witness mtime — never blocks the foreground. The API index keeps its own
runner (`cli --_bg-refresh`) because it carries a URL.

Foreground: `background_refresh(kind)` spawns
`python -m brew_hop_search.sources._bg <kind>` in its own session, passing
a sentinel path via BHS_REFRESH_SENTINEL, and registers it so
`display.trailing_refresh_status` can poll for completion.

Background (`__main__`): run the source's `refresh(silent=True)`, write the
sentinel (duration, ok/fail, message), append to refresh.log.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from brew_hop_search.cache import (
    sentinel_path, register_pending_refresh, write_sentinel, append_refresh_log,
)


def _refreshers() -> dict[str, Callable[[], bool]]:
    # Imported lazily: the sources import this module for background_refresh.
    from brew_hop_search.sources import installed, taps, local
    return {
        "installed": lambda: installed.refresh(silent=True, timeout=installed._BG_TIMEOUT),
        "taps": lambda: taps.refresh(silent=True),
        "local": lambda: local.refresh(silent=True),
    }


KINDS = ("installed", "taps", "local")


def background_refresh(kind: str) -> None:
    """Spawn a detached refresh of `kind`. Returns immediately; never raises."""
    try:
        spath = sentinel_path(kind, os.getpid())
        try:
            spath.unlink()
        except FileNotFoundError:
            pass
        env = {**os.environ, "BHS_REFRESH_SENTINEL": str(spath)}
        subprocess.Popen(
            [sys.executable, "-m", "brew_hop_search.sources._bg", kind],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        register_pending_refresh(kind, spath)
    except Exception:
        pass


def main(argv: list[str]) -> int:
    kind = argv[1] if len(argv) > 1 else ""
    sentinel = os.environ.get("BHS_REFRESH_SENTINEL")
    start = time.time()
    err = ""
    fn = _refreshers().get(kind)
    if fn is None:
        ok, err = False, f"unknown refresh kind: {kind!r}"
    else:
        try:
            ok = bool(fn())
        except Exception as e:  # the sentinel is the only channel back
            ok, err = False, str(e)[:200]
    duration_ms = int((time.time() - start) * 1000)
    if sentinel:
        try:
            write_sentinel(Path(sentinel), duration_ms, ok, err)
        except Exception:
            pass
    append_refresh_log(kind or "?", duration_ms, ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
