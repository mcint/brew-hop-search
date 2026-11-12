# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Hatch build hook: write _build_info.py + package the man-page markdown.

Bakes git metadata (commit, branch, tag, dirty flag, timestamp) into the
wheel so `brew-hop-search -V` can report the exact commit of any install,
not just dev-tree ones. Also copies docs/brew-hop-search.1.md into
src/brew_hop_search/data/ so `brew-hop-search --man` works post-install.
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
from pathlib import Path

try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:  # imported by tests outside a build; the hook never runs
    BuildHookInterface = object  # type: ignore[misc,assignment]


def _git(*args: str, cwd: str | None = None) -> str:
    try:
        r = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False,
            timeout=5, cwd=cwd,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def project_is_git_toplevel(root) -> bool:
    """True only when `root` (the project being built) is itself the git
    toplevel. An sdist extracted inside somebody else's checkout, say a
    source tree under ~/src or Homebrew's /opt/homebrew, would otherwise
    bake *that* repo's commit into _build_info. Parent repos never count.
    """
    root = Path(root).resolve()
    top = _git("rev-parse", "--show-toplevel", cwd=str(root))
    if not top:
        return False
    return Path(top).resolve() == root


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        # `uv build` does sdist → wheel-from-sdist in sequence. The
        # sdist-build step runs inside the repo (git available) and
        # produces a good _build_info.py that ships inside the sdist. The
        # wheel-build step runs inside the extracted sdist (no .git) and
        # would overwrite with empty values — so: skip if git is absent
        # and the file already exists (inherited from sdist).
        # Only this project's own repo counts; a parent directory's repo
        # (sdist extracted inside another checkout) is treated as "no git"
        # so the sdist-phase file survives.
        if project_is_git_toplevel(Path.cwd()):
            commit_short = _git("rev-parse", "--short", "HEAD")
        else:
            commit_short = ""
        out = "src/brew_hop_search/_build_info.py"
        if not commit_short:
            import os as _os
            if _os.path.exists(out):
                return  # keep the sdist-phase file
            # Fall through and write a placeholder (no git, no prior file).

        commit_full = _git("rev-parse", "HEAD")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        tag = _git("describe", "--tags", "--exact-match", "HEAD")
        last_tag = _git("describe", "--tags", "--abbrev=0")
        # Commits since last tag → drives X.Y.Z-dev+N display version.
        if last_tag:
            commit_count_str = _git("rev-list", "--count", f"{last_tag}..HEAD")
        else:
            commit_count_str = _git("rev-list", "--count", "HEAD")
        try:
            commit_count = int(commit_count_str) if commit_count_str else 0
        except ValueError:
            commit_count = 0
        dirty = bool(_git("status", "--porcelain"))
        ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

        content = (
            "# This Source Code Form is subject to the terms of the Mozilla Public\n"
            "# License, v. 2.0. If a copy of the MPL was not distributed with this\n"
            "# file, You can obtain one at https://mozilla.org/MPL/2.0/.\n"
            "# auto-generated at build time — do not edit\n"
            f'BUILD_COMMIT = "{commit_short}"\n'
            f'BUILD_COMMIT_FULL = "{commit_full}"\n'
            f'BUILD_BRANCH = "{branch}"\n'
            f'BUILD_TAG = "{tag}"\n'
            f'BUILD_LAST_TAG = "{last_tag}"\n'
            f"BUILD_COMMIT_COUNT = {commit_count}\n"
            f"BUILD_DIRTY = {dirty!r}\n"
            f'BUILD_TIMESTAMP = "{ts}"\n'
        )
        with open(out, "w") as f:
            f.write(content)

        # Stage the man-page markdown as package data so --man works
        # from installed wheels (no MANPATH required).
        man_src = Path("docs/brew-hop-search.1.md")
        man_dst = Path("src/brew_hop_search/data/brew-hop-search.1.md")
        if man_src.is_file():
            man_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(man_src, man_dst)
