"""Tests for the -O / --outdated flow.

Seeds installed_* + formula/cask tables with a few diverging versions,
then runs the CLI with various flag combinations and snapshots the
output (stripped of ANSI codes).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.snap import snap, expect  # noqa: F401


# ── fixtures ───────────────────────────────────────────────────────────────

SAMPLE_API_FORMULAE = [
    {"name": "python@3.13", "desc": "Python interpreter",
     "homepage": "https://www.python.org/",
     "versions": {"stable": "3.13.2"}, "revision": 0},
    {"name": "node", "desc": "JS runtime",
     "homepage": "https://nodejs.org/",
     "versions": {"stable": "21.6.1"}, "revision": 0},
    {"name": "wget", "desc": "File retriever",
     "homepage": "https://www.gnu.org/software/wget/",
     "versions": {"stable": "1.24.5"}, "revision": 1},
]

SAMPLE_API_CASKS = [
    {"token": "firefox", "name": ["Firefox"], "desc": "Web browser",
     "homepage": "https://www.mozilla.org/", "version": "122.0"},
    {"token": "visual-studio-code", "name": ["VS Code"], "desc": "Editor",
     "homepage": "https://code.visualstudio.com/", "version": "1.86.0"},
]

# Installed: python is out-of-date, node is current, wget pinned and outdated.
SAMPLE_INSTALLED_FORMULAE = [
    {
        "name": "python@3.13",
        "desc": "Python interpreter",
        "homepage": "https://www.python.org/",
        "pinned": False,
        "keg_only": False,
        "installed": [{"version": "3.13.1"}],
    },
    {
        "name": "node",
        "desc": "JS runtime",
        "homepage": "https://nodejs.org/",
        "pinned": False,
        "keg_only": False,
        "installed": [{"version": "21.6.1"}],
    },
    {
        "name": "wget",
        "desc": "File retriever",
        "homepage": "https://www.gnu.org/software/wget/",
        "pinned": True,
        "keg_only": False,
        "installed": [{"version": "1.24.4"}],
    },
]

SAMPLE_INSTALLED_CASKS = [
    {
        "token": "firefox",
        "name": ["Firefox"],
        "desc": "Web browser",
        "homepage": "https://www.mozilla.org/",
        "installed": "121.0",
        "auto_updates": False,
    },
    {
        "token": "visual-studio-code",
        "name": ["VS Code"],
        "desc": "Editor",
        "homepage": "https://code.visualstudio.com/",
        "installed": "1.86.0",  # current
        "auto_updates": True,
    },
]


def _seed_outdated_db(db_path: Path) -> None:
    """Seed a DB with installed + api tables so -O has data to compare."""
    import sqlite_utils
    db = sqlite_utils.Database(db_path)

    # API formula
    rows = [
        {"name": f["name"], "desc": f["desc"], "homepage": f["homepage"],
         "version": f["versions"]["stable"], "raw": json.dumps(f)}
        for f in SAMPLE_API_FORMULAE
    ]
    db["formula"].insert_all(rows, pk="name")
    db["formula"].enable_fts(["name", "desc"], tokenize="porter", create_triggers=True)

    # API cask
    cask_rows = [
        {"token": c["token"],
         "name": json.dumps(c["name"]) if isinstance(c["name"], list) else c["name"],
         "desc": c["desc"], "homepage": c["homepage"],
         "version": str(c["version"]), "raw": json.dumps(c)}
        for c in SAMPLE_API_CASKS
    ]
    db["cask"].insert_all(cask_rows, pk="token")
    db["cask"].enable_fts(["token", "name", "desc"], tokenize="porter", create_triggers=True)

    # Installed formula
    inst_f_rows = [
        {"name": f["name"], "desc": f["desc"], "homepage": f["homepage"],
         "version": f["installed"][0]["version"], "raw": json.dumps(f)}
        for f in SAMPLE_INSTALLED_FORMULAE
    ]
    db["installed_formula"].insert_all(inst_f_rows, pk="name")

    # Installed cask
    inst_c_rows = [
        {"token": c["token"],
         "name": json.dumps(c["name"]) if isinstance(c["name"], list) else c["name"],
         "desc": c["desc"], "homepage": c["homepage"],
         "version": c["installed"], "raw": json.dumps(c)}
        for c in SAMPLE_INSTALLED_CASKS
    ]
    db["installed_cask"].insert_all(inst_c_rows, pk="token")

    now = time.time()
    for kind, count in [
        ("formula", len(rows)),
        ("cask", len(cask_rows)),
        ("installed_formula", len(inst_f_rows)),
        ("installed_cask", len(inst_c_rows)),
    ]:
        db["_meta"].insert(
            {"kind": kind, "updated_at": now - 60, "count": count},
            pk="kind", replace=True,
        )


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def _run(db_path: Path, *args: str) -> str:
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", *args],
        capture_output=True, text=True, timeout=60,
        env={**env, "BREW_HOP_SEARCH_DB": str(db_path)},
    )
    return _strip_ansi(result.stdout + result.stderr)


@pytest.fixture
def outdatedb(tmp_path):
    db_path = tmp_path / "outdated.db"
    _seed_outdated_db(db_path)
    return db_path


# ── tests ──────────────────────────────────────────────────────────────────

def test_outdated_default(snap, outdatedb):
    """Default -O: both sections shown."""
    snap.assert_match(_run(outdatedb, "-O"))


def test_outdated_formulae_only(snap, outdatedb):
    """-O -f: casks section omitted."""
    output = _run(outdatedb, "-O", "-f")
    assert "outdated casks" not in output
    assert "outdated formulae" in output
    snap.assert_match(output)


def test_outdated_casks_only(snap, outdatedb):
    """-O -c: formulae section omitted."""
    output = _run(outdatedb, "-O", "-c")
    assert "outdated formulae" not in output
    assert "outdated casks" in output
    snap.assert_match(output)


def test_outdated_both_flags(outdatedb):
    """-O -f -c: same as bare -O (both kinds)."""
    both = _run(outdatedb, "-O", "-f", "-c")
    bare = _run(outdatedb, "-O")
    assert "outdated formulae" in both
    assert "outdated casks" in both


def test_outdated_quiet(snap, outdatedb):
    """-q: tab-separated, no headers, no footer, no color."""
    output = _run(outdatedb, "-O", "-q")
    # Must not have section headers or hints
    assert "#" not in output
    assert "--" not in output
    # One line per outdated pkg; 3 outdated (python, wget, firefox)
    lines = [l for l in output.splitlines() if l.strip()]
    assert len(lines) == 3
    for line in lines:
        assert line.count("\t") == 3  # name<TAB>installed<TAB>current<TAB>tags
    snap.assert_match(output)


def test_outdated_quiet_empty(tmp_path):
    """-q with nothing outdated: empty output, exit 0."""
    import sqlite_utils
    db_path = tmp_path / "empty.db"
    db = sqlite_utils.Database(db_path)
    # API and installed both agree — nothing outdated.
    f = {"name": "foo", "desc": "", "homepage": "",
         "versions": {"stable": "1.0"}, "revision": 0}
    db["formula"].insert_all([{
        "name": "foo", "desc": "", "homepage": "",
        "version": "1.0", "raw": json.dumps(f),
    }], pk="name")
    db["formula"].enable_fts(["name", "desc"], tokenize="porter")
    inst = {"name": "foo", "desc": "", "homepage": "",
            "pinned": False, "keg_only": False,
            "installed": [{"version": "1.0"}]}
    db["installed_formula"].insert_all([{
        "name": "foo", "desc": "", "homepage": "",
        "version": "1.0", "raw": json.dumps(inst),
    }], pk="name")
    db["installed_cask"].insert_all([], pk="token")
    db["cask"].insert_all([], pk="token")
    now = time.time()
    for kind in ["formula", "cask", "installed_formula", "installed_cask"]:
        db["_meta"].insert({"kind": kind, "updated_at": now, "count": 0},
                           pk="kind", replace=True)

    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "-O", "-q"],
        capture_output=True, text=True, timeout=30,
        env={**env, "BREW_HOP_SEARCH_DB": str(db_path)},
    )
    assert result.returncode == 0
    clean = _strip_ansi(result.stdout)
    assert clean == ""


def test_outdated_grep(snap, outdatedb):
    """-g: source<TAB>name<TAB>installed<TAB>current<TAB>tags."""
    output = _run(outdatedb, "-O", "-g")
    lines = [l for l in output.splitlines() if l.strip()]
    for line in lines:
        parts = line.split("\t")
        assert len(parts) == 5
        assert parts[0] in ("f", "c")
    snap.assert_match(output)


def test_outdated_csv(snap, outdatedb):
    """--csv: header + rows with same columns as -g."""
    output = _run(outdatedb, "-O", "--csv")
    lines = output.strip().splitlines()
    assert lines[0] == "source,name,installed,current,tags"
    snap.assert_match(output)


def test_outdated_tsv(snap, outdatedb):
    """--tsv: header + TSV rows."""
    output = _run(outdatedb, "-O", "--tsv")
    lines = output.strip().splitlines()
    assert lines[0] == "source\tname\tinstalled\tcurrent\ttags"
    snap.assert_match(output)


def test_outdated_table(snap, outdatedb):
    """-T: aligned columns."""
    output = _run(outdatedb, "-O", "-T")
    # Header must be present
    assert "Name" in output
    assert "Installed" in output
    snap.assert_match(output)


def test_outdated_sql(snap, outdatedb):
    """--sql: two CREATE + INSERT streams."""
    output = _run(outdatedb, "-O", "--sql")
    assert "CREATE TABLE IF NOT EXISTS outdated_formula" in output
    assert "CREATE TABLE IF NOT EXISTS outdated_cask" in output
    assert "INSERT INTO outdated_formula" in output
    assert "INSERT INTO outdated_cask" in output
    snap.assert_match(output)


def test_outdated_json_full(outdatedb):
    """--json: meta envelope + formulae/casks keys."""
    output = _run(outdatedb, "-O", "--json")
    # strip any stderr progress lines
    # the envelope is a single object at the top
    data = json.loads(output)
    assert data["meta"]["command"] == "outdated"
    assert "formulae" in data
    assert "casks" in data
    # python + wget outdated
    names = [e["name"] for e in data["formulae"]]
    assert "python@3.13" in names
    assert "wget" in names


def test_outdated_json_short(outdatedb):
    """--json=short: compact row list with same columns as -g."""
    output = _run(outdatedb, "-O", "--json=short")
    data = json.loads(output)
    assert data["meta"]["mode"] == "short"
    assert "results" in data
    for row in data["results"]:
        assert set(row.keys()) == {"source", "name", "installed", "current", "tags"}
        assert row["source"] in ("f", "c")


def test_outdated_json_filter_f(outdatedb):
    """-O -f --json: casks array empty / omitted."""
    output = _run(outdatedb, "-O", "-f", "--json")
    data = json.loads(output)
    assert "formulae" in data
    # casks either missing or empty
    assert not data.get("casks")


def test_outdated_verbose_header(outdatedb):
    """-v adds the comparing-index summary line."""
    output = _run(outdatedb, "-O", "-v")
    assert "-- comparing" in output
    assert "installed:f" in output
    assert "formula" in output


def test_outdated_vv_details(outdatedb):
    """-vv: per-entry detail shown for entries with extra info."""
    output = _run(outdatedb, "-O", "-vv")
    # wget has revision=1 → should appear in details
    assert "revision=1" in output
    # wget is pinned
    assert "pinned=true" in output


def test_help_shows_T_short(outdatedb):
    """-T is listed in help as short for --table."""
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "--help"],
        capture_output=True, text=True, timeout=10,
        env=env,
    )
    assert "-T, --table" in result.stdout


def test_help_group_order(outdatedb):
    """Help lists groups in new order: sources, info, cache, output."""
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "brew_hop_search.cli", "--help"],
        capture_output=True, text=True, timeout=10,
        env=env,
    )
    out = result.stdout
    src_i = out.index("sources")
    info_i = out.index("info:")
    cache_i = out.index("cache:")
    output_i = out.index("output:")
    assert src_i < info_i < cache_i < output_i
