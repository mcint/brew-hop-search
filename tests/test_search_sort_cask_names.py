# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Casks carry `name` as a *list* in brew's JSON (several display names).

`search()` sorts ties by `item.get("name") or item.get("token")`. With one
cask whose name list is empty (falls through to the token string) next to
one whose list is non-empty, the sort key mixes str and list and Python
raises `TypeError: '<' not supported between instances of 'str' and
'list'`. Seen on 0.3.7: `uvx brew-hop-search==0.3.7 -i home`.
"""
from __future__ import annotations

import json

import sqlite_utils


def _db(tmp_path):
    db = sqlite_utils.Database(str(tmp_path / "t.db"))
    rows = [
        {"token": "homebrew-app", "name": ["Homebrew App"], "desc": "home things"},
        {"token": "home-tool",    "name": [],               "desc": "home things"},
        {"token": "homeb",        "name": ["Home B", "HB"], "desc": "home things"},
        {"token": "homea",        "name": "Home A",         "desc": "home things"},  # str form
    ]
    db["installed_cask"].insert_all(
        [{"token": r["token"], "name": json.dumps(r["name"]), "raw": json.dumps(r)} for r in rows],
        pk="token",
    )
    return db


def test_search_sorts_when_cask_names_mix_list_and_str(tmp_path):
    from brew_hop_search.search import search
    results = search(_db(tmp_path), "installed_cask", "home", 10, pk_col="token")
    tokens = [r["token"] for r in results]
    assert set(tokens) == {"homebrew-app", "home-tool", "homeb", "homea"}


def test_tie_order_uses_first_display_name_then_token(tmp_path):
    from brew_hop_search.search import _sort_name
    assert _sort_name({"name": ["Home B", "HB"], "token": "homeb"}) == "home b"
    assert _sort_name({"name": [], "token": "home-tool"}) == "home-tool"
    assert _sort_name({"name": "Home A", "token": "homea"}) == "home a"
    assert _sort_name({"name": None, "token": "x"}) == "x"
