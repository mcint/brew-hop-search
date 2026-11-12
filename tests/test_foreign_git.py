# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Never report a *foreign* git tree as our own.

A brew install lives under /opt/homebrew/Cellar/..., and /opt/homebrew is
Homebrew's git checkout. `git -C <pkg_dir> ...` happily walks up to it, so
0.3.7 from the tap reported Homebrew/brew's HEAD, its commit count and its
recent commits as if they were ours. The same happens to a build run from
an sdist extracted inside any unrelated repo.

Rule: git facts are used only when the repository that contains the
package *is this project* (toplevel has pyproject.toml and
src/brew_hop_search/VERSION, and the package dir sits under it).
Otherwise the baked _build_info is the truth.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_git_env(monkeypatch):
    """Git hooks export GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE; a child
    git would then answer for the hook's repo, not the directory we ask
    about. The pre-commit hook runs this suite, so scrub them."""
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX"):
        monkeypatch.delenv(var, raising=False)


def _fake_run(toplevel: str):
    """subprocess.run stand-in: git says the toplevel is `toplevel`."""
    def run(cmd, *a, **kw):
        class R:
            returncode = 0
            stdout = ""
        r = R()
        if "--show-toplevel" in cmd:
            r.stdout = toplevel + "\n"
        elif "--is-inside-work-tree" in cmd:
            r.stdout = "true\n"
        elif "rev-parse" in cmd:
            r.stdout = "b70618fe42\n"          # Homebrew/brew's HEAD
        elif "rev-list" in cmd:
            r.stdout = "95\n"
        elif "log" in cmd:
            r.stdout = "b70618fe42 Merge pull request #24586 ...\n"
        return r
    return run


def test_dev_tree_git_accepts_this_repo():
    from brew_hop_search import _dev_tree_git
    top = _dev_tree_git()
    assert top is not None and Path(top).resolve() == REPO


def test_dev_tree_git_rejects_foreign_toplevel(monkeypatch):
    from brew_hop_search import _dev_tree_git
    monkeypatch.setattr(subprocess, "run", _fake_run("/opt/homebrew"))
    assert _dev_tree_git() is None


def test_commit_hash_ignores_foreign_git(monkeypatch):
    import sys, types
    import brew_hop_search
    fake = types.ModuleType("brew_hop_search._build_info")
    fake.BUILD_COMMIT = "deadbee"
    fake.BUILD_COMMIT_COUNT = 3
    monkeypatch.setitem(sys.modules, "brew_hop_search._build_info", fake)
    monkeypatch.delattr(brew_hop_search, "_build_info", raising=False)
    monkeypatch.setattr(subprocess, "run", _fake_run("/opt/homebrew"))
    assert brew_hop_search.commit_hash() == "deadbee"
    assert brew_hop_search._commit_count_since_tag() == 3


def test_install_source_is_not_local_inside_foreign_git(monkeypatch):
    import brew_hop_search
    monkeypatch.setattr(subprocess, "run", _fake_run("/opt/homebrew"))
    assert brew_hop_search.install_source() != "local"


def test_VV_hides_recent_commits_outside_dev_tree(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    import brew_hop_search
    from brew_hop_search import cli, version_check
    monkeypatch.setattr(brew_hop_search, "_dev_tree_git", lambda: None)
    monkeypatch.setattr(subprocess, "run", _fake_run("/opt/homebrew"))
    monkeypatch.setattr(version_check, "fetch_latest", lambda timeout=5: "")
    cli._show_version(2)
    out = capsys.readouterr().out
    assert "recent commits" not in out
    assert "Merge pull request" not in out


# ── build hook: an sdist extracted inside someone else's repo ──────────────

def test_build_hook_refuses_parent_repo(tmp_path):
    """hatch_build must not read a parent directory's git when the project
    root being built is not itself the git toplevel."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("hatch_build", REPO / "release" / "hatch_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    inner = outer / "brew_hop_search-0.3.7"          # extracted sdist
    (inner / "src" / "brew_hop_search").mkdir(parents=True)
    (inner / "pyproject.toml").write_text("[project]\nname='brew-hop-search'\n")
    (inner / "src" / "brew_hop_search" / "VERSION").write_text("0.3.7\n")

    assert mod.project_is_git_toplevel(inner) is False
    assert mod.project_is_git_toplevel(REPO) is True
