# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Remote Homebrew API source (formulae.brew.sh)."""
from __future__ import annotations

import json
import subprocess
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

from brew_hop_search.cache import (
    get_db, import_to_db, save_raw_json, table_age, table_exists,
)
from brew_hop_search.display import dim, red, status_line

FORMULA_URL = "https://formulae.brew.sh/api/formula.json"
CASK_URL = "https://formulae.brew.sh/api/cask.json"
TIMEOUT = 10


def fetch(url: str):
    from brew_hop_search import user_agent
    req = Request(url, headers={"User-Agent": user_agent()})
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _formula_rows(data: list[dict]) -> list[dict]:
    return [
        {
            "name": item.get("name", ""),
            "desc": item.get("desc") or "",
            "homepage": item.get("homepage", ""),
            "version": (item.get("versions") or {}).get("stable", ""),
            "raw": json.dumps(item),
        }
        for item in data
    ]


def _cask_rows(data: list[dict]) -> list[dict]:
    return [
        {
            "token": item.get("token", ""),
            "name": item.get("name") or "",
            "desc": item.get("desc") or "",
            "homepage": item.get("homepage", ""),
            "version": str(item.get("version", "")),
            "raw": json.dumps(item),
        }
        for item in data
    ]


def refresh(kind: str, url: str, silent: bool = False) -> bool:
    prefix = f"[{kind}]"
    if not silent:
        status_line(dim(f"  {prefix} fetching index \u2026"))
    try:
        from brew_hop_search.version_check import check_if_due
        check_if_due()
        data = fetch(url)
        if not silent:
            status_line(dim(f"  {prefix} saving {len(data)} entries \u2026"))
        save_raw_json(kind, data)
        if not silent:
            status_line(dim(f"  {prefix} indexing \u2026"))
        db = get_db()
        if kind == "formula":
            rows = _formula_rows(data)
            import_to_db(db, kind, rows, list(rows[0].keys()), "name", ["name", "desc"])
        else:
            rows = _cask_rows(data)
            import_to_db(db, kind, rows, list(rows[0].keys()), "token", ["token", "name", "desc"])
        if not silent:
            status_line(dim(f"  {prefix} \u2713 cached {len(data)} entries"), done=True)
        return True
    except (URLError, Exception) as e:
        if not silent:
            status_line(red(f"  {prefix} \u2717 fetch failed: {e}"), done=True)
        return False


def background_refresh(kind: str, url: str) -> None:
    try:
        subprocess.Popen(
            [sys.executable, "-m", "brew_hop_search.cli", "--_bg-refresh", kind, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def ensure_cache(kind: str, url: str, force: bool, stale: int,
                 fresh: int | None) -> bool:
    db = get_db()
    needs_sync = force or not table_exists(db, kind)

    if not needs_sync and fresh is not None:
        age = table_age(db, kind)
        if age > fresh:
            needs_sync = True

    if needs_sync:
        ok = refresh(kind, url, silent=False)
        if not ok and not table_exists(get_db(), kind):
            return False
        return True

    age = table_age(db, kind)
    if age > stale:
        background_refresh(kind, url)
    return True
