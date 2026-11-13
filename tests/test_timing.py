# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for the per-command timing footer (`# [time] <felt>`).

Covers:
- _fmt_secs format ladder (sub-second, single-digit, two-digit, minutes)
- should_emit policy table from docs/specs/drafts/timing.md
- emit_footer output and suppression
- Timer/record scaffolding round-trip
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _reset_records():
    """Each test gets a clean recorder."""
    from brew_hop_search.timing import reset
    reset()
    yield
    reset()


# ── _fmt_secs ────────────────────────────────────────────────────────────────

def test_fmt_secs_sub_second_uses_ms_precision():
    from brew_hop_search.timing import _fmt_secs
    assert _fmt_secs(0.034) == "0.034s"
    assert _fmt_secs(0.001) == "0.001s"


def test_fmt_secs_single_digit_uses_three_decimals():
    from brew_hop_search.timing import _fmt_secs
    assert _fmt_secs(1.234) == "1.234s"


def test_fmt_secs_two_digit_drops_a_decimal():
    from brew_hop_search.timing import _fmt_secs
    assert _fmt_secs(12.345) == "12.35s"


def test_fmt_secs_minutes():
    from brew_hop_search.timing import _fmt_secs
    assert _fmt_secs(65) == "1m05s"
    assert _fmt_secs(3725) == "62m05s"


# ── should_emit policy ───────────────────────────────────────────────────────

def _args(**kw):
    """Build a minimal args namespace with the timing-relevant fields."""
    defaults = dict(
        quiet=False, no_timing=False, verbose=0,
        help_full=None, help_short=None, man=False, version=0,
        _bg_refresh=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def test_emit_default_when_stderr_is_tty(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert should_emit(_args())


def test_suppress_default_when_stderr_not_tty(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: False)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args())


def test_emit_at_verbose_even_when_not_tty(monkeypatch):
    """-v overrides the non-TTY default-suppression."""
    monkeypatch.setattr("sys.stderr.isatty", lambda: False)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert should_emit(_args(verbose=1))
    assert should_emit(_args(verbose=2))


def test_quiet_suppresses_even_at_verbose(monkeypatch):
    """-q wins over -v (matches the existing verbosity ladder)."""
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args(quiet=True, verbose=2))


def test_no_timing_flag_suppresses(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args(no_timing=True))


def test_env_var_suppresses(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.setenv("BREW_HOP_SEARCH_NO_TIMING", "1")
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args())


def test_help_paths_suppress(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args(help_full=""))
    assert not should_emit(_args(help_short=""))
    assert not should_emit(_args(man=True))


def test_version_suppresses(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args(version=1))
    assert not should_emit(_args(version=2))


def test_bg_refresh_subprocess_suppresses(monkeypatch):
    """The detached bg refresh writes its own sentinel — no footer."""
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import should_emit
    assert not should_emit(_args(_bg_refresh=["formula", "https://x"]))


# ── render + emit ────────────────────────────────────────────────────────────

def test_render_footer_format():
    from brew_hop_search.timing import render_footer
    line = render_footer(total=0.034, cache=0.0, api=(0, 0.0), refresh=None)
    assert line == "# [time] total 0.034s · cache 0.000s · api(0) —"


def test_emit_footer_writes_to_stderr(monkeypatch, capsys):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import emit_footer
    emit_footer(_args(), 0.123)
    err = capsys.readouterr().err
    assert "# [time]" in err
    assert "0.123s" in err


def test_emit_footer_silent_when_suppressed(monkeypatch, capsys):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    monkeypatch.delenv("BREW_HOP_SEARCH_NO_TIMING", raising=False)
    from brew_hop_search.timing import emit_footer
    emit_footer(_args(quiet=True), 0.123)
    assert capsys.readouterr().err == ""


# ── Timer / record round-trip ────────────────────────────────────────────────

def test_record_appends_tuple():
    from brew_hop_search.timing import record, _records
    record("installed:f", 0.012)
    assert ("installed:f", 0.012) in _records


def test_timer_records_on_exit():
    from brew_hop_search.timing import Timer, _records
    with Timer("formula") as t:
        pass  # near-zero elapsed
    assert t.elapsed >= 0
    labels = [label for label, _ in _records]
    assert "formula" in labels


def test_timer_records_even_on_exception():
    from brew_hop_search.timing import Timer, _records
    with pytest.raises(ValueError):
        with Timer("cask"):
            raise ValueError("boom")
    labels = [label for label, _ in _records]
    assert "cask" in labels
