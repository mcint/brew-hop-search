"""Hatch build hook: write _build_info.py into the package at build time.

Bakes git metadata (commit, branch, tag, dirty flag, timestamp) into the
wheel so `brew-hop-search -V` can report the exact commit of any install,
not just dev-tree ones.
"""
from __future__ import annotations

import datetime
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def _git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False, timeout=5
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        commit_short = _git("rev-parse", "--short", "HEAD")
        commit_full = _git("rev-parse", "HEAD")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        tag = _git("describe", "--tags", "--exact-match", "HEAD")
        dirty = bool(_git("status", "--porcelain"))
        ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

        content = (
            "# auto-generated at build time — do not edit\n"
            f'BUILD_COMMIT = "{commit_short}"\n'
            f'BUILD_COMMIT_FULL = "{commit_full}"\n'
            f'BUILD_BRANCH = "{branch}"\n'
            f'BUILD_TAG = "{tag}"\n'
            f"BUILD_DIRTY = {dirty!r}\n"
            f'BUILD_TIMESTAMP = "{ts}"\n'
        )
        out = "src/brew_hop_search/_build_info.py"
        with open(out, "w") as f:
            f.write(content)
