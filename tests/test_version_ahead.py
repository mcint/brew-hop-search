# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""-VV against PyPI: behind, equal, ahead, and ahead-but-unqualified.

The local build can be *ahead* of PyPI (a dev tree, or an rc). That is
not "up to date" and must not print green. It prints a distinct state
("ahead of PyPI"). If the local version is ahead and *unqualified* (a
plain X.Y.Z with no -dev, +N, rc or similar), the tree claims to be a
release that PyPI has never seen: -VV balks with a warning and a
non-zero status, because that is exactly the state the release guards
exist to prevent.
"""
from __future__ import annotations

import pytest

from .test_version import _FakeResp


def _fake_pypi(latest: str, calls: list):
    def urlopen(req, timeout=None):
        calls.append(req.full_url)
        return _FakeResp(f'{{"info": {{"version": "{latest}"}}}}'.encode())
    return urlopen


def _run_VV(monkeypatch, tmp_path, local: str, latest: str) -> tuple:
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    from brew_hop_search import version_check, cli
    import brew_hop_search
    monkeypatch.setattr(version_check, "urlopen", _fake_pypi(latest, []))
    monkeypatch.setattr(brew_hop_search, "version_info", lambda: local)
    return cli._show_version(2)


@pytest.mark.parametrize("local,latest,word,status", [
    ("0.3.7",        "0.3.7", "up to date",    0),
    ("0.3.6",        "0.3.7", "available",     0),   # behind: upgrade hint
    ("0.3.8-dev+3",  "0.3.7", "ahead of PyPI", 0),   # dev tree
    ("0.3.8rc1",     "0.3.7", "ahead of PyPI", 0),   # candidate
    ("0.3.8+2",      "0.3.7", "ahead of PyPI", 0),   # built between tags
])
def test_VV_states(monkeypatch, tmp_path, capsys, local, latest, word, status):
    rc = _run_VV(monkeypatch, tmp_path, local, latest)
    out = capsys.readouterr().out
    assert word in out, out
    assert "up to date" not in out or word == "up to date"
    assert (rc or 0) == status


def test_VV_balks_when_ahead_and_unqualified(monkeypatch, tmp_path, capsys):
    rc = _run_VV(monkeypatch, tmp_path, "0.3.8", "0.3.7")
    out = capsys.readouterr().out
    assert "0.3.8" in out and "not on PyPI" in out
    assert "up to date" not in out
    assert rc == 1
