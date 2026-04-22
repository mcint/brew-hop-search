# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""brew-hop-search: fast offline-first Homebrew search."""
import os
from pathlib import Path

__version__ = (Path(__file__).parent / "VERSION").read_text().strip()

PYPI_URL = "https://pypi.org/project/brew-hop-search/"
GITHUB_URL = "https://github.com/mcint/brew-hop-search"
BREW_TAP_URL = ""  # set when a tap is published

_DEFAULT_USER_AGENT = f"brew-hop-search/{__version__}"


def user_agent() -> str:
    """User-Agent string. Override via BREW_HOP_SEARCH_UA env var or config."""
    ua = os.environ.get("BREW_HOP_SEARCH_UA")
    if ua:
        return ua
    try:
        from brew_hop_search._config import load_config
        cfg = load_config()
        if cfg.get("user_agent"):
            return cfg["user_agent"]
    except Exception:
        pass
    return _DEFAULT_USER_AGENT


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


def _live_dirty() -> bool:
    """Live `git status --porcelain` check (for dev-tree installs)."""
    try:
        import subprocess
        from pathlib import Path
        pkg_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "-C", str(pkg_dir), "status", "--porcelain", "-uno"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def version_info() -> str:
    """Version string with git commit hash; marks dirty builds."""
    h = commit_hash()
    if not h:
        return __version__
    bi = build_info()
    dirty = bi.get("dirty") if bi else _live_dirty()
    suffix = f"+{h}"
    if dirty:
        suffix += ".dirty"
    return f"{__version__}{suffix}"


def dev_marker() -> str:
    """`(dev: hash[+dirty])` suffix for local builds, empty string otherwise.

    Keeps the base version string standards-compliant (PEP 440) while still
    surfacing a reproducibility hint when running from a dev checkout.
    """
    if install_source() != "local":
        return ""
    h = commit_hash()
    if not h:
        return ""
    bi = build_info()
    dirty = bi.get("dirty") if bi else _live_dirty()
    return f"(dev: {h}{'+dirty' if dirty else ''})"


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
