# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The repo root is deliberate ("lean" tier, docs/meta/DECISIONS.md).

A stranger's first `ls` should read as "a Python CLI with docs and
tests". Build and release machinery lives in release/, agent material in
agents/, tracking on its own branch. Adding a root entry means adding it
here too, on purpose, in the same commit. That is the reminder.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED = {
    # read first
    "README.md", "LICENSE", "CHANGELOG.md", "SECURITY.md", "AGENTS.md",
    # the package and its truth
    "pyproject.toml", "uv.lock", "src", "tests", "docs",
    # one directory each for the build surface and the agent surface
    "release", "agents",
    # a one-line stub so `make test` works from the root
    "Makefile",
    # tooling convention
    ".github", ".gitignore", ".gitattributes", ".python-version",
}


def _tracked_root_entries() -> set[str]:
    # The index, not HEAD, so a staged addition fails before it is committed.
    out = subprocess.check_output(["git", "-C", str(ROOT), "ls-files"], text=True)
    return {line.split("/", 1)[0] for line in out.splitlines() if line.strip()}


def test_root_has_only_the_entries_we_mean():
    extra = _tracked_root_entries() - ALLOWED
    assert not extra, f"new root entries (add to ALLOWED on purpose): {sorted(extra)}"


def test_root_keeps_what_readers_expect():
    assert {"README.md", "LICENSE", "pyproject.toml", "src", "tests"} <= _tracked_root_entries()
