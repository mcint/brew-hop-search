# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for the displayed version string (`version_info()`).

The contract (mirrors scripts/bump-version.sh comment):
  - VERSION file holds X.Y.Z (release) or X.Y.Z-dev (between releases).
  - version_info() decorates with commit-count suffix:
      X.Y.Z              — tagged release / count == 0
      X.Y.Z-dev+N        — dev tree, N commits ahead of last tag
      X.Y.Z+N            — built wheel between tags (no -dev: "built")

`packaging.Version` is the parser/sort source-of-truth; this test pins
the rendered string and the PEP 440 sort relations.
"""
from __future__ import annotations

import re
from unittest.mock import patch


# ── render shape ─────────────────────────────────────────────────────────────

def test_version_info_renders_dev_with_count_for_local_install():
    from brew_hop_search import version_info
    with patch("brew_hop_search.__version__", "0.3.7-dev"), \
         patch("brew_hop_search._commit_count_since_tag", return_value=31), \
         patch("brew_hop_search.install_source", return_value="local"):
        assert version_info() == "0.3.7-dev+31"


def test_version_info_drops_dev_for_built_install_between_tags():
    from brew_hop_search import version_info
    with patch("brew_hop_search.__version__", "0.3.7-dev"), \
         patch("brew_hop_search._commit_count_since_tag", return_value=31), \
         patch("brew_hop_search.install_source", return_value="pypi"):
        assert version_info() == "0.3.7+31"


def test_version_info_drops_dev_for_brew_install_between_tags():
    from brew_hop_search import version_info
    with patch("brew_hop_search.__version__", "0.3.7-dev"), \
         patch("brew_hop_search._commit_count_since_tag", return_value=31), \
         patch("brew_hop_search.install_source", return_value="brew"):
        assert version_info() == "0.3.7+31"


def test_version_info_no_suffix_when_count_zero():
    """On a tag exactly (count == 0), strip nothing and add nothing."""
    from brew_hop_search import version_info
    with patch("brew_hop_search.__version__", "0.3.7"), \
         patch("brew_hop_search._commit_count_since_tag", return_value=0):
        assert version_info() == "0.3.7"


def test_version_info_no_suffix_for_dev_version_with_count_zero():
    """VERSION='X.Y.Z-dev' + count==0 → show as-is (no +)."""
    from brew_hop_search import version_info
    with patch("brew_hop_search.__version__", "0.3.7-dev"), \
         patch("brew_hop_search._commit_count_since_tag", return_value=0):
        assert version_info() == "0.3.7-dev"


def test_version_info_tagged_release_with_count_appends_local():
    """Edge: VERSION='X.Y.Z' (release) but commits ahead of that tag.
    Probably a forgotten bump-version --dev; surface count anyway."""
    from brew_hop_search import version_info
    with patch("brew_hop_search.__version__", "0.3.7"), \
         patch("brew_hop_search._commit_count_since_tag", return_value=5):
        assert version_info() == "0.3.7+5"


# ── PEP 440 ordering ─────────────────────────────────────────────────────────

def test_pep440_sort_order_dev_lt_release_lt_post():
    from packaging.version import Version
    assert Version("0.3.7.dev0+31") < Version("0.3.7")
    assert Version("0.3.7-dev+31") < Version("0.3.7")
    assert Version("0.3.7") < Version("0.3.7.post1")
    assert Version("0.3.7+31") < Version("0.3.8.dev0")


def test_pep440_dash_dev_normalizes_same_as_dot_devN():
    """`0.3.7-dev` and `0.3.7.dev0` are the same Version under PEP 440."""
    from packaging.version import Version
    assert Version("0.3.7-dev") == Version("0.3.7.dev0")


# ── existing __version__ guard ───────────────────────────────────────────────

def test_version_string_still_starts_with_mmp():
    """__version__ is the raw VERSION file content — keep it parse-able."""
    from brew_hop_search import __version__
    assert re.match(r"\d+\.\d+\.\d+", __version__), \
        f"__version__ should start with X.Y.Z — got {__version__!r}"


# ── commit-count fallback path ───────────────────────────────────────────────

def test_commit_count_falls_back_to_build_info(monkeypatch):
    """If git is unavailable (wheel install), use baked BUILD_COMMIT_COUNT."""
    import sys
    import types
    fake = types.ModuleType("brew_hop_search._build_info")
    fake.BUILD_COMMIT_COUNT = 42
    monkeypatch.setitem(sys.modules, "brew_hop_search._build_info", fake)

    import subprocess as _sp
    def _raise(*a, **kw): raise OSError("simulated no git")
    monkeypatch.setattr(_sp, "run", _raise)

    from brew_hop_search import _commit_count_since_tag
    assert _commit_count_since_tag() == 42


def test_commit_count_zero_when_no_git_no_build_info(monkeypatch):
    """No git and no _build_info → 0 (renders plain VERSION)."""
    import sys
    import brew_hop_search
    # A None entry in sys.modules makes `from brew_hop_search import
    # _build_info` raise ModuleNotFoundError regardless of whether the
    # generated file exists on disk. (Patching builtins.__import__ doesn't
    # work: the from-import path goes through importlib._handle_fromlist,
    # which bypasses the builtin hook.) Also drop the package attribute a
    # prior import may have left behind.
    monkeypatch.setitem(sys.modules, "brew_hop_search._build_info", None)
    monkeypatch.delattr(brew_hop_search, "_build_info", raising=False)

    import subprocess as _sp
    def _raise(*a, **kw): raise OSError("simulated no git")
    monkeypatch.setattr(_sp, "run", _raise)

    from brew_hop_search import _commit_count_since_tag
    assert _commit_count_since_tag() == 0
