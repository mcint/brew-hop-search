# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Database, FTS, and cache TTL logic.

Also hosts the **refresh tracker** + sentinel-file mechanism that the
cache-first stale flow uses. When a foreground command serves results
from cache and kicks off a background refresh subprocess, that subprocess
writes a sentinel file at completion so the foreground process can show
a trailing status line and a wall-clock duration.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import sqlite_utils

CACHE_DIR = Path.home() / ".cache" / "brew-hop-search"
DB_PATH = CACHE_DIR / "brew-hop-search.db"

# On-disk schema version (docs/specs/SCHEMA.md). Bump when a table or column
# changes shape in a way a *reader other than this package* would notice —
# the brew-hop-api read model pins this number, not our package version.
# Written to `_meta` (kind "schema_version", value column) on every import.
SCHEMA_VERSION = 1
REFRESH_LOG = CACHE_DIR / "refresh.log"
_REFRESH_LOG_MAX = 1 * 1024 * 1024  # 1 MB before rotation


# ── refresh tracker (foreground side) ──────────────────────────────────────

# Populated when the foreground process kicks off a bg refresh. Each
# entry: (kind, sentinel_path, started_at_seconds). The CLI inspects this
# after printing results to decide whether to render a trailing line.
_pending_refreshes: list[tuple[str, "Path", float]] = []


def register_pending_refresh(kind: str, sentinel: "Path") -> None:
    _pending_refreshes.append((kind, sentinel, time.time()))


def pending_refreshes() -> list[tuple[str, "Path", float]]:
    return list(_pending_refreshes)


def sentinel_path(kind: str, pid: int) -> Path:
    """Path the bg subprocess writes when refresh of `kind` completes."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f".refresh-{kind}.{pid}.done"


def write_sentinel(path: Path, duration_ms: int, ok: bool, msg: str = "") -> None:
    """Atomic write: tmp + rename. Tab-separated single line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    line = f"{int(time.time())}\t{duration_ms}\t{'ok' if ok else 'fail'}\t{msg}\n"
    tmp.write_text(line)
    tmp.replace(path)


def read_sentinel(path: Path) -> tuple[int, bool, str] | None:
    """Read a sentinel file. Returns (duration_ms, ok, msg) or None."""
    try:
        raw = path.read_text().strip()
    except FileNotFoundError:
        return None
    parts = raw.split("\t")
    if len(parts) < 3:
        return None
    try:
        duration_ms = int(parts[1])
    except ValueError:
        return None
    ok = parts[2] == "ok"
    msg = parts[3] if len(parts) > 3 else ""
    return duration_ms, ok, msg


def append_refresh_log(kind: str, duration_ms: int, ok: bool) -> None:
    """Append a row to ~/.cache/brew-hop-search/refresh.log (rotated at 1MB)."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Rotate if oversized (truncate to most-recent half).
        if REFRESH_LOG.exists() and REFRESH_LOG.stat().st_size > _REFRESH_LOG_MAX:
            tail = REFRESH_LOG.read_bytes()[-_REFRESH_LOG_MAX // 2:]
            REFRESH_LOG.write_bytes(tail.split(b"\n", 1)[-1])  # drop partial first line
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        with REFRESH_LOG.open("a") as f:
            f.write(f"{ts}\t{kind}\t{duration_ms}\t{'ok' if ok else 'fail'}\n")
    except Exception:
        pass  # never fail a refresh because of logging


def effective_db_path() -> Path:
    override = os.environ.get("BREW_HOP_SEARCH_DB")
    return Path(override) if override else DB_PATH


def get_db() -> sqlite_utils.Database:
    p = effective_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return sqlite_utils.Database(p)


def table_age(db: sqlite_utils.Database, kind: str) -> float:
    if "_meta" not in db.table_names():
        return float("inf")
    try:
        row = db["_meta"].get(kind)
        return time.time() - row["updated_at"]
    except Exception:
        return float("inf")


def table_updated_at(db: sqlite_utils.Database, kind: str) -> float | None:
    if "_meta" not in db.table_names():
        return None
    try:
        return db["_meta"].get(kind)["updated_at"]
    except Exception:
        return None


def table_count(db: sqlite_utils.Database, kind: str) -> int | None:
    if "_meta" not in db.table_names():
        return None
    try:
        return db["_meta"].get(kind)["count"]
    except Exception:
        return None


def table_exists(db: sqlite_utils.Database, kind: str) -> bool:
    return kind in db.table_names()


def json_path(kind: str) -> Path:
    return CACHE_DIR / f"{kind}.json"


def save_raw_json(kind: str, data: list[dict]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = json_path(kind).with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(data, f)
    tmp.replace(json_path(kind))


def import_to_db(db: sqlite_utils.Database, kind: str, data: list[dict],
                 columns: list[str], pk: str, fts_columns: list[str]) -> None:
    """Import rows into the DB with FTS index.

    Args:
        db: Database instance.
        kind: Table name (e.g. "formula", "cask", "installed_formula").
        data: List of row dicts (must include all columns + "raw").
        columns: Column names to extract from each row dict.
        pk: Primary key column name.
        fts_columns: Columns to include in FTS5 index.
    """
    fts_name = f"{kind}_fts"
    if fts_name in db.table_names():
        db[fts_name].drop()
    if kind in db.table_names():
        db[kind].drop()

    if data:
        db[kind].insert_all(data, pk=pk)
        db[kind].enable_fts(fts_columns, tokenize="porter", create_triggers=True)

    db["_meta"].insert(
        {"kind": kind, "updated_at": time.time(), "count": len(data)},
        pk="kind",
        replace=True,
    )
    stamp_schema_version(db)


def stamp_schema_version(db: sqlite_utils.Database) -> None:
    """Record SCHEMA_VERSION in `_meta` so external readers can check compat.

    Idempotent; `alter=True` adds the `value` column to pre-0.4 databases.
    """
    try:
        db["_meta"].insert(
            {"kind": "schema_version", "updated_at": time.time(), "count": 0,
             "value": str(SCHEMA_VERSION)},
            pk="kind", replace=True, alter=True,
        )
    except Exception:
        pass  # never fail an import over a bookkeeping row


def read_schema_version(db: sqlite_utils.Database) -> int | None:
    """Schema version stamped in `_meta`, or None (pre-0.4 DB: assume 1)."""
    if "_meta" not in db.table_names():
        return None
    try:
        return int(db["_meta"].get("schema_version")["value"])
    except Exception:
        return None


def mark_updated(db: sqlite_utils.Database, kind: str, count: int) -> None:
    db["_meta"].insert(
        {"kind": kind, "updated_at": time.time(), "count": count},
        pk="kind",
        replace=True,
    )
