# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The honest footer: total · cache · api(n) · refresh.

`# [time] 0.134s` beside a shell `time` of 2.7 s was accurate for main()
and silent about everything else. The footer now reports wall clock from
the package's first import (within ~10 ms of process start), the time
spent in the local database, the count and time of foreground HTTP
requests, and whether a background refresh was left running. Spec:
docs/specs/features/timing.md.
"""
from __future__ import annotations

import time

import pytest

from brew_hop_search import timing


@pytest.fixture(autouse=True)
def _clean():
    timing.reset()
    yield
    timing.reset()


def test_render_cache_only():
    line = timing.render_footer(total=0.213, cache=0.012, api=(0, 0.0), refresh=None)
    assert line == "# [time] total 0.213s · cache 0.012s · api(0) —"


def test_render_with_api_and_bg_refresh():
    line = timing.render_footer(total=3.321, cache=0.512, api=(1, 2.503), refresh="bg")
    assert line == "# [time] total 3.321s · cache 0.512s · api(1) 2.503s · refresh bg"


def test_render_refresh_finished_inside_grace():
    line = timing.render_footer(total=2.4, cache=0.1, api=(0, 0.0), refresh="1.9s")
    assert line.endswith("· refresh 1.9s")


def test_counters_feed_the_summary():
    with timing.Timer("cache"):
        time.sleep(0.01)
    with timing.Timer("cache"):
        pass
    timing.record_api(0.4)
    timing.record_api(0.6)
    timing.note_refresh("bg")
    s = timing.summary()
    assert s["cache"] >= 0.01
    assert s["api"] == (2, pytest.approx(1.0))
    assert s["refresh"] == "bg"


def test_reset_clears_everything():
    timing.record_api(1.0)
    timing.note_refresh("bg")
    with timing.Timer("cache"):
        pass
    timing.reset()
    assert timing.summary() == {"cache": 0.0, "api": (0, 0.0), "refresh": None}


def test_process_start_predates_now():
    t0 = timing.process_start()
    assert isinstance(t0, float)
    assert t0 <= time.monotonic()


def test_emit_uses_recorded_counters(monkeypatch):
    import io
    import types
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    args = types.SimpleNamespace(quiet=False, no_timing=False, verbose=1,
                                 help_full=None, help_short=None, man=False,
                                 version=0, _bg_refresh=None)
    timing.record_api(0.25)
    with timing.Timer("cache"):
        pass
    out = io.StringIO()
    timing.emit_footer(args, 1.5, stream=out)
    text = out.getvalue()
    assert "total 1.500s" in text
    assert "api(1) 0.250s" in text
    assert "refresh" not in text
