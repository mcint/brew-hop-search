# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Search brew's local API cache (per-formula/cask JSON files)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brew_hop_search.cache import get_db, import_to_db, table_age, table_exists
from brew_hop_search.display import dim, red

DEFAULT_STALE = 3600


def _brew_cache_api() -> Path:
    result = subprocess.run(["brew", "--cache"], capture_output=True, text=True)
    return Path(result.stdout.strip()) / "api"


def _index_local_jsons(api_dir: Path, kind: str) -> list[dict]:
    """Read individual JSON files from brew's API cache."""
    kind_dir = api_dir / kind
    if not kind_dir.is_dir():
        return []
    items = []
    for jf in kind_dir.glob("*.json"):
        try:
            data = json.loads(jf.read_text())
            items.append(data)
        except Exception:
            continue
    return items


def refresh(silent: bool = False) -> bool:
    if not silent:
        print(dim("  \u21bb indexing local brew cache \u2026"), file=sys.stderr)
    try:
        api_dir = _brew_cache_api()
        db = get_db()

        for kind, pk, fts_cols in [
            ("formula", "name", ["name", "desc"]),
            ("cask", "token", ["token", "name", "desc"]),
        ]:
            items = _index_local_jsons(api_dir, kind)
            table_name = f"local_{kind}"

            if kind == "formula":
                rows = [
                    {
                        "name": item.get("name", ""),
                        "desc": item.get("desc") or "",
                        "homepage": item.get("homepage", ""),
                        "version": (item.get("versions") or {}).get("stable", ""),
                        "raw": json.dumps(item),
                    }
                    for item in items
                ]
            else:
                rows = [
                    {
                        "token": item.get("token", ""),
                        "name": json.dumps(item.get("name")) if isinstance(item.get("name"), list) else str(item.get("name", "")),
                        "desc": item.get("desc") or "",
                        "homepage": item.get("homepage", ""),
                        "version": str(item.get("version", "")),
                        "raw": json.dumps(item),
                    }
                    for item in items
                ]

            import_to_db(db, table_name, rows,
                          list(rows[0].keys()) if rows else [],
                          pk, fts_cols)

        total = sum(1 for _ in (api_dir / "formula").glob("*.json")) + sum(1 for _ in (api_dir / "cask").glob("*.json")) if api_dir.is_dir() else 0
        if not silent:
            print(dim(f"  \u2713 indexed {total} local formulae/casks"), file=sys.stderr)
        return True
    except Exception as e:
        if not silent:
            print(red(f"  \u2717 local index failed: {e}"), file=sys.stderr)
        return False


def ensure_cache(force: bool = False, stale: int = DEFAULT_STALE) -> bool:
    db = get_db()
    needs_sync = force or not table_exists(db, "local_formula")
    if not needs_sync:
        age = table_age(db, "local_formula")
        if age > stale:
            needs_sync = True
    if needs_sync:
        return refresh()
    return True
