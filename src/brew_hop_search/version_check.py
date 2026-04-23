# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Check PyPI for newer versions of brew-hop-search, piggyback on existing network ops."""
from __future__ import annotations

import json
import sys
import time
from urllib.request import Request, urlopen

from brew_hop_search import __version__
from brew_hop_search.cache import get_db
from brew_hop_search.display import dim, yellow

from brew_hop_search.defaults import VERSION_CHECK_INTERVAL as CHECK_INTERVAL

PYPI_URL = "https://pypi.org/pypi/brew-hop-search/json"
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


def _parse_version(v: str):
    """PEP 440 `Version` for comparison, or None if unparseable.

    Uses `packaging.version.Version` so the full ordering holds:
    `0.3.7.dev0 < 0.3.7 < 0.3.7.post0 < 0.3.8`, and `-dev` / `.devN` /
    `+local` are all handled correctly without hand-rolled stripping.
    """
    from packaging.version import InvalidVersion, Version
    try:
        return Version(v)
    except InvalidVersion:
        return None


def check_if_due() -> None:
    """Check PyPI for a newer version if enough time has passed.

    Call this when a network request is already being made.
    Prints a one-line notice to stderr if an update is available.
    """
    try:
        if _last_check_age() < CHECK_INTERVAL:
            return

        from brew_hop_search import user_agent
        req = Request(PYPI_URL, headers={"User-Agent": user_agent()})
        with urlopen(req, timeout=5) as r:
            data = json.loads(r.read())

        latest = data.get("info", {}).get("version", "")
        if not latest:
            return

        _record_check()

        cur_v = _parse_version(__version__)
        latest_v = _parse_version(latest)
        if cur_v and latest_v and latest_v > cur_v:
            print(
                dim(f"  brew-hop-search {yellow(latest)} available "
                    f"(current: {__version__})  "
                    f"pip install -U brew-hop-search"),
                file=sys.stderr,
            )
    except Exception:
        pass  # never block on version check failures
