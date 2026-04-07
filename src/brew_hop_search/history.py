"""Install history log — records package versions over time for rollback."""
from __future__ import annotations

import subprocess
import time

import sqlite_utils

from brew_hop_search.cache import get_db

TABLE = "install_log"


def _brew_commit() -> str:
    """Get the current Homebrew core commit (short hash)."""
    try:
        repo = subprocess.run(
            ["brew", "--repository"], capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if not repo:
            return ""
        return subprocess.run(
            ["git", "-C", repo, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def _ensure_table(db: sqlite_utils.Database) -> None:
    if TABLE not in db.table_names():
        db[TABLE].create({
            "name": str,
            "kind": str,       # "formula" or "cask"
            "version": str,
            "brew_commit": str,
            "recorded_at": float,
        }, pk=("name", "kind", "version"))


def record_installed(formulae: list[dict], casks: list[dict]) -> None:
    """Record current installed packages, skipping versions already logged."""
    db = get_db()
    _ensure_table(db)
    commit = _brew_commit()
    now = time.time()

    rows = []
    for f in formulae:
        ver = (f.get("versions") or {}).get("stable", "")
        if ver:
            rows.append({
                "name": f.get("name", ""),
                "kind": "formula",
                "version": ver,
                "brew_commit": commit,
                "recorded_at": now,
            })
    for c in casks:
        ver = str(c.get("version", ""))
        if ver:
            rows.append({
                "name": c.get("token", ""),
                "kind": "cask",
                "version": ver,
                "brew_commit": commit,
                "recorded_at": now,
            })

    if rows:
        db[TABLE].insert_all(rows, pk=("name", "kind", "version"), replace=True)


def get_history(name: str, kind: str | None = None) -> list[dict]:
    """Get version history for a package, newest first."""
    db = get_db()
    if TABLE not in db.table_names():
        return []
    where = "name = ?"
    params = [name]
    if kind:
        where += " AND kind = ?"
        params.append(kind)
    return list(db[TABLE].rows_where(
        where, params, order_by="-recorded_at",
    ))
