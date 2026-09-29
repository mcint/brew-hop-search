# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""brew-hop-search: fast offline-first Homebrew search."""
from pathlib import Path

__version__ = (Path(__file__).parent / "VERSION").read_text().strip()

PYPI_URL = "https://pypi.org/project/brew-hop-search/"
GITHUB_URL = "https://github.com/mcint/brew-hop-search"
BREW_TAP_URL = ""  # set when a tap is published


def user_agent() -> str:
    """User-Agent string. BREW_HOP_UA / BREW_HOP_SEARCH_UA, [hop] ua, or legacy `user_agent`."""
    try:
        from brew_hop_search.settings import get
        ua = get("ua", tool="search")
        if ua:
            return ua
    except Exception:
        pass
    return f"brew-hop-search/{version_info()}"


def commit_hash() -> str:
    """Short git commit hash, or empty string.

    Dev-tree installs resolve via `git rev-parse`. Wheel installs fall back
    to BUILD_COMMIT baked in at build time by hatch_build.py.
    """
    try:
        import subprocess
        from pathlib import Path
        pkg_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "-C", str(pkg_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    try:
        from brew_hop_search import _build_info
        return _build_info.BUILD_COMMIT
    except ImportError:
        return ""


def build_info() -> dict:
    """Static build metadata from _build_info.py (empty for dev-tree installs)."""
    try:
        from brew_hop_search import _build_info
        return {
            "commit": _build_info.BUILD_COMMIT,
            "commit_full": _build_info.BUILD_COMMIT_FULL,
            "branch": _build_info.BUILD_BRANCH,
            "tag": _build_info.BUILD_TAG,
            "dirty": _build_info.BUILD_DIRTY,
            "timestamp": _build_info.BUILD_TIMESTAMP,
        }
    except ImportError:
        return {}


def _commit_count_since_tag() -> int:
    """Commits between HEAD and the most recent tag.

    Dev tree: live `git describe --tags --abbrev=0` + `rev-list --count`.
    Wheel install: read BUILD_COMMIT_COUNT baked at build time.
    Returns 0 on any error (which renders the plain VERSION string).
    """
    try:
        import subprocess
        pkg_dir = Path(__file__).resolve().parent
        tag_r = subprocess.run(
            ["git", "-C", str(pkg_dir), "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=5,
        )
        if tag_r.returncode == 0 and tag_r.stdout.strip():
            range_arg = f"{tag_r.stdout.strip()}..HEAD"
        else:
            # No tags yet — count all commits.
            range_arg = "HEAD"
        count_r = subprocess.run(
            ["git", "-C", str(pkg_dir), "rev-list", "--count", range_arg],
            capture_output=True, text=True, timeout=5,
        )
        if count_r.returncode == 0 and count_r.stdout.strip():
            return int(count_r.stdout.strip())
    except Exception:
        pass
    try:
        from brew_hop_search import _build_info
        return int(getattr(_build_info, "BUILD_COMMIT_COUNT", 0) or 0)
    except ImportError:
        return 0


def version_info() -> str:
    """Computed display version. PEP 440-compatible.

    Three shapes (matching the design in scripts/bump-version.sh and
    docs/specs/drafts/version-string.md):

      X.Y.Z              — tagged release, or count is zero
      X.Y.Z-dev+N        — dev tree (uv run from working copy), N commits ahead
      X.Y.Z+N            — built wheel between tags (the `-dev` suffix is
                           dropped to mark "built / could ship" vs the
                           working-tree "live, not built" form)

    Local-version `+N` is opaque to PyPI (uploads strip it); fine for
    debug visibility in -V, --version, and User-Agent.
    """
    count = _commit_count_since_tag()
    if count <= 0:
        return __version__
    has_dev = __version__.endswith("-dev")
    if has_dev and install_source() == "local":
        return f"{__version__}+{count}"
    base = __version__[:-len("-dev")] if has_dev else __version__
    return f"{base}+{count}"


def install_source() -> str:
    """Where the running package came from: 'local', 'brew', 'pypi', 'unknown'.

    Local = a git work tree at the package location (uv run / editable install).
    Brew / pypi inferred from the package path.
    """
    try:
        import subprocess
        from pathlib import Path
        pkg_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "-C", str(pkg_dir), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip() == "true":
            return "local"
    except Exception:
        pass
    from pathlib import Path
    path = str(Path(__file__).resolve().parent)
    if "/Cellar/" in path or "/linuxbrew/" in path:
        return "brew"
    if "site-packages" in path:
        return "pypi"
    return "unknown"
