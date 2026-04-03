"""Check PyPI for newer versions of brew-search, piggyback on existing network ops."""
from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen

from brew_search import __version__
from brew_search.cache import get_db
from brew_search.display import dim, yellow

PYPI_URL = "https://pypi.org/pypi/brew-search/json"
CHECK_INTERVAL = 4 * 3600  # 4 hours
META_KEY = "version_check"


def _last_check_age() -> float:
    """Seconds since last version check, or inf if never checked."""
    try:
        db = get_db()
        if "_meta" not in db.table_names():
            return float("inf")
        row = db["_meta"].get(META_KEY)
        return time.time() - row["updated_at"]
    except Exception:
        return float("inf")


def _record_check() -> None:
    try:
        db = get_db()
        db["_meta"].insert(
            {"kind": META_KEY, "updated_at": time.time(), "count": 0},
            pk="kind", replace=True,
        )
    except Exception:
        pass


def _parse_version(v: str) -> tuple:
    """Parse version string into comparable tuple."""
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(p)
    return tuple(parts)


def check_if_due() -> None:
    """Check PyPI for a newer version if enough time has passed.

    Call this when a network request is already being made.
    Prints a one-line notice to stderr if an update is available.
    """
    try:
        if _last_check_age() < CHECK_INTERVAL:
            return

        req = Request(PYPI_URL, headers={"User-Agent": "brew-search-cli/1.0"})
        with urlopen(req, timeout=5) as r:
            data = json.loads(r.read())

        latest = data.get("info", {}).get("version", "")
        if not latest:
            return

        _record_check()

        if _parse_version(latest) > _parse_version(__version__):
            print(
                dim(f"  brew-search {yellow(latest)} available "
                    f"(current: {__version__})  "
                    f"pip install -U brew-search"),
                file=sys.stderr,
            )
    except Exception:
        pass  # never block on version check failures
