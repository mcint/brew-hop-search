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

from brew_hop_search.display import fmt_formula, fmt_cask, fmt_tap_formula
from tests.snap import snap, expect  # noqa: F401

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
        age = now - 3600 if kind in ("formula", "cask") else now - 60  # installed: recent
        db["_meta"].insert(
            {"kind": kind, "updated_at": age, "count": count},
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
        capture_output=True, text=True, timeout=60,
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
    """JSON output format with meta envelope."""
    output = _run_with_db(testdb, "--json", "node")
    # Normalize dynamic date field for snapshot stability
    output = re.sub(r'"date": "[^"]+"', '"date": "NORMALIZED"', output)
    snap.assert_match(output)


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


# ── inline expect tests (ppx_expect style) ─────────────────────────────────
# Full expected output as multiline literals — diffs appear in commits.

def test_expect_default_output(testdb):
    r"""Default output — section header, indented results, no source tag."""
    expect(_run_with_db(testdb, "python"),
           "  # formulae (1/3)  • brew install python@3.13\n"
           "    python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/\n")


def test_expect_quiet_output(testdb):
    r"""Quiet mode — no labels, no tags, just results."""
    expect(_run_with_db(testdb, "-q", "python"),
           "python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/\n")


def test_expect_grep_output(testdb):
    r"""Grep mode — tab-separated, parseable."""
    expect(_run_with_db(testdb, "-g", "python"),
           "python@3.13\t3.13.2\thttps://www.python.org/\n"
           "  Interpreted, interactive, object-oriented programming language\n")


def test_expect_no_results(testdb):
    r"""No results message."""
    expect(_run_with_db(testdb, "zzzznonexistent"),
           "  no results for 'zzzznonexistent'\n")


def test_expect_cask_search(testdb):
    r"""Cask-only search — install --cask hint, no source tag at default."""
    expect(_run_with_db(testdb, "-c", "firefox"),
           "  # casks (1/2)  • brew install --cask firefox\n"
           "    firefox  122.0  Web browser  │ https://www.mozilla.org/firefox/\n")


def test_expect_multi_word_query(testdb):
    r"""Multi-word query: both terms must match."""
    expect(_run_with_db(testdb, "search", "tool"),
           "  # formulae (1/3)  • brew install ripgrep\n"
           "    ripgrep  14.1.0  Search tool like grep and The Silver Searcher  │ https://github.com/BurntSushi/ripgrep\n")


# ── display formatter tests ────────────────────────────────────────────────

def test_fmt_formula(snap):
    """Formula formatting (single item).

    Expected output:
    > python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
    """
    import brew_hop_search.display as d
    old = d.USE_COLOR
    d.USE_COLOR = False
    try:
        output = fmt_formula(SAMPLE_FORMULAE[0])
    finally:
        d.USE_COLOR = old
    snap.assert_match(output + "\n")
    expect(output + "\n", """\
python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
""")


def test_fmt_cask(snap):
    """Cask formatting (single item).

    Expected output:
    > firefox  122.0  Web browser  │ https://www.mozilla.org/firefox/
    """
    import brew_hop_search.display as d
    old = d.USE_COLOR
    d.USE_COLOR = False
    try:
        output = fmt_cask(SAMPLE_CASKS[0])
    finally:
        d.USE_COLOR = old
    snap.assert_match(output + "\n")
    expect(output + "\n", """\
firefox  122.0  Web browser  │ https://www.mozilla.org/firefox/
""")


def test_fmt_tap(snap):
    """Tap formula formatting (single item).

    Expected output:
    > custom-tool  2.0.1  user/homebrew-tools  A custom tap formula  │ https://example.com/custom
    """
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
    expect(output + "\n", """\
custom-tool  2.0.1  user/homebrew-tools  A custom tap formula  │ https://example.com/custom
""")
