"""Expect-style snapshot tests for all output modes.

ppx_expect / cram style: expected output lives in tests/snapshots/*.txt.
Output diffs appear in commits when behavior changes.

Run with UPDATE_SNAPSHOTS=1 to regenerate all snapshots.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.snap import snap  # noqa: F401

# ── test data ───────────────────────────────────────────────────────────────

SAMPLE_FORMULAE = [
    {
        "name": "python@3.13",
        "desc": "Interpreted, interactive, object-oriented programming language",
        "homepage": "https://www.python.org/",
        "versions": {"stable": "3.13.2"},
        "revision": 0,
    },
    {
        "name": "node",
        "desc": "Platform built on V8 to build network applications",
        "homepage": "https://nodejs.org/",
        "versions": {"stable": "21.6.1"},
        "revision": 0,
    },
    {
        "name": "ripgrep",
        "desc": "Search tool like grep and The Silver Searcher",
        "homepage": "https://github.com/BurntSushi/ripgrep",
        "versions": {"stable": "14.1.0"},
        "revision": 0,
    },
]

SAMPLE_CASKS = [
    {
        "token": "firefox",
        "name": ["Firefox"],
        "desc": "Web browser",
        "homepage": "https://www.mozilla.org/firefox/",
        "version": "122.0",
    },
    {
        "token": "visual-studio-code",
        "name": ["Microsoft Visual Studio Code"],
        "desc": "Open-source code editor",
        "homepage": "https://code.visualstudio.com/",
        "version": "1.86.0",
    },
]


def _seed_db(db_path: Path) -> None:
    """Seed a test database with sample data."""
    import sqlite_utils

    db = sqlite_utils.Database(db_path)

    # Formulae
    rows = [
        {
            "name": f["name"],
            "desc": f["desc"],
            "homepage": f["homepage"],
            "version": f["versions"]["stable"],
            "raw": json.dumps(f),
        }
        for f in SAMPLE_FORMULAE
    ]
    db["formula"].insert_all(rows, pk="name")
    db["formula"].enable_fts(["name", "desc"], tokenize="porter", create_triggers=True)

    # Casks
    cask_rows = [
        {
            "token": c["token"],
            "name": json.dumps(c["name"]) if isinstance(c["name"], list) else c["name"],
            "desc": c["desc"],
            "homepage": c["homepage"],
            "version": str(c["version"]),
            "raw": json.dumps(c),
        }
        for c in SAMPLE_CASKS
    ]
    db["cask"].insert_all(cask_rows, pk="token")
    db["cask"].enable_fts(["token", "name", "desc"], tokenize="porter", create_triggers=True)

    # Empty installed tables (prevents background brew subprocess)
    db["installed_formula"].insert_all([], pk="name")
    db["installed_cask"].insert_all([], pk="token")

    # Meta
    import time
    now = time.time()
    for kind, count in [
        ("formula", len(rows)),
        ("cask", len(cask_rows)),
        ("installed_formula", 0),
        ("installed_cask", 0),
    ]:
        db["_meta"].insert(
            {"kind": kind, "updated_at": now - 3600, "count": count},  # 1h old
            pk="kind", replace=True,
        )


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _run_with_db(db_path: Path, *args: str) -> str:
    """Run CLI with a custom DB path, return stripped output."""
    import subprocess
    import sys
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", *args],
        capture_output=True, text=True, timeout=30,
        env={**env, "BREW_HOP_SEARCH_DB": str(db_path)},
    )
    return _strip_ansi(result.stdout + result.stderr)


@pytest.fixture
def testdb(tmp_path):
    """Create a seeded test database."""
    db_path = tmp_path / "test.db"
    _seed_db(db_path)
    return db_path


# ── snapshot tests ──────────────────────────────────────────────────────────

def test_default_output(snap, testdb):
    """Default TTY output with formula + cask results."""
    snap.assert_match(_run_with_db(testdb, "python"))


def test_default_output_no_results(snap, testdb):
    """Default output when no results match."""
    snap.assert_match(_run_with_db(testdb, "zzzznonexistent"))


def test_grep_output(snap, testdb):
    """Grep mode output format."""
    snap.assert_match(_run_with_db(testdb, "-g", "python"))


def test_quiet_output(snap, testdb):
    """Quiet mode — results only, no header/footer."""
    snap.assert_match(_run_with_db(testdb, "-q", "python"))


def test_formulae_only(snap, testdb):
    """Formula-only search."""
    snap.assert_match(_run_with_db(testdb, "-f", "python"))


def test_casks_only(snap, testdb):
    """Cask-only search."""
    snap.assert_match(_run_with_db(testdb, "-c", "firefox"))


def test_json_output(snap, testdb):
    """JSON output format."""
    snap.assert_match(_run_with_db(testdb, "--json", "node"))


def test_version_flag(snap):
    """Version output (-V)."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "-V"],
        capture_output=True, text=True, timeout=10,
    )
    output = _strip_ansi(result.stdout + result.stderr)
    # Just check the first line (version) since the rest is dynamic
    first_line = output.strip().splitlines()[0]
    assert re.match(r"brew-hop-search \d+\.\d+\.\d+", first_line)


# ── display formatter tests ────────────────────────────────────────────────

def test_fmt_formula(snap):
    """Formula formatting (single item)."""
    from brew_hop_search.display import fmt_formula, USE_COLOR
    # Temporarily disable color for stable snapshots
    import brew_hop_search.display as d
    old = d.USE_COLOR
    d.USE_COLOR = False
    try:
        output = fmt_formula(SAMPLE_FORMULAE[0])
    finally:
        d.USE_COLOR = old
    snap.assert_match(output + "\n")


def test_fmt_cask(snap):
    """Cask formatting (single item)."""
    from brew_hop_search.display import fmt_cask
    import brew_hop_search.display as d
    old = d.USE_COLOR
    d.USE_COLOR = False
    try:
        output = fmt_cask(SAMPLE_CASKS[0])
    finally:
        d.USE_COLOR = old
    snap.assert_match(output + "\n")


def test_fmt_tap(snap):
    """Tap formula formatting (single item)."""
    from brew_hop_search.display import fmt_tap_formula
    import brew_hop_search.display as d
    old = d.USE_COLOR
    d.USE_COLOR = False
    try:
        output = fmt_tap_formula({
            "name": "custom-tool",
            "version": "2.0.1",
            "desc": "A custom tap formula",
            "homepage": "https://example.com/custom",
            "tap": "user/homebrew-tools",
        })
    finally:
        d.USE_COLOR = old
    snap.assert_match(output + "\n")
