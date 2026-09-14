# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Parse and index formulae/casks from locally tapped repos."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from brew_hop_search.cache import get_db, import_to_db, table_age, table_exists
from brew_hop_search.display import dim, red

from brew_hop_search.defaults import stale_taps_seconds


def _brew_prefix() -> Path:
    result = subprocess.run(["brew", "--repository"], capture_output=True, text=True)
    return Path(result.stdout.strip())


def _taps_dir() -> Path:
    return _brew_prefix() / "Library" / "Taps"


# ── lightweight .rb parser ───────────────────────────────────────────────────

_RE_CLASS = re.compile(r'^\s*(?:class|cask)\s+"?(\w[\w-]*)"?', re.MULTILINE)
_RE_DESC = re.compile(r'^\s*desc\s+"([^"]*)"', re.MULTILINE)
_RE_HOMEPAGE = re.compile(r'^\s*homepage\s+"([^"]*)"', re.MULTILINE)
_RE_VERSION = re.compile(r'^\s*version\s+"([^"]*)"', re.MULTILINE)
_RE_URL = re.compile(r'^\s*url\s+"([^"]*)"', re.MULTILINE)


def parse_rb(path: Path, tap_name: str) -> dict | None:
    """Extract metadata from a .rb formula/cask file."""
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return None

    # Derive name from filename (most reliable)
    name = path.stem

    desc_m = _RE_DESC.search(text)
    homepage_m = _RE_HOMEPAGE.search(text)
    version_m = _RE_VERSION.search(text)
    url_m = _RE_URL.search(text)

    # Infer dates from file timestamps
    try:
        stat = path.stat()
        mtime = stat.st_mtime
        # birthtime (creation) available on macOS; falls back to mtime
        ctime = getattr(stat, "st_birthtime", mtime)
    except Exception:
        mtime = ctime = 0.0

    return {
        "name": name,
        "tap": tap_name,
        "desc": desc_m.group(1) if desc_m else "",
        "homepage": homepage_m.group(1) if homepage_m else "",
        "version": version_m.group(1) if version_m else "",
        "url": url_m.group(1) if url_m else "",
        "added_at": ctime,
        "modified_at": mtime,
    }


def scan_taps() -> list[dict]:
    """Scan all taps for .rb formula/cask files.

    Some taps keep a stale copy at the repo root after migrating into
    `Formula/` — e.g. `steipete/tap` has both `goplaces.rb` and
    `Formula/goplaces.rb` at different versions. We dedupe by
    `(tap, kind, name)` and keep the newest mtime, which is the file
    the maintainer is actually updating.
    """
    taps_dir = _taps_dir()
    if not taps_dir.is_dir():
        return []

    by_slug: dict[tuple[str, str, str], dict] = {}
    for user_dir in sorted(taps_dir.iterdir()):
        if not user_dir.is_dir():
            continue
        for tap_dir in sorted(user_dir.iterdir()):
            if not tap_dir.is_dir():
                continue
            tap_name = f"{user_dir.name}/{tap_dir.name.removeprefix('homebrew-')}"
            for rb_file in tap_dir.rglob("*.rb"):
                rel = str(rb_file.relative_to(tap_dir))
                if "test" in rel.lower() or "spec" in rel.lower():
                    continue
                parsed = parse_rb(rb_file, tap_name)
                if not parsed:
                    continue
                is_cask = "/cask" in rel.lower() or rel.lower().startswith("cask")
                parsed["kind"] = "cask" if is_cask else "formula"
                key = (parsed["tap"], parsed["kind"], parsed["name"])
                prev = by_slug.get(key)
                if prev is None or parsed["modified_at"] > prev["modified_at"]:
                    by_slug[key] = parsed
    return list(by_slug.values())


# \u2500\u2500 tap trust metadata (brew \u2265 6.0: `brew tap-info --installed --json=v1`) \u2500\u2500

_TAP_INFO_TIMEOUT = 60


def _tap_meta_from_json(data: list[dict]) -> dict[str, dict]:
    """tap-info JSON \u2192 {tap_name: {trusted, official, remote, head, branch,
    last_commit, path}}. Keeps only what we display or might diff later."""
    meta: dict[str, dict] = {}
    for t in data or []:
        name = t.get("name")
        if not name:
            continue
        meta[name] = {
            "trusted": bool(t.get("trusted", False)),
            "official": bool(t.get("official", False)),
            "remote": t.get("remote") or "",
            "head": t.get("HEAD") or "",
            "branch": t.get("branch") or "",
            "last_commit": t.get("last_commit") or "",
            "path": t.get("path") or "",
        }
    return meta


def fetch_tap_meta() -> dict[str, dict]:
    """Run tap-info when brew is new enough; {} (and a recorded skip) otherwise.

    Failure is never fatal \u2014 trust is an enrichment, the .rb scan is the
    source of truth for what exists.
    """
    from brew_hop_search import brewver
    if not brewver.supports("tap-info-trusted"):
        return {}
    try:
        r = subprocess.run(["brew", "tap-info", "--installed", "--json=v1"],
                           capture_output=True, text=True,
                           timeout=_TAP_INFO_TIMEOUT)
        if r.returncode != 0:
            return {}
        return _tap_meta_from_json(json.loads(r.stdout))
    except Exception:
        return {}


def _annotate_trust(rows: list[dict], meta: dict[str, dict]) -> None:
    """Fold trusted/official onto each tap row in place.

    Stored as 0/1 for SQLite; None when the tap isn't in tap-info (unknown),
    which is distinct from 'known untrusted'.
    """
    for row in rows:
        m = meta.get(row.get("tap", ""))
        if m is None:
            row["trusted"] = None
            row["official"] = None
        else:
            row["trusted"] = int(m["trusted"])
            row["official"] = int(m["official"])


def refresh(silent: bool = False) -> bool:
    if not silent:
        print(dim("  \u21bb scanning taps \u2026"), file=sys.stderr)
    try:
        items = scan_taps()
        meta = fetch_tap_meta()
        # Annotate the scanned items (not just the row projection): search
        # returns the stored `raw` JSON, so display only sees what's in it.
        _annotate_trust(items, meta)
        db = get_db()
        rows = [
            {
                "slug": f"{item['tap']}/{item['kind']}/{item['name']}",
                "name": item["name"],
                "tap": item["tap"],
                "desc": item["desc"],
                "homepage": item["homepage"],
                "version": item["version"],
                "added_at": item.get("added_at", 0.0),
                "modified_at": item.get("modified_at", 0.0),
                "trusted": item.get("trusted"),
                "official": item.get("official"),
                "raw": json.dumps(item),
            }
            for item in items
        ]
        import_to_db(db, "tap", rows,
                      ["slug", "name", "tap", "desc", "homepage", "version",
                       "added_at", "modified_at", "trusted", "official", "raw"],
                      "slug", ["name", "tap", "desc"])
        if not silent:
            print(dim(f"  \u2713 indexed {len(rows)} tap formulae/casks"), file=sys.stderr)
        return True
    except Exception as e:
        if not silent:
            print(red(f"  \u2717 tap scan failed: {e}"), file=sys.stderr)
        return False


def ensure_cache(force: bool = False, stale: int | None = None) -> bool:
    if stale is None:
        stale = stale_taps_seconds()
    db = get_db()
    needs_sync = force or not table_exists(db, "tap")
    if not needs_sync:
        age = table_age(db, "tap")
        if age > stale:
            needs_sync = True
    if needs_sync:
        return refresh()
    return True
