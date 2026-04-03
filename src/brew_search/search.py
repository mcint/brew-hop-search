"""Scoring and FTS query logic."""
from __future__ import annotations

import json

import sqlite_utils


def score(name: str, desc: str, terms: list[str]) -> int:
    """Return a relevance score (higher = better). 0 means no match."""
    name_l = name.lower()
    desc_l = desc.lower()
    total = 0
    for term in terms:
        t = term.lower()
        if t == name_l:
            total += 100
        elif name_l.startswith(t):
            total += 60
        elif t in name_l:
            total += 30
        elif t in desc_l:
            total += 10
        else:
            return 0  # all terms must match something
    return total


def fts_query(terms: list[str]) -> str:
    escaped = []
    for t in terms:
        safe = t.replace('"', '""')
        escaped.append(f'"{safe}"*')
    return " AND ".join(escaped)


def search(db: sqlite_utils.Database, kind: str, query: str, limit: int,
           pk_col: str | None = None) -> list[dict]:
    terms = query.split()
    if not terms:
        return []

    if pk_col is None:
        pk_col = "name" if kind in ("formula", "installed_formula") else "token"

    fts_table = f"{kind}_fts"
    name_field = pk_col

    candidates = []
    if fts_table in db.table_names():
        fq = fts_query(terms)
        try:
            sql = f"""
                SELECT {kind}.raw FROM {kind}
                JOIN {fts_table} ON {kind}.{pk_col} = {fts_table}.{pk_col}
                WHERE {fts_table} MATCH ?
                LIMIT 200
            """
            candidates = [json.loads(row[0]) for row in db.execute(sql, [fq]).fetchall()]
        except Exception:
            pass

    if not candidates:
        if kind in db.table_names():
            candidates = [json.loads(row[0]) for row in db.execute(f"SELECT raw FROM {kind}").fetchall()]

    scored = []
    for item in candidates:
        if kind in ("formula", "installed_formula"):
            name = item.get("name", "")
        elif kind == "tap":
            name = f"{item.get('tap', '')} {item.get('name', '')}"
        else:
            name = f"{item.get('token', '')} {item.get('name', '')}"
        desc = item.get("desc") or ""
        s = score(name, desc, terms)
        if s > 0:
            scored.append((s, item))

    scored.sort(key=lambda x: (-x[0], x[1].get("name") or x[1].get("token", "")))
    return [item for _, item in scored[:limit]]
