"""brew-hop-search: fast offline-first Homebrew search."""
import os

__version__ = "0.3.0"

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
    """Short git commit hash, or empty string."""
    try:
        import subprocess
        from pathlib import Path
        pkg_dir = Path(__file__).resolve().parent
        result = subprocess.run(
            ["git", "-C", str(pkg_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def version_info() -> str:
    """Version string with git commit hash for local/dev builds."""
    h = commit_hash()
    return f"{__version__}+{h}" if h else __version__
