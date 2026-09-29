# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Contextual help (`-h <flags>`) explains every flag the user typed —
including each member of a clustered short group like `-OT`.

Regression: `-h -OT` explained only `-O`, while `-h -O -T` explained both.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest


def _run(*args: str) -> str:
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, timeout=30)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout)


def _explained(out: str) -> list[str]:
    """The flag column of each explanation row, e.g. ['-O, --outdated', ...]."""
    rows = []
    for line in out.splitlines():
        if line.strip().startswith("more help:"):
            break
        m = re.match(r"^    (-\S.*?)  \S", line)
        if m:
            rows.append(m.group(1).strip())
    return rows


def test_cluster_explains_each_member():
    assert _explained(_run("-h", "-OT")) == _explained(_run("-h", "-O", "-T"))
    rows = _explained(_run("-h", "-OT"))
    assert any(r.startswith("-O") for r in rows)
    assert any(r.startswith("-T") for r in rows)


def test_cluster_keeps_typed_form_in_parsed_line():
    out = _run("-h", "-OT")
    assert "parsed: -OT" in out


def test_short_with_value_is_not_a_cluster():
    rows = _explained(_run("-h", "-n0"))
    assert len(rows) == 1 and rows[0].startswith("-n")


def test_repeated_count_flag_is_one_row():
    rows = _explained(_run("-h", "-VV"))
    assert len(rows) == 1 and rows[0].startswith("-V")


def test_cluster_with_unknown_member():
    rows = _explained(_run("-h", "-Oz"))
    assert any(r.startswith("-O") for r in rows)
    assert any(r.startswith("-z") for r in rows)  # shown, marked unknown


def test_expand_short_cluster_unit():
    import argparse
    from brew_hop_search.help_ui import expand_short_cluster
    ap = argparse.ArgumentParser(add_help=False)
    for f in ("-O", "-T", "-i", "-t", "-l"):
        ap.add_argument(f, action="store_true")
    ap.add_argument("-n", default="20")
    ap.add_argument("-V", action="count", default=0)
    ap.add_argument("--table", action="store_true")
    assert expand_short_cluster(ap, "-OT") == ["-O", "-T"]
    assert expand_short_cluster(ap, "-itl") == ["-i", "-t", "-l"]
    assert expand_short_cluster(ap, "-n0") == ["-n0"]      # -n takes a value
    assert expand_short_cluster(ap, "-VV") == ["-V"]       # count flag, repeated
    assert expand_short_cluster(ap, "-VVn5") == ["-V", "-n5"]
    assert expand_short_cluster(ap, "--table") == ["--table"]
    assert expand_short_cluster(ap, "-O") == ["-O"]
    assert expand_short_cluster(ap, "-Oz") == ["-O", "-z"]  # unknown kept, shown as such
