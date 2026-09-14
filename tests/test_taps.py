# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Integration tests for the taps source.

The 2026-05-18 session caught that taps was silently broken: the parser
and DB writer worked, but the CLI never dispatched to them because
`--refresh=taps` (with no query or `-T`) hit the usage-banner exit path.
These tests pin the scanner + DB round-trip so the next regression at
that layer fails noisily instead of quietly showing `taps 0 never ago`.
"""
from __future__ import annotations

import pytest


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_taps_dir(tmp_path, monkeypatch):
    """Create a fake Library/Taps tree and point taps._taps_dir at it.

    Layout mirrors what Homebrew actually has on disk:
      <root>/user1/homebrew-foo/bar.rb         (formula)
      <root>/user2/homebrew-baz/Casks/qux.rb   (cask, via path heuristic)
    """
    root = tmp_path / "Taps"
    formula = root / "user1" / "homebrew-foo" / "bar.rb"
    cask = root / "user2" / "homebrew-baz" / "Casks" / "qux.rb"
    formula.parent.mkdir(parents=True)
    cask.parent.mkdir(parents=True)

    formula.write_text('''
class Bar < Formula
  desc "A bar that exists"
  homepage "https://example.com/bar"
  version "1.0.0"
  url "https://example.com/bar-1.0.0.tar.gz"
end
''')
    cask.write_text('''
cask "qux" do
  version "2.3.4"
  desc "Qux the cask"
  homepage "https://example.com/qux"
  url "https://example.com/qux-2.3.4.dmg"
end
''')
    monkeypatch.setattr("brew_hop_search.sources.taps._taps_dir", lambda: root)
    return root


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redirect the cache DB to a tmp path so tests don't touch ~/.cache."""
    db_path = tmp_path / "brew-hop-search.db"
    monkeypatch.setenv("BREW_HOP_SEARCH_DB", str(db_path))
    # Trust enrichment shells out to `brew tap-info` (~2s); these tests are
    # about the .rb scan + DB round-trip. tests/test_tap_trust.py covers it.
    monkeypatch.setattr("brew_hop_search.sources.taps.fetch_tap_meta", lambda: {})
    return db_path


# ── scanner ────────────────────────────────────────────────────────────────

def test_scan_taps_finds_rb_files(synthetic_taps_dir):
    from brew_hop_search.sources.taps import scan_taps
    items = scan_taps()
    by_name = {it["name"]: it for it in items}
    assert set(by_name) == {"bar", "qux"}
    assert by_name["bar"]["kind"] == "formula"
    assert by_name["bar"]["tap"] == "user1/foo"
    assert by_name["bar"]["version"] == "1.0.0"
    assert by_name["qux"]["kind"] == "cask"
    assert by_name["qux"]["tap"] == "user2/baz"
    assert by_name["qux"]["version"] == "2.3.4"


def test_scan_taps_skips_test_and_spec_dirs(tmp_path, monkeypatch):
    """Files under */test/* or */spec/* are excluded so test fixtures
    in tap repos don't pollute the index."""
    root = tmp_path / "Taps"
    real = root / "u" / "homebrew-t" / "thing.rb"
    fixture = root / "u" / "homebrew-t" / "spec" / "fixture.rb"
    real.parent.mkdir(parents=True)
    fixture.parent.mkdir(parents=True)
    real.write_text('class Thing < Formula\n  version "1"\nend\n')
    fixture.write_text('class Fixture < Formula\n  version "0"\nend\n')
    monkeypatch.setattr("brew_hop_search.sources.taps._taps_dir", lambda: root)

    from brew_hop_search.sources.taps import scan_taps
    names = {it["name"] for it in scan_taps()}
    assert names == {"thing"}


def test_scan_taps_dedupes_same_name_keeping_newest(tmp_path, monkeypatch):
    """A tap can carry a stale root-level copy of a file that's been
    migrated into Formula/ — both stems are the same. The DB pk is
    (tap, kind, name) so we must dedupe, keeping the newer mtime."""
    import os
    root = tmp_path / "Taps"
    legacy = root / "u" / "homebrew-t" / "thing.rb"  # old, top-level
    canonical = root / "u" / "homebrew-t" / "Formula" / "thing.rb"  # new
    legacy.parent.mkdir(parents=True)
    canonical.parent.mkdir(parents=True)
    legacy.write_text('class Thing < Formula\n  version "1.0"\nend\n')
    canonical.write_text('class Thing < Formula\n  version "2.0"\nend\n')
    # Force the canonical copy to be the newer file regardless of FS order.
    os.utime(legacy, (1_700_000_000, 1_700_000_000))
    os.utime(canonical, (1_800_000_000, 1_800_000_000))
    monkeypatch.setattr("brew_hop_search.sources.taps._taps_dir", lambda: root)

    from brew_hop_search.sources.taps import scan_taps
    items = scan_taps()
    assert len(items) == 1
    assert items[0]["version"] == "2.0"


def test_scan_taps_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "brew_hop_search.sources.taps._taps_dir", lambda: tmp_path / "nope"
    )
    from brew_hop_search.sources.taps import scan_taps
    assert scan_taps() == []


# ── refresh → DB round-trip ────────────────────────────────────────────────

def test_refresh_populates_tap_table(synthetic_taps_dir, isolated_db):
    from brew_hop_search.sources.taps import refresh
    from brew_hop_search.cache import get_db, table_count

    assert refresh(silent=True) is True

    db = get_db()
    assert "tap" in db.table_names()
    rows = list(db["tap"].rows)
    assert len(rows) == 2
    slugs = {r["slug"] for r in rows}
    assert "user1/foo/formula/bar" in slugs
    assert "user2/baz/cask/qux" in slugs
    assert table_count(db, "tap") == 2


def test_ensure_cache_force_repopulates(synthetic_taps_dir, isolated_db):
    """force=True must always re-run the scanner, even when a (possibly
    stale) tap table already exists."""
    from brew_hop_search.sources.taps import ensure_cache, refresh
    from brew_hop_search.cache import get_db

    assert refresh(silent=True) is True
    db = get_db()
    initial = list(db["tap"].rows)
    assert len(initial) == 2

    # Drop one row, then force a refresh; scanner should restore both.
    db["tap"].delete("user1/foo/formula/bar")
    assert len(list(db["tap"].rows)) == 1

    assert ensure_cache(force=True) is True
    assert len(list(db["tap"].rows)) == 2


def test_ensure_cache_no_force_returns_true_when_fresh(synthetic_taps_dir, isolated_db):
    from brew_hop_search.sources.taps import ensure_cache, refresh
    from brew_hop_search.cache import get_db

    assert refresh(silent=True) is True
    # Without force, recent _meta means no re-scan.
    assert ensure_cache(force=False) is True
    # Still populated.
    db = get_db()
    assert len(list(db["tap"].rows)) == 2
