# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Snapshot tests for brew-hop-search CLI output."""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from tests.snap import snap  # noqa: F401 (fixture)


_VERSION_RE = re.compile(
    r"\d+\.\d+\.\d+(?:\.dev\d+)?(?:\+[0-9a-f]+(?:\.dirty)?)?"
)


def run(*args: str) -> str:
    """Run brew-hop-search and return stdout, stripping ANSI + version suffix."""
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", *args],
        capture_output=True, text=True, timeout=30,
    )
    # Strip ANSI escape codes for stable snapshots
    clean = re.sub(r"\033\[[0-9;]*m", "", result.stdout + result.stderr)
    # Mask version+commit so snapshots don't churn on every commit
    clean = _VERSION_RE.sub("X.Y.Z", clean)
    return clean


def test_help(snap):
    snap.assert_match(run("--help"))


def test_help_terse(snap):
    snap.assert_match(run("-h"))


def test_help_contextual_single(snap):
    """`-h <flag>` echoes the flag and explains it."""
    snap.assert_match(run("-h", "-O"))


def test_help_contextual_multi(snap):
    """`-h <flag> <flag>` explains each in order typed."""
    snap.assert_match(run("-h", "-c", "-i"))


def test_help_contextual_value_attached(snap):
    """`-h -n0` matches -n's action despite the attached value."""
    snap.assert_match(run("-h", "-n0"))


def test_help_contextual_flag_after_others(snap):
    """`<flag> -h` (flag before -h) still routes to contextual help."""
    snap.assert_match(run("-O", "-h"))


def test_help_scoped_section(snap):
    snap.assert_match(run("--help=sources"))


def test_help_scoped_flag(snap):
    snap.assert_match(run("--help=outdated"))


def test_help_scoped_unknown():
    out = run("--help=frobnicate")
    assert "unknown help mode" in out
    assert "frobnicate" in out


def test_help_h_equals_mode(snap):
    """`-h=man` should normalize to `-h man` (first 5 lines of man page)."""
    out = run("-h=man")
    lines = out.splitlines()[:5]
    snap.assert_match("\n".join(lines))


def test_man_flag(snap):
    """--man output starts with the man-page header."""
    out = run("--man")
    lines = out.splitlines()[:5]
    snap.assert_match("\n".join(lines))


def test_version_importable():
    from brew_hop_search import __version__
    assert re.match(r"\d+\.\d+\.\d+", __version__)


def test_limit_env_var_applies():
    """BREW_HOP_SEARCH_LIMIT sets the default for -n (verified via -q row count)."""
    import os as _os
    env = {**_os.environ, "BREW_HOP_SEARCH_LIMIT": "3"}
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "-f", "-q", "python"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    nonempty = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(nonempty) == 3, f"got {len(nonempty)} lines: {result.stdout!r}"


def test_cache_status_json():
    """Cache status JSON should be valid and have expected keys."""
    import json
    output = run("-C", "--json")
    data = json.loads(output)
    assert "cache_dir" in data
    assert "db_path" in data
    assert "sources" in data


def test_duration_parsing():
    from brew_hop_search.cli import parse_duration
    assert parse_duration("30m") == 1800
    assert parse_duration("6h") == 21600
    assert parse_duration("1d") == 86400
    assert parse_duration("1h30m") == 5400
    assert parse_duration("90") == 90


def test_duration_formatting():
    from brew_hop_search.display import fmt_duration
    assert fmt_duration(30) == "<1m"
    assert fmt_duration(90) == "1m"
    assert fmt_duration(3600) == "1h"
    assert fmt_duration(3660) == "1h1m"
    assert fmt_duration(86400) == "1d"
    assert fmt_duration(float("inf")) == "never"


def test_scoring():
    from brew_hop_search.search import score
    # Exact match
    assert score("python", "", ["python"]) == 100
    # Prefix match
    assert score("python3", "", ["python"]) == 60
    # Substring match
    assert score("cpython", "", ["python"]) == 30
    # Description match
    assert score("foo", "uses python", ["python"]) == 10
    # No match
    assert score("foo", "bar", ["python"]) == 0
    # All terms must match
    assert score("python", "language", ["python", "java"]) == 0


def test_fts_query():
    from brew_hop_search.search import fts_query
    assert fts_query(["python"]) == '"python"*'
    assert fts_query(["python", "build"]) == '"python"* AND "build"*'


def test_rb_parser():
    """Test the lightweight Ruby formula parser."""
    import tempfile
    from pathlib import Path
    from brew_hop_search.sources.taps import parse_rb

    rb_content = '''
cask "test-app" do
  version "1.2.3"
  desc "A test application"
  homepage "https://example.com"
  url "https://example.com/download/v1.2.3/test.dmg"
end
'''
    with tempfile.NamedTemporaryFile(suffix=".rb", mode="w", delete=False) as f:
        f.write(rb_content)
        f.flush()
        result = parse_rb(Path(f.name), "test/tap")

    assert result is not None
    assert result["name"] == Path(f.name).stem
    assert result["version"] == "1.2.3"
    assert result["desc"] == "A test application"
    assert result["homepage"] == "https://example.com"
    assert result["tap"] == "test/tap"
