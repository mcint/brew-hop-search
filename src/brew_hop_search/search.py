# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Query parsing, FTS pre-filter, predicate matching, and scoring.

Query grammar (see docs/specs/features/search.md#query-syntax):

    [field:][!][^]pattern[$]

- `field`: `name`/`n` or `desc`/`d`/`description`; default = name OR desc
- `!`: negate
- `^` / `$`: anchor start/end
- quoted phrases preserve internal whitespace
"""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass

import sqlite_utils


_FIELD_ALIASES = {
    "name": "name", "n": "name",
    "desc": "desc", "d": "desc", "description": "desc",
}


@dataclass(frozen=True)
class Term:
    field: str | None         # "name", "desc", or None (= either)
    negate: bool
    anchor_start: bool
    anchor_end: bool
    literal: str              # lowercased

    def _haystacks(self, rec: dict) -> list[str]:
        """Return the lowercased strings this term searches against."""
        name_parts: list[str] = []
        for key in ("name", "token"):
            val = rec.get(key)
            if isinstance(val, str):
                name_parts.append(val.lower())
            elif isinstance(val, list):
                name_parts.extend(v.lower() for v in val if isinstance(v, str))
        # Casks: both `token` (slug) and `name` (array of localized names) count
        # as the "name" surface. Taps: `tap` slug + `name`.
        tap_slug = rec.get("tap")
        if isinstance(tap_slug, str):
            name_parts.append(tap_slug.lower())

        desc_val = rec.get("desc") or ""
        desc = desc_val.lower() if isinstance(desc_val, str) else ""

        if self.field == "name":
            return name_parts
        if self.field == "desc":
            return [desc]
        return name_parts + [desc]

    def _predicate(self, hay: str) -> bool:
        if self.anchor_start and self.anchor_end:
            return hay == self.literal
        if self.anchor_start:
            return hay.startswith(self.literal)
        if self.anchor_end:
            return hay.endswith(self.literal)
        return self.literal in hay

    def matches(self, rec: dict) -> bool:
        hit = any(self._predicate(h) for h in self._haystacks(rec))
        return (not hit) if self.negate else hit


def parse_query(query: str) -> list[Term]:
    """Tokenize a query string into Terms. Respects `"..."` quoting."""
    if not query or not query.strip():
        return []

    # shlex: honors quoted phrases, strips the quotes.
    try:
        tokens = shlex.split(query, posix=True)
    except ValueError:
        # Unclosed quote → fall back to whitespace split so users still get
        # *something*; the spec only promises shlex semantics for well-formed
        # input.
        tokens = query.split()

    terms: list[Term] = []
    for raw in tokens:
        if not raw:
            continue
        terms.append(_parse_one(raw))
    return terms


def _parse_one(tok: str) -> Term:
    # Peel `field:` and `!` prefixes in either order (each at most once).
    # A token like `http://example` must not be misread: field: is only
    # consumed when the head is a known alias.
    field: str | None = None
    negate = False
    for _ in range(2):
        if field is None and ":" in tok:
            head, _, tail = tok.partition(":")
            alias = _FIELD_ALIASES.get(head.lower())
            if alias is not None:
                field = alias
                tok = tail
                continue
        if not negate and tok.startswith("!") and len(tok) > 1:
            negate = True
            tok = tok[1:]
            continue
        break

    anchor_start = False
    anchor_end = False
    if tok.startswith("^"):
        anchor_start = True
        tok = tok[1:]
    if tok.endswith("$") and len(tok) > 0:
        anchor_end = True
        tok = tok[:-1]

    return Term(field=field, negate=negate,
                anchor_start=anchor_start, anchor_end=anchor_end,
                literal=tok.lower())


def score_term(term: Term, rec: dict) -> int:
    """Score a single term against a record. 0 = term does not match."""
    if not term.matches(rec):
        return 0
    desc = (rec.get("desc") or "").lower() if isinstance(rec.get("desc"), str) else ""
    hays_name = [h for h in term._haystacks(rec) if h != desc]
    lit = term.literal

    def best(hay: str) -> int:
        # Anchored forms: users who asked for anchoring are telling us the
        # tier they expect. Exact > prefix > suffix.
        if term.anchor_start and term.anchor_end:
            return 100 if hay == lit else 0
        if term.anchor_start:
            return 60 if hay.startswith(lit) else 0
        if term.anchor_end:
            return 40 if hay.endswith(lit) else 0
        # Unanchored: legacy ranking — exact > prefix > substring. No
        # suffix tier; an unanchored `python` query should not rank
        # `ipython` above `python-utils`.
        if hay == lit:
            return 100
        if hay.startswith(lit):
            return 60
        if lit in hay:
            return 30
        return 0

    if term.field == "desc":
        return 10
    name_score = max((best(h) for h in hays_name), default=0)
    if name_score:
        return name_score
    return 10


def score(rec: dict, terms: list[Term]) -> int:
    """Total score for a record given parsed terms. 0 = disqualified."""
    total = 0
    for t in terms:
        s = score_term(t, rec)
        if not t.negate:
            if s == 0:
                return 0
            total += s
        else:
            # Negation: `matches()` already folds the polarity. If it says
            # "matches" (the forbidden thing is absent), it's fine and
            # contributes 0. If it says "does not match", disqualify.
            if not t.matches(rec):
                return 0
    return total


def fts_query(terms: list[Term]) -> str:
    """Build an FTS5 MATCH string from terms suitable as a *pre-filter*.

    Only contributes unanchored, non-negated, single-word terms; anchored,
    negated, phrase, and field-scoped terms are applied in the Python-side
    post-filter where the semantics are correct.
    """
    parts: list[str] = []
    for t in terms:
        if t.negate or t.anchor_start or t.anchor_end:
            continue
        if " " in t.literal:
            continue
        if not t.literal:
            continue
        safe = t.literal.replace('"', '""')
        parts.append(f'"{safe}"*')
    return " AND ".join(parts)


def search(db: sqlite_utils.Database, kind: str, query: str, limit: int,
           pk_col: str | None = None, offset: int = 0) -> list[dict]:
    terms = parse_query(query)

    # No query → return all rows (for listing)
    if not terms:
        if kind not in db.table_names():
            return []
        rows = [json.loads(r[0]) for r in db.execute(
            f"SELECT raw FROM {kind} LIMIT ? OFFSET ?", [limit, offset]
        ).fetchall()]
        return rows

    if pk_col is None:
        pk_col = "name" if kind in ("formula", "installed_formula") else "token"

    fts_table = f"{kind}_fts"

    candidates: list[dict] = []
    fq = fts_query(terms)
    if fq and fts_table in db.table_names():
        try:
            sql = f"""
                SELECT {kind}.raw FROM {kind}
                JOIN {fts_table} ON {kind}.{pk_col} = {fts_table}.{pk_col}
                WHERE {fts_table} MATCH ?
                LIMIT 200
            """
            candidates = [json.loads(row[0]) for row in db.execute(sql, [fq]).fetchall()]
        except Exception:
            candidates = []

    if not candidates:
        if kind in db.table_names():
            candidates = [json.loads(row[0]) for row in db.execute(f"SELECT raw FROM {kind}").fetchall()]

    scored: list[tuple[int, dict]] = []
    for item in candidates:
        s = score(item, terms)
        if s > 0:
            scored.append((s, item))

    scored.sort(key=lambda x: (-x[0], _sort_name(x[1])))
    return [item for _, item in scored[offset:offset + limit]]


def _sort_name(item: dict) -> str:
    """Tie-break key: one lowercase string for every record shape.

    Casks carry `name` as a list of display names (possibly empty);
    formulae as a string. Mixing the two in a sort key raised TypeError
    (str vs list) on 0.3.7 for `-i` with casks installed. First display
    name, else the token, else the empty string.
    """
    name = item.get("name")
    if isinstance(name, list):
        name = next((n for n in name if isinstance(n, str) and n), None)
    if not isinstance(name, str) or not name:
        name = item.get("token") or ""
    return str(name).lower()
