# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""SCHEMA_VERSION is stamped into `_meta` so external readers (brew-hop-api)
can check compatibility against the on-disk shape, not our package version."""
from __future__ import annotations

import sqlite_utils

from brew_hop_search import cache


def test_import_stamps_schema_version(tmp_path, monkeypatch):
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(tmp_path / "x.db"))
    db = cache.get_db()
    cache.import_to_db(db, "formula",
                       [{"name": "foo", "desc": "", "homepage": "", "version": "1", "raw": "{}"}],
                       ["name", "desc", "homepage", "version", "raw"], "name", ["name", "desc"])
    assert cache.read_schema_version(db) == cache.SCHEMA_VERSION == 1


def test_pre_0_4_db_reads_as_none(tmp_path):
    db = sqlite_utils.Database(tmp_path / "old.db")
    db["_meta"].insert({"kind": "formula", "updated_at": 0, "count": 1}, pk="kind")
    assert cache.read_schema_version(db) is None
    # stamping adds the missing `value` column in place
    cache.stamp_schema_version(db)
    assert cache.read_schema_version(db) == 1
    assert "value" in db["_meta"].columns_dict


def test_schema_version_matches_spec():
    import re
    from pathlib import Path
    spec = Path(__file__).resolve().parents[1] / "docs" / "specs" / "SCHEMA.md"
    m = re.search(r"Schema version: \*\*(\d+)\*\*", spec.read_text())
    assert m and int(m.group(1)) == cache.SCHEMA_VERSION
