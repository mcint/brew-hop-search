"""Database, FTS, and cache TTL logic."""
from __future__ import annotations

import json
import time
from pathlib import Path

import sqlite_utils

CACHE_DIR = Path.home() / ".cache" / "brew-search"
DB_PATH = CACHE_DIR / "brew-search.db"


def get_db() -> sqlite_utils.Database:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite_utils.Database(DB_PATH)


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


def mark_updated(db: sqlite_utils.Database, kind: str, count: int) -> None:
    db["_meta"].insert(
        {"kind": kind, "updated_at": time.time(), "count": count},
        pk="kind",
        replace=True,
    )
