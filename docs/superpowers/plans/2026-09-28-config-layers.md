# config-layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One declarative settings table drives every env var, config key, generated help/man text and the non-defaults dump, across the `hop` / `search` / `peek` namespaces with `HOMEBREW_HOP…` twins, plus a `FEATURES` list and a `brew-hop` dispatcher.

**Architecture:** A new `settings.py` holds `SETTINGS` (frozen dataclasses) and `resolve()`, which walks flag → tool env → family env → config `[tool]` → config `[hop]` → legacy config keys → default and records which layer answered. Existing accessors (`defaults.stale_api_seconds()`, `_config.resolve_output_format()`, …) become thin wrappers so no caller and no existing env name changes. A `settings_testing.py` fixture auto-parametrizes precedence tests over every row. `hop.py` is the `brew-hop` entry point that execs `brew-hop-<verb>`.

**Tech Stack:** Python 3.12 (pinned by `.python-version`), stdlib only (`tomllib`, `argparse`, `os`, `dataclasses`), `sqlite_utils` already present, pytest + the repo's `tests/snap.py` expect/snapshot helper. Run tests with `uv run python -m pytest tests/ -x -q --tb=short` (that is `make test`; the pre-commit hook runs the same and blocks the commit on failure).

**Spec:** `docs/specs/drafts/config-layers.md` (with `docs/research/2026-09-28-brew-env-config-and-external-commands.md` as its evidence). Read both before Task 1.

## Global Constraints

- No new runtime dependencies. `tomllib` is stdlib on 3.12; the existing `tomli` fallback in `_config.py` stays for older interpreters.
- **No existing name changes.** Every `BREW_HOP_SEARCH_<KEY>` env var, every `[output] default` / `user_agent` config key, every `defaults.py` function name keeps working. Existing tests must stay green without edits (except where a test pins a behaviour this spec deliberately changes; there is exactly one, in Task 3, and it is called out).
- Env names: `BREW_HOP_<KEY>` (family), `BREW_HOP_SEARCH_<KEY>`, `BREW_HOP_PEEK_<KEY>` (tools); each has a `HOMEBREW_HOP…` twin. `BREW_HOP…` wins a twin conflict.
- Precedence: `flag > tool env > family env > config [tool] > config [hop] > legacy config key > default`.
- Booleans: brew's rule — set and not in `false no off nil 0` (case-insensitive) is on; empty string is unset. Default-on booleans are exposed as `NO_<KEY>`.
- Lists are comma-separated, trimmed, empties dropped.
- Secrets are never printed; dumps show `set`.
- Config file stays at `~/.config/brew-hop-search/config.toml`, path override `BREW_HOP_SEARCH_CONFIG` (env-only).
- Commits: Conventional Commits with scope, body says *why*, spec edit in the same commit as the code it describes, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Commit with `git commit -F <file>`; heredocs are refused in this environment.
- Tests first (red), then implementation (green). Snapshot tests: first run with no snapshot file writes it; `UPDATE_SNAPSHOTS=1` regenerates.
- Work on branch `feat/peek` (it already holds the spec) or a branch cut from it.

## Review Focus

1. **A config file from before this change** (`[output] default = "csv"`, top-level `user_agent = "…"`) must keep producing CSV output and that User-Agent. Pinned in Task 3.
2. **Garbage in an env var** (`BREW_HOP_SEARCH_STALE_API=soon`) must not crash and must not silently poison: fall through to the next layer, and say so at `-v`. Pinned in Task 1 and Task 6.
3. **`NO_TIMING=0`.** Today any set value disables the footer; brew's rule makes `0` falsy, so the footer stays on. This is the one deliberate behaviour change; pinned in Task 3, noted in CHANGELOG.
4. **Both twins set, different values** (`BREW_HOP_FORMAT=json HOMEBREW_HOP_FORMAT=table`): `BREW_HOP` wins and `-v` prints one `# [env] …` line naming both. Pinned in Task 1 and Task 6.
5. **`brew hop` with a verb we don't ship** (`brew hop frobnicate`) must exit 2 with the verb list, not a traceback; and a verb whose feature is off (`peek`) must say how to enable it. Pinned in Task 8.

---

### Task 1: The settings table and resolver

**Files:**
- Create: `src/brew_hop_search/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `brew_hop_search.defaults.parse_duration(s) -> int` (exists), `brew_hop_search._config.load_config() -> dict` and `effective_config_path()` (exist).
- Produces:
  - `FALSY = frozenset({"false", "no", "off", "nil", "0"})`
  - `SCOPES = ("hop", "search", "peek")`
  - `@dataclass(frozen=True) class Setting(key, kind, default, scope="hop", doc="", aliases=None, negate=False, env_only=False, legacy_config=())`
  - `SETTINGS: tuple[Setting, ...]` and `SETTING_BY_KEY: dict[str, Setting]`
  - `env_names(setting, tool) -> list[str]` — most specific first, each `BREW_HOP…` immediately followed by its `HOMEBREW_HOP…` twin
  - `parse_value(setting, raw: str) -> object` — raises `ValueError` on bad input
  - `@dataclass class Resolved(value, source: str, notes: list[str])`
  - `resolve(key, tool="search", flag=None) -> Resolved`
  - `get(key, tool="search", flag=None) -> object`
  - `env_name(setting, scope) -> str` (single name, e.g. `BREW_HOP_SEARCH_STALE_API`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_settings.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""settings.py: the declarative table, name generation, parsing, resolution.

Spec: docs/specs/drafts/config-layers.md § Names, § Precedence, § Kinds.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def clean(tmp_path, monkeypatch):
    """No BREW_HOP*/HOMEBREW_HOP* in env; config at a tmp path that may not exist."""
    for k in list(os.environ):
        if k.startswith(("BREW_HOP", "HOMEBREW_HOP")):
            monkeypatch.delenv(k, raising=False)
    cfg = tmp_path / "config.toml"
    monkeypatch.setenv("BREW_HOP_SEARCH_CONFIG", str(cfg))
    return cfg


# ── names ──────────────────────────────────────────────────────────────────

def test_env_names_most_specific_first_with_twins():
    from brew_hop_search.settings import SETTING_BY_KEY, env_names
    s = SETTING_BY_KEY["format"]
    assert env_names(s, "peek") == [
        "BREW_HOP_PEEK_FORMAT", "HOMEBREW_HOP_PEEK_FORMAT",
        "BREW_HOP_FORMAT", "HOMEBREW_HOP_FORMAT",
    ]
    assert env_names(s, "search") == [
        "BREW_HOP_SEARCH_FORMAT", "HOMEBREW_HOP_SEARCH_FORMAT",
        "BREW_HOP_FORMAT", "HOMEBREW_HOP_FORMAT",
    ]


def test_negated_bool_gets_no_prefix():
    from brew_hop_search.settings import SETTING_BY_KEY, env_name
    assert env_name(SETTING_BY_KEY["timing"], "search") == "BREW_HOP_SEARCH_NO_TIMING"


def test_env_only_setting_has_only_search_names():
    """The config path can't come from config. Today's name is BREW_HOP_SEARCH_CONFIG."""
    from brew_hop_search.settings import SETTING_BY_KEY, env_names
    assert env_names(SETTING_BY_KEY["config"], "search")[0] == "BREW_HOP_SEARCH_CONFIG"


def test_every_existing_env_name_is_generated():
    """Back-compat: the names users have exported today must all exist."""
    from brew_hop_search.settings import SETTINGS, env_names
    generated = {n for s in SETTINGS for n in env_names(s, "search")}
    for name in ("BREW_HOP_SEARCH_STALE_API", "BREW_HOP_SEARCH_STALE_INSTALLED",
                 "BREW_HOP_SEARCH_STALE_TAPS", "BREW_HOP_SEARCH_STALE_LOCAL",
                 "BREW_HOP_SEARCH_DURATION", "BREW_HOP_SEARCH_FORMAT",
                 "BREW_HOP_SEARCH_NO_TIMING", "BREW_HOP_SEARCH_DB",
                 "BREW_HOP_SEARCH_CONFIG", "BREW_HOP_SEARCH_UA",
                 "BREW_HOP_SEARCH_LIMIT", "BREW_HOP_SEARCH_BREW_VERSION"):
        assert name in generated, name


# ── parsing ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,want", [
    ("1", True), ("yes", True), ("anything", True), ("TRUE", True),
    ("0", False), ("false", False), ("No", False), ("off", False), ("nil", False),
])
def test_bool_uses_brew_falsy_rule(raw, want):
    from brew_hop_search.settings import Setting, parse_value
    assert parse_value(Setting("x", "bool", False), raw) is want


def test_list_is_comma_separated_trimmed_no_empties():
    from brew_hop_search.settings import Setting, parse_value
    assert parse_value(Setting("x", "list", []), " peek, clock ,,") == ["peek", "clock"]


def test_enum_canonicalizes_aliases_and_rejects_unknown():
    from brew_hop_search.settings import SETTING_BY_KEY, parse_value
    fmt = SETTING_BY_KEY["format"]
    assert parse_value(fmt, "long") == "multi"
    assert parse_value(fmt, "JSON:Short") == "json:short"
    with pytest.raises(ValueError):
        parse_value(fmt, "sundial")


def test_duration_parses_and_rejects():
    from brew_hop_search.settings import SETTING_BY_KEY, parse_value
    assert parse_value(SETTING_BY_KEY["stale_api"], "2h") == 7200
    with pytest.raises(ValueError):
        parse_value(SETTING_BY_KEY["stale_api"], "soon")


def test_path_expands_home_and_vars(monkeypatch):
    from brew_hop_search.settings import Setting, parse_value
    monkeypatch.setenv("XDIR", "/tmp/x")
    p = parse_value(Setting("db", "path", None), "~/$XDIR/y.db")
    assert str(p).endswith("/tmp/x/y.db") and not str(p).startswith("~")


# ── resolution ─────────────────────────────────────────────────────────────

def test_default_when_nothing_set(clean):
    from brew_hop_search.settings import resolve
    r = resolve("stale_api", tool="search")
    assert r.value == 6 * 3600 and r.source == "default"


def test_tool_env_beats_family_env(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_FORMAT", "table")
    monkeypatch.setenv("BREW_HOP_SEARCH_FORMAT", "csv")
    r = resolve("format", tool="search")
    assert r.value == "csv" and r.source == "env:BREW_HOP_SEARCH_FORMAT"


def test_family_env_beats_tool_config(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    clean.write_text('[search]\nformat = "csv"\n')
    monkeypatch.setenv("BREW_HOP_FORMAT", "table")
    assert resolve("format", tool="search").value == "table"


def test_tool_config_beats_family_config(clean):
    from brew_hop_search.settings import resolve
    clean.write_text('[hop]\nformat = "table"\n[search]\nformat = "csv"\n')
    r = resolve("format", tool="search")
    assert r.value == "csv" and r.source == "config:[search] format"


def test_homebrew_twin_is_read(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("HOMEBREW_HOP_SEARCH_FORMAT", "csv")
    r = resolve("format", tool="search")
    assert r.value == "csv" and r.source == "env:HOMEBREW_HOP_SEARCH_FORMAT"


def test_brew_hop_wins_twin_conflict_and_notes_it(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_FORMAT", "json")
    monkeypatch.setenv("HOMEBREW_HOP_FORMAT", "table")
    r = resolve("format", tool="search")
    assert r.value == "json"
    assert r.notes == ["BREW_HOP_FORMAT=json overrides HOMEBREW_HOP_FORMAT=table"]


def test_empty_env_is_unset(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_SEARCH_FORMAT", "")
    assert resolve("format", tool="search").source == "default"


def test_garbage_env_falls_through_with_note(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    clean.write_text('[search]\nstale_api = "2h"\n')
    monkeypatch.setenv("BREW_HOP_SEARCH_STALE_API", "soon")
    r = resolve("stale_api", tool="search")
    assert r.value == 7200 and r.source == "config:[search] stale_api"
    assert r.notes == ["BREW_HOP_SEARCH_STALE_API='soon' ignored: not a duration (30s 5m 6h 1d)"]


def test_flag_beats_everything(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    monkeypatch.setenv("BREW_HOP_SEARCH_FORMAT", "csv")
    r = resolve("format", tool="search", flag="json")
    assert r.value == "json" and r.source == "flag"


def test_negated_bool_env_turns_default_on_off(clean, monkeypatch):
    from brew_hop_search.settings import resolve
    assert resolve("timing", tool="search").value is True
    monkeypatch.setenv("BREW_HOP_SEARCH_NO_TIMING", "1")
    assert resolve("timing", tool="search").value is False
    monkeypatch.setenv("BREW_HOP_SEARCH_NO_TIMING", "0")   # brew rule: 0 is falsy
    assert resolve("timing", tool="search").value is True


def test_legacy_config_keys_still_read(clean):
    from brew_hop_search.settings import resolve
    clean.write_text('user_agent = "me/1"\n[output]\ndefault = "csv"\n')
    assert resolve("format", tool="search").value == "csv"
    assert resolve("format", tool="search").source == "config:output.default (legacy)"
    assert resolve("ua", tool="search").value == "me/1"


def test_config_bool_and_list_types(clean):
    from brew_hop_search.settings import resolve
    clean.write_text('[hop]\ntiming = false\nfeatures = ["peek", "clock"]\n')
    assert resolve("timing", tool="search").value is False
    assert resolve("features", tool="search").value == ["peek", "clock"]


def test_secret_value_is_returned_but_flagged(clean, monkeypatch):
    from brew_hop_search.settings import resolve, SETTING_BY_KEY
    monkeypatch.setenv("BREW_HOP_GITHUB_TOKEN", "ghp_abc")
    assert resolve("github_token", tool="peek").value == "ghp_abc"
    assert SETTING_BY_KEY["github_token"].kind == "secret"


def test_unknown_key_raises():
    from brew_hop_search.settings import resolve
    with pytest.raises(KeyError):
        resolve("nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_settings.py -q --tb=line`
Expected: every test FAILS with `ModuleNotFoundError: No module named 'brew_hop_search.settings'`.

- [ ] **Step 3: Write the module**

```python
# src/brew_hop_search/settings.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""One settings table; every env name, config key and doc line derives from it.

    flag > tool env > family env > config [tool] > config [hop] > legacy key > default

Namespaces: BREW_HOP_<KEY> (family), BREW_HOP_SEARCH_<KEY>, BREW_HOP_PEEK_<KEY>.
Each has a HOMEBREW_HOP… twin because `bin/brew` filters the environment to
HOMEBREW_* before exec'ing an external command — BREW_HOP_* never reaches
`brew hop`. BREW_HOP wins a twin conflict (it can only have been set by
someone running us directly). Spec: docs/specs/drafts/config-layers.md.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

FALSY = frozenset({"false", "no", "off", "nil", "0"})
SCOPES = ("hop", "search", "peek")
KINDS = ("bool", "duration", "enum", "list", "path", "str", "secret")

# Output format aliases (canonical → accepted spellings). Was _config._FORMAT_ALIASES.
FORMAT_ALIASES = {
    "default": ("default", "tty", "human"),
    "json": ("json", "json:full", "full"),
    "json:short": ("json:short", "short"),
    "csv": ("csv",),
    "tsv": ("tsv",),
    "table": ("table",),
    "sql": ("sql",),
    "grep": ("grep",),
    "multi": ("multi", "long"),
    "quiet": ("quiet",),
}
DURATION_ALIASES = {"compact": ("compact",), "clock": ("clock",)}


@dataclass(frozen=True)
class Setting:
    key: str                      # "stale_api" → env STALE_API, config stale_api
    kind: str                     # one of KINDS
    default: object
    scope: str = "hop"            # where the default is documented; overridable anywhere narrower
    doc: str = ""
    aliases: dict | None = None   # enum: canonical → variants
    negate: bool = False          # bool that defaults on: env name is NO_<KEY>, set ⇒ False
    env_only: bool = False        # never read from config (e.g. the config path itself)
    legacy_config: tuple[str, ...] = ()   # dotted keys read from config as a last resort

    def __post_init__(self):
        assert self.kind in KINDS, self.kind
        assert self.scope in SCOPES, self.scope


_DB_DEFAULT = Path.home() / ".cache" / "brew-hop-search" / "brew-hop-search.db"
_CONFIG_DEFAULT = Path.home() / ".config" / "brew-hop-search" / "config.toml"

SETTINGS: tuple[Setting, ...] = (
    Setting("format", "enum", "default", scope="hop", aliases=FORMAT_ALIASES,
            legacy_config=("output.default",),
            doc="default output format when no format flag is given"),
    Setting("features", "list", [], scope="hop",
            doc="experimental surfaces to enable, comma-separated (see --help=features)"),
    Setting("duration", "enum", "compact", scope="hop", aliases=DURATION_ALIASES,
            doc="how ages and TTLs render: compact (40m old) or clock (-0:40:12)"),
    Setting("timing", "bool", True, scope="hop", negate=True,
            doc="the `# [time]` footer (NO_TIMING=1 turns it off)"),
    Setting("db", "path", _DB_DEFAULT, scope="hop",
            doc="SQLite cache database path"),
    Setting("config", "path", _CONFIG_DEFAULT, scope="search", env_only=True,
            doc="config.toml path (env only, for tests)"),
    Setting("ua", "str", None, scope="hop", legacy_config=("user_agent",),
            doc="User-Agent for HTTP requests"),
    Setting("github_token", "secret", None, scope="hop",
            doc="GitHub API token; else HOMEBREW_GITHUB_API_TOKEN, GITHUB_TOKEN, `gh auth token`"),
    Setting("stale_api", "duration", 6 * 3600, scope="search",
            doc="remote index TTL before a background refresh"),
    Setting("stale_installed", "duration", 3600, scope="search",
            doc="installed-packages index TTL"),
    Setting("stale_taps", "duration", 3600, scope="search",
            doc="tapped-repos index TTL"),
    Setting("stale_local", "duration", 3600, scope="search",
            doc="brew API-cache index TTL"),
    Setting("limit", "str", "20", scope="search",
            doc="default -n / --limit (N[+OFFSET])"),
    Setting("brew_version", "str", None, scope="search", env_only=True,
            doc="pretend `brew --version` said this (tests)"),
    Setting("stale_peek", "duration", 15 * 60, scope="peek",
            doc="peeked-tap listing TTL"),
)
SETTING_BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}


# ── names ──────────────────────────────────────────────────────────────────

def _suffix(setting: Setting) -> str:
    return ("NO_" if setting.negate else "") + setting.key.upper()


def env_name(setting: Setting, scope: str) -> str:
    """One name in one scope, BREW_HOP form: `BREW_HOP_SEARCH_STALE_API`."""
    mid = "" if scope == "hop" else scope.upper() + "_"
    return f"BREW_HOP_{mid}{_suffix(setting)}"


def _twin(name: str) -> str:
    return "HOMEBREW_HOP_" + name[len("BREW_HOP_"):]


def env_names(setting: Setting, tool: str) -> list[str]:
    """Most specific first; each BREW_HOP name followed by its HOMEBREW_HOP twin."""
    scopes = [tool, "hop"] if tool != "hop" else ["hop"]
    out: list[str] = []
    for sc in scopes:
        n = env_name(setting, sc)
        out.extend([n, _twin(n)])
    return out


def config_key(setting: Setting, scope: str) -> str:
    return f"[{scope}] {setting.key}"


# ── parsing ────────────────────────────────────────────────────────────────

def parse_value(setting: Setting, raw):
    """Env/config text → typed value. ValueError on bad input, message ready to print."""
    kind = setting.kind
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() not in FALSY
    if kind == "duration":
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        from brew_hop_search.defaults import parse_duration
        try:
            return parse_duration(str(raw))
        except (ValueError, TypeError):
            raise ValueError("not a duration (30s 5m 6h 1d)")
    if kind == "enum":
        v = str(raw).strip().lower()
        for canonical, variants in (setting.aliases or {}).items():
            if v == canonical or v in variants:
                return canonical
        raise ValueError(f"not one of {', '.join(setting.aliases or {})}")
    if kind == "list":
        if isinstance(raw, (list, tuple)):
            items = [str(x).strip() for x in raw]
        else:
            items = [x.strip() for x in str(raw).split(",")]
        return [x for x in items if x]
    if kind == "path":
        return Path(os.path.expandvars(os.path.expanduser(str(raw))))
    return str(raw)


# ── resolution ─────────────────────────────────────────────────────────────

@dataclass
class Resolved:
    value: object
    source: str                     # "flag" | "env:<NAME>" | "config:[scope] key" | "config:<dotted> (legacy)" | "default"
    notes: list[str] = field(default_factory=list)   # twin conflicts, ignored garbage


def _config() -> dict:
    from brew_hop_search._config import load_config
    return load_config()


def _dig(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def resolve(key: str, tool: str = "search", flag=None, config: dict | None = None) -> Resolved:
    """Walk the layers for `key` as seen by `tool`; record which layer answered."""
    setting = SETTING_BY_KEY[key]           # KeyError for unknown keys, on purpose
    notes: list[str] = []
    if flag is not None:
        return Resolved(flag, "flag", notes)

    # env: pairs of (BREW_HOP name, HOMEBREW_HOP twin), most specific scope first
    names = env_names(setting, tool)
    for i in range(0, len(names), 2):
        primary, twin = names[i], names[i + 1]
        pv, tv = os.environ.get(primary, ""), os.environ.get(twin, "")
        if pv and tv and pv != tv:
            notes.append(f"{primary}={pv} overrides {twin}={tv}")
        chosen = (primary, pv) if pv else ((twin, tv) if tv else None)
        if chosen is None:
            continue
        name, raw = chosen
        try:
            val = parse_value(setting, raw)
        except ValueError as e:
            notes.append(f"{name}={raw!r} ignored: {e}")
            continue
        if setting.negate:
            val = not val
        return Resolved(val, f"env:{name}", notes)

    if not setting.env_only:
        cfg = _config() if config is None else config
        scopes = [tool, "hop"] if tool != "hop" else ["hop"]
        for sc in scopes:
            table = cfg.get(sc)
            if isinstance(table, dict) and setting.key in table:
                try:
                    val = parse_value(setting, table[setting.key])
                except ValueError as e:
                    notes.append(f"{config_key(setting, sc)}={table[setting.key]!r} ignored: {e}")
                    continue
                return Resolved(val, f"config:{config_key(setting, sc)}", notes)
        for dotted in setting.legacy_config:
            raw = _dig(cfg, dotted)
            if raw is None:
                continue
            try:
                val = parse_value(setting, raw)
            except ValueError as e:
                notes.append(f"{dotted}={raw!r} ignored: {e}")
                continue
            return Resolved(val, f"config:{dotted} (legacy)", notes)

    return Resolved(setting.default, "default", notes)


def get(key: str, tool: str = "search", flag=None):
    return resolve(key, tool, flag).value
```

Note on `timing`: the table declares the positive concept (`timing`, default `True`). The env name is `NO_TIMING`; a truthy `NO_TIMING` yields `False` (the `negate` flip in `resolve`). Config uses the positive key: `[hop] timing = false`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_settings.py -q --tb=short`
Expected: all PASS. If `test_legacy_config_keys_still_read` fails on `ua`, check that `_dig(cfg, "user_agent")` reads the top-level key (it should).

- [ ] **Step 5: Run the whole suite; nothing else may change**

Run: `uv run python -m pytest tests/ -x -q --tb=short`
Expected: previous count + new tests, all PASS (the module is not wired to anything yet).

- [ ] **Step 6: Commit**

Write the message to `/tmp/…/c1.txt` (or the job tmp dir) and commit:

```
feat(settings): declarative settings table with namespaced env names and layered resolution

One table (`SETTINGS`) now declares every setting once — key, kind,
default, scope, doc — and derives the env names in the hop / search /
peek namespaces, each with a HOMEBREW_HOP… twin (bin/brew filters the
environment to HOMEBREW_* before exec'ing an external command, so a
BREW_HOP_* name alone never reaches `brew hop`). `resolve()` walks
flag > tool env > family env > config [tool] > config [hop] > legacy
key > default and records which layer answered, so -v and the -C dump
can say where a value came from. Booleans follow brew's falsy rule;
lists are comma-separated; garbage falls through with a note instead
of poisoning the value.

Not wired yet: the existing accessors keep their own lookups until the
next commit, so this is additive.

Spec: docs/specs/drafts/config-layers.md § Names, § Precedence, § Kinds.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/settings.py tests/test_settings.py
git commit -q -F /path/to/c1.txt
```

---

### Task 2: The reusable test harness — every row gets precedence tests for free

**Files:**
- Create: `src/brew_hop_search/settings_testing.py`
- Test: `tests/test_settings_layers.py`

**Interfaces:**
- Consumes: `settings.SETTINGS`, `settings.env_name`, `settings.env_names`, `settings.resolve`, `settings.parse_value`, `Setting` fields.
- Produces:
  - `sample_values(setting) -> tuple[object, object]` — two distinct valid *raw* values (strings as a user would type) for any setting kind, for tests to set at two different layers.
  - `class Layers` with `set_env(name, raw)`, `set_config(scope, key, raw)`, `write_config()`, `resolve(key, tool, flag=None)`; and the pytest fixture `layers(tmp_path, monkeypatch)`.
  - Importable by a sibling package: `from brew_hop_search.settings_testing import layers, sample_values`.

- [ ] **Step 1: Write the failing test file (auto-parametrized)**

```python
# tests/test_settings_layers.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Precedence, for every row of SETTINGS, without writing a test per row.

Adding a Setting adds ~8 cases here automatically. Sibling tools import
`brew_hop_search.settings_testing` and run the same matrix over their table.
Spec: docs/specs/drafts/config-layers.md § Testing.
"""
from __future__ import annotations

import pytest

from brew_hop_search.settings import SETTINGS, env_name, env_names, parse_value
from brew_hop_search.settings_testing import layers, sample_values  # noqa: F401

ROWS = [pytest.param(s, id=s.key) for s in SETTINGS]
CONFIGURABLE = [pytest.param(s, id=s.key) for s in SETTINGS if not s.env_only]
TOOL = "search"


def _typed(setting, raw):
    v = parse_value(setting, raw)
    return (not v) if setting.negate else v


@pytest.mark.parametrize("setting", ROWS)
def test_default(layers, setting):
    r = layers.resolve(setting.key, TOOL)
    assert r.source == "default" and r.value == setting.default


@pytest.mark.parametrize("setting", CONFIGURABLE)
def test_family_config_beats_default(layers, setting):
    a, _ = sample_values(setting)
    layers.set_config("hop", setting.key, a)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"config:[hop] {setting.key}" and r.value == parse_value(setting, a)


@pytest.mark.parametrize("setting", CONFIGURABLE)
def test_tool_config_beats_family_config(layers, setting):
    a, b = sample_values(setting)
    layers.set_config("hop", setting.key, a)
    layers.set_config(TOOL, setting.key, b)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"config:[{TOOL}] {setting.key}" and r.value == parse_value(setting, b)


@pytest.mark.parametrize("setting", CONFIGURABLE)
def test_family_env_beats_tool_config(layers, setting):
    a, b = sample_values(setting)
    layers.set_config(TOOL, setting.key, a)
    layers.set_env(env_name(setting, "hop"), b)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"env:{env_name(setting, 'hop')}" and r.value == _typed(setting, b)


@pytest.mark.parametrize("setting", ROWS)
def test_tool_env_beats_family_env(layers, setting):
    a, b = sample_values(setting)
    layers.set_env(env_name(setting, "hop"), a)
    layers.set_env(env_name(setting, TOOL), b)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"env:{env_name(setting, TOOL)}" and r.value == _typed(setting, b)


@pytest.mark.parametrize("setting", ROWS)
def test_homebrew_twin_equals_brew_hop_form(layers, setting):
    a, _ = sample_values(setting)
    twin = env_names(setting, TOOL)[1]
    assert twin.startswith("HOMEBREW_HOP_")
    layers.set_env(twin, a)
    r = layers.resolve(setting.key, TOOL)
    assert r.source == f"env:{twin}" and r.value == _typed(setting, a)


@pytest.mark.parametrize("setting", ROWS)
def test_brew_hop_wins_twin_conflict(layers, setting):
    a, b = sample_values(setting)
    primary, twin = env_names(setting, TOOL)[:2]
    layers.set_env(primary, a)
    layers.set_env(twin, b)
    r = layers.resolve(setting.key, TOOL)
    assert r.value == _typed(setting, a)
    assert r.notes == [f"{primary}={a} overrides {twin}={b}"]


@pytest.mark.parametrize("setting", ROWS)
def test_flag_beats_env(layers, setting):
    a, b = sample_values(setting)
    layers.set_env(env_name(setting, TOOL), a)
    r = layers.resolve(setting.key, TOOL, flag=parse_value(setting, b))
    assert r.source == "flag" and r.value == parse_value(setting, b)


@pytest.mark.parametrize("setting", [pytest.param(s, id=s.key) for s in SETTINGS if s.kind == "secret"])
def test_secret_never_appears_in_source_or_notes(layers, setting):
    layers.set_env(env_name(setting, "hop"), "ghp_SENTINEL")
    layers.set_env(env_names(setting, "hop")[1], "ghp_OTHER")
    r = layers.resolve(setting.key, TOOL)
    assert "ghp_SENTINEL" not in r.source
    assert all("ghp_" not in n for n in r.notes)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_settings_layers.py -q --tb=line 2>&1 | tail -3`
Expected: collection error `ModuleNotFoundError: No module named 'brew_hop_search.settings_testing'`.

- [ ] **Step 3: Write the harness**

```python
# src/brew_hop_search/settings_testing.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Test harness for the settings layers. Importable by sibling tools:

    from brew_hop_search.settings_testing import layers, sample_values

`layers` is a pytest fixture: a clean env (no BREW_HOP*/HOMEBREW_HOP*), a
tmp config file, and helpers to set a value at any layer. It ships in the
package (not tests/) on purpose — a tool built on this table gets the
precedence matrix in tests/test_settings_layers.py for its own rows by
copying that one file.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from brew_hop_search.settings import Setting, resolve, Resolved

_SECRET_MASK = "ghp_"   # notes/dumps must never contain a secret's value


def sample_values(setting: Setting) -> tuple[str, str]:
    """Two distinct valid raw values for `setting`, as a user would type them."""
    k = setting.kind
    if k == "bool":
        return ("1", "0")
    if k == "duration":
        return ("2h", "45m")
    if k == "enum":
        keys = list(setting.aliases or {})
        assert len(keys) >= 2, f"enum {setting.key} needs two values to test precedence"
        return (keys[0], keys[1])
    if k == "list":
        return ("alpha,beta", "gamma")
    if k == "path":
        return ("/tmp/a-path", "/tmp/b-path")
    if k == "secret":
        return ("ghp_aaaa", "ghp_bbbb")
    return ("value-a", "value-b")


class Layers:
    def __init__(self, tmp_path: Path, monkeypatch):
        self.tmp_path = tmp_path
        self.mp = monkeypatch
        self.cfg_path = tmp_path / "config.toml"
        self.cfg: dict[str, dict] = {}
        self.top: dict[str, object] = {}
        for k in list(os.environ):
            if k.startswith(("BREW_HOP", "HOMEBREW_HOP")):
                monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("BREW_HOP_SEARCH_CONFIG", str(self.cfg_path))

    def set_env(self, name: str, raw: str) -> None:
        self.mp.setenv(name, raw)

    def set_config(self, scope: str, key: str, raw) -> None:
        self.cfg.setdefault(scope, {})[key] = raw
        self.write_config()

    def set_config_top(self, key: str, raw) -> None:
        """Top-level (legacy) key such as `user_agent`."""
        self.top[key] = raw
        self.write_config()

    def write_config(self) -> None:
        lines = [f"{k} = {_toml(v)}" for k, v in self.top.items()]
        for scope, table in self.cfg.items():
            lines.append(f"[{scope}]")
            lines.extend(f"{k} = {_toml(v)}" for k, v in table.items())
        self.cfg_path.write_text("\n".join(lines) + "\n")

    def resolve(self, key: str, tool: str = "search", flag=None) -> Resolved:
        return resolve(key, tool, flag)


def _toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml(x) for x in v) + "]"
    return '"' + str(v).replace('"', '\\"') + '"'


@pytest.fixture
def layers(tmp_path, monkeypatch) -> Layers:
    return Layers(tmp_path, monkeypatch)
```

- [ ] **Step 4: Run; fix what the matrix finds**

Run: `uv run python -m pytest tests/test_settings_layers.py -q --tb=short 2>&1 | tail -15`
Expected: all PASS. Two likely trips, both fixed in `settings.py`, not by loosening tests:
- A `bool` row's `test_flag_beats_env` passes `parse_value(...)` (a bool) as the flag; the flag path returns it untouched — fine.
- `duration` config values are written as strings (`"2h"`); `parse_value` handles both `int` and `str` — fine. If a config value arrives as an int for `limit` (`str` kind), `parse_value` returns `str(raw)` — fine.

- [ ] **Step 5: Whole suite**

Run: `uv run python -m pytest tests/ -x -q --tb=short | tail -1`
Expected: PASS.

- [ ] **Step 6: Commit**

```
test(settings): precedence matrix auto-parametrized over every row; harness ships in the package

`settings_testing.py` lives in the package, not tests/, so a sibling
tool built on the same table (`brew-hop-peek` next) imports the `layers`
fixture and `sample_values` and gets the same eight guarantees per row
by copying one test file. Adding a Setting adds its cases; forgetting a
namespace or the HOMEBREW_HOP twin fails here before anyone types it.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/settings_testing.py tests/test_settings_layers.py
git commit -q -F /path/to/c2.txt
```

---

### Task 3: Wire the existing accessors through the table (no name changes)

**Files:**
- Modify: `src/brew_hop_search/defaults.py` (`_from_env`, `stale_*_seconds`, `duration_style`, `LIMIT` comment)
- Modify: `src/brew_hop_search/_config.py` (`resolve_output_format`, drop `_FORMAT_ALIASES`)
- Modify: `src/brew_hop_search/timing.py:83` (`should_emit`)
- Modify: `src/brew_hop_search/cache.py:100-102` (`effective_db_path`)
- Modify: `src/brew_hop_search/__init__.py:16-25` (`user_agent`)
- Modify: `src/brew_hop_search/brewver.py:61-65` (`_from_env`)
- Modify: `src/brew_hop_search/cli.py:649-653` (`-n` default)
- Modify: `CHANGELOG.md` (Unreleased)
- Test: `tests/test_settings_wiring.py` (new), `tests/test_timing.py` (one pin changes, see Step 1)

**Interfaces:**
- Consumes: `settings.get(key, tool, flag)`, `settings.resolve(...)`.
- Produces: unchanged public names — `defaults.stale_api_seconds()` etc., `defaults.duration_style()`, `_config.resolve_output_format()`, `cache.effective_db_path()`, `brew_hop_search.user_agent()`, `timing.should_emit(args)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_settings_wiring.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""The old accessors now read through settings.py — same names, new layers."""
from __future__ import annotations

import types

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_stale_reads_family_env(layers):
    from brew_hop_search.defaults import stale_api_seconds
    layers.set_env("BREW_HOP_STALE_API", "2h")          # family scope, new
    assert stale_api_seconds() == 7200


def test_stale_reads_homebrew_twin(layers):
    from brew_hop_search.defaults import stale_taps_seconds
    layers.set_env("HOMEBREW_HOP_SEARCH_STALE_TAPS", "5m")
    assert stale_taps_seconds() == 300


def test_stale_reads_config(layers):
    from brew_hop_search.defaults import stale_local_seconds
    layers.set_config("search", "stale_local", "90m")
    assert stale_local_seconds() == 5400


def test_duration_style_from_config(layers):
    from brew_hop_search.defaults import duration_style
    layers.set_config("hop", "duration", "clock")
    assert duration_style() == "clock"


def test_format_legacy_output_default_still_works(layers):
    """Review Focus 1: a config from before this change keeps working."""
    from brew_hop_search._config import resolve_output_format
    layers.set_config("output", "default", "csv")
    assert resolve_output_format() == "csv"


def test_format_new_hop_table_beats_legacy(layers):
    from brew_hop_search._config import resolve_output_format
    layers.set_config("output", "default", "csv")
    layers.set_config("hop", "format", "table")
    assert resolve_output_format() == "table"


def test_format_none_when_default(layers):
    from brew_hop_search._config import resolve_output_format
    assert resolve_output_format() is None


def test_user_agent_legacy_top_level_key(layers):
    from brew_hop_search import user_agent
    layers.set_config_top("user_agent", "me/1.0")
    assert user_agent() == "me/1.0"


def test_user_agent_env_beats_config(layers):
    from brew_hop_search import user_agent
    layers.set_config_top("user_agent", "me/1.0")
    layers.set_env("BREW_HOP_UA", "env/2")
    assert user_agent() == "env/2"


def test_db_path_from_family_env(layers, tmp_path):
    from brew_hop_search.cache import effective_db_path
    layers.set_env("BREW_HOP_DB", str(tmp_path / "fam.db"))
    assert effective_db_path() == tmp_path / "fam.db"


def test_db_path_search_env_still_wins(layers, tmp_path):
    from brew_hop_search.cache import effective_db_path
    layers.set_env("BREW_HOP_DB", str(tmp_path / "fam.db"))
    layers.set_env("BREW_HOP_SEARCH_DB", str(tmp_path / "s.db"))
    assert effective_db_path() == tmp_path / "s.db"


def test_brew_version_override_env(layers):
    from brew_hop_search.brewver import _from_env
    layers.set_env("BREW_HOP_SEARCH_BREW_VERSION", "6.1.2")
    assert _from_env() == (6, 1, 2)


def _args(**kw):
    base = dict(quiet=False, no_timing=False, help_full=None, help_short=None,
                man=False, version=0, _bg_refresh=None, verbose=1)
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_timing_no_timing_env_disables(layers):
    from brew_hop_search.timing import should_emit
    layers.set_env("BREW_HOP_SEARCH_NO_TIMING", "1")
    assert should_emit(_args()) is False


def test_timing_no_timing_zero_is_falsy(layers):
    """Review Focus 3: brew's rule. NO_TIMING=0 does NOT disable (it used to)."""
    from brew_hop_search.timing import should_emit
    layers.set_env("BREW_HOP_SEARCH_NO_TIMING", "0")
    assert should_emit(_args()) is True


def test_timing_config_false_disables(layers):
    from brew_hop_search.timing import should_emit
    layers.set_config("hop", "timing", False)
    assert should_emit(_args()) is False
```

Then check `tests/test_timing.py` for a test that sets `BREW_HOP_SEARCH_NO_TIMING` to `"0"` or similar and expects the footer off:

Run: `grep -n "NO_TIMING" tests/*.py`
If a test asserts `"0"` disables, change that literal to `"1"` and add the comment `# brew's falsy rule: 0 does not disable (config-layers)`. If none does, nothing to change.

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_settings_wiring.py -q --tb=line 2>&1 | tail -8`
Expected: the family-env, twin, config, and legacy tests FAIL (old code reads only `BREW_HOP_SEARCH_*` / `[output]`); `test_format_legacy_output_default_still_works`, `test_user_agent_legacy_top_level_key`, `test_db_path_search_env_still_wins`, `test_brew_version_override_env`, `test_timing_no_timing_env_disables` may already PASS. `test_timing_no_timing_zero_is_falsy` FAILS.

- [ ] **Step 3: Rewire `defaults.py`**

Replace the `_from_env` helper and the four `stale_*_seconds` bodies and `duration_style`:

```python
# defaults.py — replace from "# ── env-var resolution helper" through duration_style()

# ── resolution: everything goes through settings.py ─────────────────────────
# Names are unchanged (BREW_HOP_SEARCH_STALE_API …); what's new is the family
# scope (BREW_HOP_STALE_API), the HOMEBREW_HOP twins, and config.toml tables.

def _get(key: str):
    from brew_hop_search.settings import get
    return get(key, tool="search")


# ── duration display style (experimental) ─────────────────────────────────

DURATION_STYLES = ("compact", "clock")


def duration_style() -> str:
    """`compact` (40m old) or `clock` (-0:40:12). See cache-flow.md § Duration style."""
    return _get("duration")


# ── cache stale thresholds (seconds) ───────────────────────────────────────

def stale_api_seconds() -> int:
    """API index (formulae.brew.sh). Drives `--stale` and bg refresh."""
    return _get("stale_api")


def stale_taps_seconds() -> int:
    """Tapped repos (scanned from $(brew --repo)/Library/Taps/)."""
    return _get("stale_taps")


def stale_installed_seconds() -> int:
    """Installed-packages index (`brew info --json=v2 --installed`)."""
    return _get("stale_installed")


def stale_local_seconds() -> int:
    """Local brew API cache at $(brew --cache)/api/."""
    return _get("stale_local")
```

Keep `parse_duration`, the back-compat constants (`STALE_API = stale_api_seconds()` …), `LIMIT`, `API_TIMEOUT`, `VERSION_CHECK_INTERVAL` exactly as they are. Update the module docstring's resolution line to:

```
    defaults (settings.py table)  →  config.toml  →  env var  →  CLI flag
    env: BREW_HOP_SEARCH_<NAME>, BREW_HOP_<NAME>, or HOMEBREW_HOP… twins
```

- [ ] **Step 4: Rewire `_config.py`**

Delete `_FORMAT_ALIASES` and replace `resolve_output_format` with:

```python
def resolve_output_format() -> str | None:
    """User-configured default output format (canonical name), or None.

    Layers per settings.py: env (any namespace) > [search] format >
    [hop] format > legacy [output] default. "default" means no override.
    """
    from brew_hop_search.settings import resolve
    r = resolve("format", tool="search")
    return None if r.source == "default" or r.value == "default" else r.value
```

Keep `CONFIG_DIR`, `CONFIG_PATH`, `effective_config_path`, `load_config` as they are (`load_config` is what `settings._config()` calls).

- [ ] **Step 5: Rewire `timing.py`, `cache.py`, `__init__.py`, `brewver.py`, `cli.py`**

`timing.py` — replace the env check inside `should_emit`:

```python
    # was: if os.environ.get("BREW_HOP_SEARCH_NO_TIMING"): return False
    from brew_hop_search.settings import get
    if not get("timing", tool="search"):
        return False
```

`cache.py` — `effective_db_path`:

```python
def effective_db_path() -> Path:
    from brew_hop_search.settings import get
    return Path(get("db", tool="search"))
```

`__init__.py` — `user_agent`: replace the env + config lookup with

```python
def user_agent() -> str:
    """User-Agent string. BREW_HOP_UA / BREW_HOP_SEARCH_UA, [hop] ua, or legacy `user_agent`."""
    try:
        from brew_hop_search.settings import get
        ua = get("ua", tool="search")
        if ua:
            return ua
    except Exception:
        pass
    # … keep the existing default-UA construction below unchanged …
```

`brewver.py` — `_from_env`:

```python
def _from_env() -> tuple[int, int, int] | None:
    from brew_hop_search.settings import get
    raw = get("brew_version", tool="search")
    if not raw:
        return None
    return parse_brew_version(f"Homebrew {raw.strip()}")
```

`cli.py` (around line 649) — the `-n` default:

```python
    from brew_hop_search.settings import get as _setting
    fmt.add_argument("-n", "--limit", type=str,
                     default=_setting("limit", tool="search"),
                     metavar="N[+OFF]",
                     help="max results [+offset], 0=all (default: 20, or $BREW_HOP_SEARCH_LIMIT)")
```

- [ ] **Step 6: Run the new tests, then the whole suite**

Run: `uv run python -m pytest tests/test_settings_wiring.py -q --tb=short 2>&1 | tail -5`
Expected: all PASS.

Run: `uv run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -3`
Expected: PASS. If `tests/test_config.py::test_unknown_name_in_env_falls_through_to_config` fails: it expects an unknown `BREW_HOP_SEARCH_FORMAT` to fall through to config — `resolve` does exactly that via the garbage note, so a failure means `parse_value` raised something other than `ValueError`; fix in `settings.py`. If `tests/test_defaults.py::test_env_override_falls_back_on_garbage` fails, same cause.

- [ ] **Step 7: CHANGELOG**

Under `## [Unreleased] — 0.4.0-dev` → `### Highlights`, add:

```
- **One settings table.** Every env var, config key and default now
  comes from `settings.py`. New without renaming anything: family-scope
  names (`BREW_HOP_FORMAT` applies to every tool; `BREW_HOP_SEARCH_FORMAT`
  overrides it for search), `HOMEBREW_HOP…` twins so settings survive
  `brew hop` (brew filters the environment to `HOMEBREW_*`), and
  `[hop]` / `[search]` tables in config.toml (`[output] default` and
  `user_agent` still read). Booleans follow brew's rule: set and not
  `false|no|off|nil|0` is on — so `BREW_HOP_SEARCH_NO_TIMING=0` no
  longer disables the footer.
```

- [ ] **Step 8: Commit**

```
refactor(settings): read every existing setting through the table; add family scope, twins, config tables

Same names, new layers. `stale_*_seconds`, `duration_style`,
`resolve_output_format`, `effective_db_path`, `user_agent`,
`brewver._from_env` and the -n default now call settings.get, which
adds BREW_HOP_<KEY> (family), HOMEBREW_HOP… twins and [hop]/[search]
config tables behind each of them. Legacy `[output] default` and
top-level `user_agent` keep working as last-resort config keys.

One deliberate behaviour change, per brew's boolean rule:
NO_TIMING=0 no longer disables the footer. CHANGELOG says so.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/defaults.py src/brew_hop_search/_config.py src/brew_hop_search/timing.py src/brew_hop_search/cache.py src/brew_hop_search/__init__.py src/brew_hop_search/brewver.py src/brew_hop_search/cli.py tests/test_settings_wiring.py tests/test_timing.py CHANGELOG.md
git commit -q -F /path/to/c3.txt
```

---

### Task 4: Features — `features_enabled()`, `feature_on()`, `require_feature()`; `clock` is the first

**Files:**
- Create: `src/brew_hop_search/features.py`
- Modify: `src/brew_hop_search/defaults.py` (`duration_style`)
- Modify: `docs/specs/features/cache-flow.md` § Duration style (one paragraph)
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `settings.resolve("features", tool)`, `settings.env_names`.
- Produces:
  - `KNOWN_FEATURES: dict[str, str]` — name → one-line doc. Initial: `{"clock": "clock-style durations: `updated -0:40:12 ttl +5:19:48` (same as duration=clock)", "peek": "brew hop peek — list an untapped tap from GitHub (brew-hop-peek)"}`
  - `features_enabled(tool="search") -> set[str]` — union of the `features` list and every truthy `BREW_HOP_FEATURE_<NAME>` / `HOMEBREW_HOP_FEATURE_<NAME>` (family scope only for the per-feature alias).
  - `unknown_features(tool) -> list[str]` — names enabled but not in `KNOWN_FEATURES` (for a `-v` warning).
  - `feature_on(name, tool="search") -> bool`
  - `require_feature(name, tool, prog) -> None` — prints the enable hint to stderr and `sys.exit(2)` when off.
  - `enable_hint(name) -> str` — the two-line message text (used by help too).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_features.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""FEATURES list + per-feature alias; clock as the first feature.
Spec: docs/specs/drafts/config-layers.md § Features."""
from __future__ import annotations

import pytest

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_nothing_enabled_by_default(layers):
    from brew_hop_search.features import features_enabled
    assert features_enabled() == set()


def test_list_env_family(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("BREW_HOP_FEATURES", "peek, clock")
    assert features_enabled() == {"peek", "clock"}


def test_list_env_homebrew_twin(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("HOMEBREW_HOP_FEATURES", "peek")
    assert features_enabled() == {"peek"}


def test_list_config(layers):
    from brew_hop_search.features import features_enabled
    layers.set_config("hop", "features", ["clock"])
    assert features_enabled() == {"clock"}


def test_per_feature_alias_bool(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("BREW_HOP_FEATURE_PEEK", "1")
    layers.set_env("HOMEBREW_HOP_FEATURE_CLOCK", "yes")
    layers.set_env("BREW_HOP_FEATURE_OTHER", "0")      # falsy → not enabled
    assert features_enabled() == {"peek", "clock"}


def test_alias_and_list_union(layers):
    from brew_hop_search.features import features_enabled
    layers.set_env("BREW_HOP_FEATURES", "peek")
    layers.set_env("BREW_HOP_FEATURE_CLOCK", "1")
    assert features_enabled() == {"peek", "clock"}


def test_unknown_names_reported_not_fatal(layers):
    from brew_hop_search.features import features_enabled, unknown_features
    layers.set_env("BREW_HOP_FEATURES", "peek,frobnicate")
    assert "peek" in features_enabled()
    assert unknown_features() == ["frobnicate"]


def test_feature_on(layers):
    from brew_hop_search.features import feature_on
    assert feature_on("clock") is False
    layers.set_env("BREW_HOP_FEATURES", "clock")
    assert feature_on("clock") is True


def test_require_feature_exits_2_with_hint(layers, capsys):
    from brew_hop_search.features import require_feature
    with pytest.raises(SystemExit) as e:
        require_feature("peek", tool="peek", prog="brew hop peek")
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "peek is experimental" in err
    assert "BREW_HOP_FEATURES=peek" in err
    assert "HOMEBREW_HOP_FEATURES=peek" in err


def test_require_feature_passes_when_on(layers):
    from brew_hop_search.features import require_feature
    layers.set_env("BREW_HOP_FEATURES", "peek")
    require_feature("peek", tool="peek", prog="brew hop peek")   # no exit


def test_clock_feature_turns_on_clock_style(layers):
    from brew_hop_search.defaults import duration_style
    assert duration_style() == "compact"
    layers.set_env("BREW_HOP_FEATURES", "clock")
    assert duration_style() == "clock"


def test_duration_setting_still_works_without_feature(layers):
    from brew_hop_search.defaults import duration_style
    layers.set_env("BREW_HOP_SEARCH_DURATION", "clock")
    assert duration_style() == "clock"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_features.py -q --tb=line 2>&1 | tail -3`
Expected: `ModuleNotFoundError: No module named 'brew_hop_search.features'`.

- [ ] **Step 3: Write `features.py`**

```python
# src/brew_hop_search/features.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Experimental surfaces, off by default, outside the 1.0 promise.

    BREW_HOP_FEATURES=peek,clock       # the list (family scope; HOMEBREW_HOP_ twin)
    BREW_HOP_FEATURE_PEEK=1            # per-feature alias, brew's one-var shape
    [hop] features = ["peek"]          # config

Brew itself has no feature list (one var per feature); the list is a
deliberate departure — one string to paste, quote, and diff — with the
per-feature alias kept for people who prefer brew's shape.
Spec: docs/specs/drafts/config-layers.md § Features.
"""
from __future__ import annotations

import os
import sys

from brew_hop_search.settings import FALSY, resolve

KNOWN_FEATURES: dict[str, str] = {
    "clock": "clock-style durations: `updated -0:40:12 ttl +5:19:48` (same as duration=clock)",
    "peek": "brew hop peek — list an untapped tap from GitHub (brew-hop-peek)",
}

_ALIAS_PREFIXES = ("BREW_HOP_FEATURE_", "HOMEBREW_HOP_FEATURE_")


def _from_aliases() -> set[str]:
    out: set[str] = set()
    for name, val in os.environ.items():
        for p in _ALIAS_PREFIXES:
            if name.startswith(p) and val and val.strip().lower() not in FALSY:
                out.add(name[len(p):].lower())
    return out


def features_enabled(tool: str = "search") -> set[str]:
    listed = {f.lower() for f in resolve("features", tool).value}
    return listed | _from_aliases()


def unknown_features(tool: str = "search") -> list[str]:
    return sorted(f for f in features_enabled(tool) if f not in KNOWN_FEATURES)


def feature_on(name: str, tool: str = "search") -> bool:
    return name.lower() in features_enabled(tool)


def enable_hint(name: str) -> str:
    return (f"{name} is experimental — enable it with BREW_HOP_FEATURES={name}\n"
            f"(under `brew hop`: HOMEBREW_HOP_FEATURES={name}; or [hop] features in config)")


def require_feature(name: str, tool: str = "search", prog: str = "") -> None:
    if feature_on(name, tool):
        return
    prefix = f"{prog}: " if prog else ""
    print(prefix + enable_hint(name), file=sys.stderr)
    sys.exit(2)
```

- [ ] **Step 4: `clock` feature ⇒ clock style**

In `defaults.py`:

```python
def duration_style() -> str:
    """`compact` (40m old) or `clock` (-0:40:12). The `clock` feature is the
    same switch spelled as a feature; see cache-flow.md § Duration style."""
    from brew_hop_search.features import feature_on
    if feature_on("clock", tool="search"):
        return "clock"
    return _get("duration")
```

- [ ] **Step 5: Spec paragraph**

In `docs/specs/features/cache-flow.md`, § "Duration style (experimental)", append after the tiers paragraph:

```
It is also the first entry in the features list: `BREW_HOP_FEATURES=clock`
(or `[hop] features = ["clock"]`) is the same switch, spelled the way
every other experiment will be (config-layers § Features). `duration =
"clock"` stays for when it graduates to a plain setting.
```

- [ ] **Step 6: Run tests, whole suite**

Run: `uv run python -m pytest tests/test_features.py -q --tb=short 2>&1 | tail -3` → PASS.
Run: `uv run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -1` → PASS.

- [ ] **Step 7: Commit**

```
feat(features): FEATURES list + per-feature alias; `clock` is the first feature

Experimental surfaces are now switched on by name — BREW_HOP_FEATURES=
peek,clock, the HOMEBREW_HOP twin, [hop] features in config, or brew's
one-var shape BREW_HOP_FEATURE_PEEK=1 — and a gated surface says how to
enable itself (exit 2) instead of hiding. Replaces the blanket
BREW_HOP_SEARCH_DRAFT=1 idea: the user picks which experiments to live
with. The clock duration trial is the first feature; peek is the next.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/features.py src/brew_hop_search/defaults.py docs/specs/features/cache-flow.md tests/test_features.py
git commit -q -F /path/to/c4.txt
```

---

### Task 5: Generated help — `--help=env` and `--help=features`

**Files:**
- Create: `src/brew_hop_search/settings_docs.py`
- Modify: `src/brew_hop_search/help_ui.py` (`show_scoped`: two new modes; the "known sections" hint)
- Modify: `docs/specs/features/help.md` (add the two modes to its mode table)
- Test: `tests/test_settings_docs.py`, snapshots `tests/snapshots/test_help_env.txt`, `tests/snapshots/test_help_features.txt`

**Interfaces:**
- Consumes: `settings.SETTINGS`, `settings.env_name`, `settings.config_key`, `features.KNOWN_FEATURES`, `features.features_enabled`.
- Produces:
  - `render_env_help(tool="search") -> str` — plain text (no color) for `--help=env`.
  - `render_features_help(tool="search") -> str`.
  - `render_man_environment() -> str` — Markdown for the man page block (used in Task 6).
  - `fmt_default(setting) -> str` — how a default is shown (`6h` for durations, `off`/`on` for bools, `~/.cache/…` for paths under home, `(none)` for None, `[]` for empty list).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_settings_docs.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""--help=env and --help=features are generated from the table."""
from __future__ import annotations

import re
import subprocess
import sys

from brew_hop_search.settings_testing import layers  # noqa: F401
from tests.snap import snap  # noqa: F401


def _run(*args, env=None):
    import os
    base = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    base["HOME"] = "/home/tester"           # stable path defaults in snapshots
    base.update(env or {})
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, env=base, timeout=30)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout + r.stderr)


def test_help_env(snap):
    snap.assert_match(_run("--help=env"))


def test_help_features(snap):
    snap.assert_match(_run("--help=features"))


def test_help_features_shows_on_when_enabled():
    out = _run("--help=features", env={"BREW_HOP_FEATURES": "clock"})
    assert re.search(r"clock\s+on\b", out)
    assert re.search(r"peek\s+off\b", out)


def test_every_setting_appears_in_env_help():
    from brew_hop_search.settings import SETTINGS, env_name
    out = _run("--help=env")
    for s in SETTINGS:
        assert env_name(s, s.scope) in out, s.key


def test_env_help_mentions_twin_once():
    out = _run("--help=env")
    assert out.count("HOMEBREW_HOP_") == 1


def test_fmt_default_shapes():
    from brew_hop_search.settings_docs import fmt_default
    from brew_hop_search.settings import SETTING_BY_KEY
    assert fmt_default(SETTING_BY_KEY["stale_api"]) == "6h"
    assert fmt_default(SETTING_BY_KEY["timing"]) == "on"
    assert fmt_default(SETTING_BY_KEY["ua"]) == "(none)"
    assert fmt_default(SETTING_BY_KEY["features"]) == "[]"
    assert fmt_default(SETTING_BY_KEY["db"]).startswith("~/")


def test_unknown_mode_hint_lists_env_and_features():
    out = _run("--help=nope")
    assert "env" in out and "features" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_settings_docs.py -q --tb=line 2>&1 | tail -4`
Expected: `test_help_env` / `test_help_features` write snapshots containing the "unknown help mode" error (first run writes) — **delete those two snapshot files after this run** so the real output gets captured in Step 5: `rm tests/snapshots/test_help_env.txt tests/snapshots/test_help_features.txt`. The others FAIL (`ModuleNotFoundError` for `settings_docs`; env help text absent).

- [ ] **Step 3: Write `settings_docs.py`**

```python
# src/brew_hop_search/settings_docs.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Text generated from the settings table: --help=env, --help=features, man § ENVIRONMENT."""
from __future__ import annotations

from pathlib import Path

from brew_hop_search.settings import SETTINGS, Setting, env_name, config_key, SCOPES
from brew_hop_search.display import fmt_duration

_SCOPE_TITLE = {"hop": "every brew-hop tool", "search": "brew-hop-search", "peek": "brew-hop-peek"}


def fmt_default(s: Setting) -> str:
    d = s.default
    if d is None:
        return "(none)"
    if s.kind == "bool":
        return "on" if d else "off"
    if s.kind == "duration":
        return fmt_duration(int(d), sub_minute=True)
    if s.kind == "list":
        return "[" + ",".join(d) + "]"
    if s.kind == "path":
        p = Path(d)
        try:
            return "~/" + str(p.relative_to(Path.home()))
        except ValueError:
            return str(p)
    return str(d)


def _rows(scope: str) -> list[Setting]:
    return [s for s in SETTINGS if s.scope == scope]


def render_env_help(tool: str = "search") -> str:
    out = [
        "  settings",
        "",
        "    flag > tool env > family env > config [tool] > config [hop] > default",
        "    Every BREW_HOP… name has a HOMEBREW_HOP… twin: brew filters the",
        "    environment to HOMEBREW_* before running `brew hop`, so use the twin there.",
        "",
    ]
    for scope in SCOPES:
        rows = _rows(scope)
        if not rows:
            continue
        out.append(f"  [{scope}]  {_SCOPE_TITLE[scope]}")
        width = max(len(env_name(s, scope)) for s in rows)
        for s in rows:
            name = env_name(s, scope).ljust(width)
            cfg = "" if s.env_only else f"  {config_key(s, scope)}"
            out.append(f"    {name}  {s.kind:<8} {fmt_default(s):<14}{cfg}")
            out.append(f"    {'':{width}}  {s.doc}")
        out.append("")
    out.append("  override for one tool: BREW_HOP_SEARCH_<KEY> / BREW_HOP_PEEK_<KEY>, or [search] / [peek] in config")
    return "\n".join(out) + "\n"


def render_features_help(tool: str = "search") -> str:
    from brew_hop_search.features import KNOWN_FEATURES, features_enabled, unknown_features
    on = features_enabled(tool)
    out = ["  features  (experimental; off by default; outside the 1.0 promise)", ""]
    width = max(len(n) for n in KNOWN_FEATURES)
    for name, doc in KNOWN_FEATURES.items():
        state = "on " if name in on else "off"
        out.append(f"    {name.ljust(width)}  {state}  {doc}")
    unk = unknown_features(tool)
    if unk:
        out += ["", f"    enabled but unknown (ignored): {', '.join(unk)}"]
    out += ["",
            "    enable:  BREW_HOP_FEATURES=peek,clock   (comma list)",
            "             BREW_HOP_FEATURE_PEEK=1         (one per feature)",
            "             [hop] features = [\"peek\"]      (config.toml)",
            "             under `brew hop`: HOMEBREW_HOP_FEATURES=…"]
    return "\n".join(out) + "\n"


def render_man_environment() -> str:
    """Markdown for the man page's ENVIRONMENT section, between the generated markers."""
    out = ["Every `BREW_HOP…` name below has a `HOMEBREW_HOP…` twin; `brew hop` only",
           "passes `HOMEBREW_*` through, so set the twin when running under brew.",
           "Precedence: flag > tool env > family env > config `[tool]` > config `[hop]` > default.",
           ""]
    for scope in SCOPES:
        rows = _rows(scope)
        if not rows:
            continue
        out.append(f"### [{scope}] — {_SCOPE_TITLE[scope]}")
        out.append("")
        for s in rows:
            cfg = "" if s.env_only else f" (config: `{config_key(s, scope)}`)"
            out.append(f"* `{env_name(s, scope)}`:")
            out.append(f"  {s.doc}. Default `{fmt_default(s)}`{cfg}.")
            out.append("")
    return "\n".join(out).rstrip() + "\n"
```

- [ ] **Step 4: Wire the two modes into `help_ui.show_scoped`**

At the top of `show_scoped`, right after the `query` check:

```python
    if mode.lower() == "env":
        from brew_hop_search.settings_docs import render_env_help
        sys.stdout.write(render_env_help())
        return 0
    if mode.lower() == "features":
        from brew_hop_search.settings_docs import render_features_help
        sys.stdout.write(render_features_help())
        return 0
```

And in the "Neither — suggest" branch, add the two names to the sections set:

```python
    sections |= {"env", "features"}
```

(insert after `sections.discard("")`). Also in `show_contextual`'s "more help" footer, change the example line to `e.g. --help=sources, --help=env, --help=features`.

- [ ] **Step 5: Run; capture snapshots; review them by eye**

Run: `uv run python -m pytest tests/test_settings_docs.py -q --tb=short 2>&1 | tail -3`
Expected: PASS (the two snapshot tests write their files on this first run). Open `tests/snapshots/test_help_env.txt` and confirm: three scope blocks, `HOMEBREW_HOP_` appears once, no absolute `/home/tester` paths leak past the `~/` form.

Run: `uv run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -1`
Expected: PASS. The existing `test_help_contextual_*` snapshots will change because the "more help" line changed → `UPDATE_SNAPSHOTS=1 uv run python -m pytest tests/test_help.py -q` and re-run.

- [ ] **Step 6: Spec**

In `docs/specs/features/help.md`, in the table of `--help=<mode>` values, add two rows:

```
| `env`      | every setting: env names per scope, kind, default, config key; the HOMEBREW_HOP twin rule once at the top |
| `features` | experimental surfaces with on/off state and how to enable them |
```

- [ ] **Step 7: Commit**

```
feat(help): --help=env and --help=features, generated from the settings table

The table is the one place a setting is declared, so it is the one
place its documentation comes from: `--help=env` lists every name per
scope with kind, default and config key (the HOMEBREW_HOP twin rule
said once, at the top, not per row); `--help=features` lists each
experiment with its on/off state and the three ways to enable it.
Snapshotted; a test asserts every SETTINGS row appears.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/settings_docs.py src/brew_hop_search/help_ui.py docs/specs/features/help.md tests/test_settings_docs.py tests/snapshots/test_help_env.txt tests/snapshots/test_help_features.txt tests/snapshots/test_help_contextual_*.txt
git commit -q -F /path/to/c5.txt
```

---

### Task 6: Man page ENVIRONMENT block (generated, round-trip tested) and the `-C -v` non-defaults dump

**Files:**
- Create: `scripts/gen-man-env.py`
- Modify: `docs/brew-hop-search.1.md:194-198` (ENVIRONMENT section gets marker comments and generated body)
- Modify: `Makefile` (target `man-env`)
- Modify: `src/brew_hop_search/cli.py` (`show_cache_status`, `show_cache_status_json`)
- Modify: `docs/specs/features/cache-status.md` (the `-C -v` settings lines)
- Test: `tests/test_settings_docs.py` (append), `tests/test_cache_status_settings.py` (new)

**Interfaces:**
- Consumes: `settings_docs.render_man_environment()`, `settings.SETTINGS`, `settings.resolve`.
- Produces:
  - `settings_docs.non_defaults(tool="search") -> list[tuple[str, str, str]]` — `(display_name, shown_value, source)` for every setting whose source is not `default`; secrets show `set`; booleans show `on`/`off`; lists comma-joined; durations via `fmt_duration(..., sub_minute=True)`.
  - `settings_docs.MAN_BEGIN = "<!-- settings:begin (generated by scripts/gen-man-env.py; do not edit) -->"`, `MAN_END = "<!-- settings:end -->"`.
  - `settings_docs.notes(tool) -> list[str]` — every `Resolved.notes` line across the table (twin conflicts, ignored garbage), deduplicated, for `-v`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings_docs.py`:

```python
def test_man_environment_block_is_current():
    """docs/brew-hop-search.1.md carries the generated block verbatim.
    Regenerate with `make man-env` when SETTINGS changes."""
    from pathlib import Path
    from brew_hop_search.settings_docs import render_man_environment, MAN_BEGIN, MAN_END
    text = (Path(__file__).resolve().parents[1] / "docs" / "brew-hop-search.1.md").read_text()
    start, end = text.index(MAN_BEGIN) + len(MAN_BEGIN), text.index(MAN_END)
    assert text[start:end].strip("\n") == render_man_environment().strip("\n")


def test_non_defaults_lists_only_overrides(layers):
    from brew_hop_search.settings_docs import non_defaults
    assert non_defaults() == []
    layers.set_env("BREW_HOP_SEARCH_STALE_API", "2h")
    layers.set_config("hop", "format", "table")
    layers.set_env("BREW_HOP_GITHUB_TOKEN", "ghp_SENTINEL")
    rows = non_defaults()
    assert ("BREW_HOP_SEARCH_STALE_API", "2h", "env:BREW_HOP_SEARCH_STALE_API") in rows
    assert ("BREW_HOP_FORMAT", "table", "config:[hop] format") in rows
    assert ("BREW_HOP_GITHUB_TOKEN", "set", "env:BREW_HOP_GITHUB_TOKEN") in rows
    assert not any("ghp_" in str(r) for r in rows)


def test_notes_collects_twin_conflicts_and_garbage(layers):
    from brew_hop_search.settings_docs import notes
    layers.set_env("BREW_HOP_FORMAT", "json")
    layers.set_env("HOMEBREW_HOP_FORMAT", "table")
    layers.set_env("BREW_HOP_SEARCH_STALE_API", "soon")
    got = notes()
    assert "BREW_HOP_FORMAT=json overrides HOMEBREW_HOP_FORMAT=table" in got
    assert any("STALE_API='soon' ignored" in n for n in got)
```

New `tests/test_cache_status_settings.py`:

```python
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""-C -v prints non-default settings with their source; -C --json carries them."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys


def _run(*args, env):
    base = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    base.update(env)
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.cli", *args],
                       capture_output=True, text=True, env=base, timeout=30)
    return re.sub(r"\033\[[0-9;]*m", "", r.stdout), re.sub(r"\033\[[0-9;]*m", "", r.stderr)


def test_c_verbose_lists_non_defaults(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_STALE_API": "2h", "BREW_HOP_GITHUB_TOKEN": "ghp_SENTINEL"}
    out, _ = _run("-C", "-v", env=env)
    assert re.search(r"settings.*non-default", out)
    assert "BREW_HOP_SEARCH_STALE_API  2h  env:BREW_HOP_STALE_API" in out
    assert "BREW_HOP_GITHUB_TOKEN" in out and "set" in out
    assert "ghp_" not in out


def test_c_default_is_silent_about_settings(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_STALE_API": "2h"}
    out, _ = _run("-C", env=env)
    assert "BREW_HOP_STALE_API" not in out


def test_c_verbose_prints_notes(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_FORMAT": "json", "HOMEBREW_HOP_FORMAT": "table"}
    _, err = _run("-C", "-v", env=env)
    assert "# [env] BREW_HOP_FORMAT=json overrides HOMEBREW_HOP_FORMAT=table" in err


def test_c_json_carries_settings(tmp_path):
    env = {"BREW_HOP_SEARCH_DB": str(tmp_path / "x.db"),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_STALE_API": "2h", "BREW_HOP_FEATURES": "clock"}
    out, _ = _run("-C", "--json", env=env)
    data = json.loads(out)
    # Keyed by the name in the setting's own scope (stale_api is a search setting);
    # `source` says which layer actually answered (here the family-scope env var).
    assert data["settings"]["BREW_HOP_SEARCH_STALE_API"] == {
        "value": "2h", "source": "env:BREW_HOP_STALE_API"}
    assert data["features"] == ["clock"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_settings_docs.py tests/test_cache_status_settings.py -q --tb=line 2>&1 | tail -8`
Expected: the new tests FAIL (`ImportError` for `MAN_BEGIN`/`non_defaults`/`notes`; `-C` output lacks settings; JSON lacks `settings`).

- [ ] **Step 3: Add `non_defaults`, `notes`, markers to `settings_docs.py`**

```python
MAN_BEGIN = "<!-- settings:begin (generated by scripts/gen-man-env.py; do not edit) -->"
MAN_END = "<!-- settings:end -->"


def _shown(s: Setting, value) -> str:
    if s.kind == "secret":
        return "set"
    if s.kind == "bool":
        return "on" if value else "off"
    if s.kind == "duration":
        return fmt_duration(int(value), sub_minute=True)
    if s.kind == "list":
        return ",".join(value)
    return str(value)


def non_defaults(tool: str = "search") -> list[tuple[str, str, str]]:
    from brew_hop_search.settings import resolve
    rows = []
    for s in SETTINGS:
        r = resolve(s.key, tool)
        if r.source == "default":
            continue
        rows.append((env_name(s, s.scope), _shown(s, r.value), r.source))
    return rows


def notes(tool: str = "search") -> list[str]:
    from brew_hop_search.settings import resolve
    seen: list[str] = []
    for s in SETTINGS:
        for n in resolve(s.key, tool).notes:
            if n not in seen:
                seen.append(n)
    return seen
```

- [ ] **Step 4: Man page: markers + generator + Makefile target**

`scripts/gen-man-env.py`:

```python
#!/usr/bin/env python3
"""Regenerate the ENVIRONMENT block in docs/brew-hop-search.1.md from settings.py.
Run: make man-env   (tests/test_settings_docs.py fails when the block is stale)."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brew_hop_search.settings_docs import render_man_environment, MAN_BEGIN, MAN_END  # noqa: E402

doc = Path(__file__).resolve().parents[1] / "docs" / "brew-hop-search.1.md"
text = doc.read_text()
start, end = text.index(MAN_BEGIN) + len(MAN_BEGIN), text.index(MAN_END)
doc.write_text(text[:start] + "\n" + render_man_environment() + text[end:])
print(f"updated {doc}")
```

In `docs/brew-hop-search.1.md`, replace the ENVIRONMENT section body (lines 196-197, the single `BREW_HOP_SEARCH_DB` bullet) with:

```
<!-- settings:begin (generated by scripts/gen-man-env.py; do not edit) -->
<!-- settings:end -->
```

Then run `uv run python scripts/gen-man-env.py` to fill it. Makefile, after the `readme:` target:

```make
man-env: ## Regenerate the man page ENVIRONMENT block from settings.py
	uv run python scripts/gen-man-env.py
```

(`.PHONY` line: add `man-env`.)

- [ ] **Step 5: `-C -v` dump, `-v` notes, `-C --json`**

In `cli.py` `show_cache_status`, **right after** the `_show_brew_version(verbose, force=refresh_brew)` call and **before** the `if not db_exists:` early return (settings exist whether or not the DB does — the test runs with a DB path that does not exist):

```python
    if verbose >= 2:
        from brew_hop_search.settings_docs import non_defaults, notes
        from brew_hop_search.features import features_enabled
        rows = non_defaults()
        feats = sorted(features_enabled())
        print(f"  {bold('settings')}  {len(rows)} non-default"
              + (f"  ·  features: {', '.join(feats)}" if feats else ""))
        for name, shown, source in rows:
            print(f"    {name}  {shown}  {dim(source)}")
        for n in notes():
            print(dim(f"  # [env] {n}"), file=sys.stderr)
```

In `show_cache_status_json`, add to `info` before the envelope:

```python
    from brew_hop_search.settings_docs import non_defaults
    from brew_hop_search.features import features_enabled
    info["settings"] = {name: {"value": shown, "source": source}
                        for name, shown, source in non_defaults()}
    info["features"] = sorted(features_enabled())
```

- [ ] **Step 6: Run, then whole suite**

Run: `uv run python -m pytest tests/test_settings_docs.py tests/test_cache_status_settings.py -q --tb=short 2>&1 | tail -3` → PASS.
Run: `uv run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -1` → PASS.

- [ ] **Step 7: Spec**

In `docs/specs/features/cache-status.md`, add under the `-v` description:

```
`-C -v` ends with a `settings` block: every setting whose value did not
come from its default, as `NAME  value  source` (secrets show `set`),
plus the enabled features; `# [env]` stderr lines report twin conflicts
and ignored garbage. `-C --json` carries the same as `settings` and
`features`. Generated from the settings table (config-layers).
```

- [ ] **Step 8: Commit**

```
feat(cli,docs): man ENVIRONMENT block generated from the table; -C -v lists non-default settings

The man page's ENVIRONMENT section listed one variable. It now carries
a generated block (markers, `make man-env`) and a test fails when the
block is stale, so the table and the man page can't drift. `-C -v`
prints every non-default setting with the layer it came from, `set`
for secrets, and the enabled features; `-C --json` mirrors it. Twin
conflicts and ignored garbage surface as `# [env]` lines at -v — the
answer to "why isn't my env var doing anything".

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add scripts/gen-man-env.py docs/brew-hop-search.1.md Makefile src/brew_hop_search/settings_docs.py src/brew_hop_search/cli.py docs/specs/features/cache-status.md tests/test_settings_docs.py tests/test_cache_status_settings.py
git commit -q -F /path/to/c6.txt
```

---

### Task 7: `-v` reports env notes in search too; `--help=env` mentioned in `-h`

**Files:**
- Modify: `src/brew_hop_search/cli.py` (search path, after the brewver skipped report, before the reminder line)
- Modify: `src/brew_hop_search/help_ui.py` (`show_terse` "more help" lines)
- Test: `tests/test_cache_status_settings.py` (append one test)

**Interfaces:**
- Consumes: `settings_docs.notes()`.
- Produces: nothing new.

- [ ] **Step 1: Failing test**

Append to `tests/test_cache_status_settings.py`:

```python
def test_search_verbose_prints_env_notes(tmp_path):
    from tests.test_output import _seed_db
    db = tmp_path / "t.db"
    _seed_db(db)
    env = {"BREW_HOP_SEARCH_DB": str(db),
           "BREW_HOP_SEARCH_CONFIG": str(tmp_path / "none.toml"),
           "BREW_HOP_SEARCH_STALE_API": "soon"}
    _, err = _run("-v", "python", env=env)
    assert "# [env] BREW_HOP_SEARCH_STALE_API='soon' ignored: not a duration" in err
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_cache_status_settings.py::test_search_verbose_prints_env_notes -q --tb=line` → FAIL (no `# [env]` line).

- [ ] **Step 3: Implement**

In `cli.py`, in the search path right after the `brewver.skipped_report()` loop (the `if verbose >= 2:` block that prints `# [brew]` lines), add:

```python
    if verbose >= 2:
        from brew_hop_search.settings_docs import notes
        for n in notes():
            print(dim(f"  # [env] {n}"), file=sys.stderr)
```

In `help_ui.show_terse`, where the "more help" hints are printed, add a line `--help=env / --help=features   settings and experiments` (match the surrounding format; update `tests/snapshots/test_help_terse.txt` with `UPDATE_SNAPSHOTS=1` and check the diff is only that line).

- [ ] **Step 4: Run, whole suite, commit**

Run: `uv run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -1` → PASS.

```
feat(cli): surface ignored/conflicting env at -v in search; point -h at --help=env

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/cli.py src/brew_hop_search/help_ui.py tests/test_cache_status_settings.py tests/snapshots/test_help_terse.txt
git commit -q -F /path/to/c7.txt
```

---

### Task 8: The `brew-hop` dispatcher

**Files:**
- Create: `src/brew_hop_search/hop.py`
- Modify: `pyproject.toml` (`[project.scripts]`: add `brew-hop = "brew_hop_search.hop:main"`)
- Modify: `docs/specs/drafts/config-layers.md` § `brew hop` dispatch (status line: shipped), `README.md` (one paragraph under install/usage: `brew hop search`)
- Modify: `CHANGELOG.md`
- Test: `tests/test_hop.py`

**Interfaces:**
- Consumes: `features.feature_on`, `features.enable_hint`, `features.KNOWN_FEATURES`.
- Produces:
  - `VERBS: tuple[Verb, ...]` with `Verb(name, entry: str | None, feature: str | None, doc: str)`; initial: `Verb("search", "brew_hop_search.cli:main", None, "search formulae, casks, taps, installed")`, `Verb("peek", None, "peek", "list an untapped tap from GitHub")`.
  - `promote_env(environ: dict) -> dict` — copy every `HOMEBREW_HOP_<X>` to `BREW_HOP_<X>` when the latter is unset (and vice versa), returning a new dict.
  - `find_executable(verb, argv0_dir) -> str | None` — `brew-hop-<verb>` next to the running binary first, then `shutil.which`.
  - `main(argv=None) -> int` — dispatch; bare → verb list, exit 0; unknown → list, exit 2; feature off → `enable_hint`, exit 2; `--help`/`-h`/`help` → same as bare.

- [ ] **Step 1: Failing tests**

```python
# tests/test_hop.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""brew-hop: git-style dispatcher. `brew hop search …` → brew-hop-search.
Spec: docs/specs/drafts/config-layers.md § brew hop dispatch."""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys

import pytest

from brew_hop_search.settings_testing import layers  # noqa: F401


def test_promote_env_both_directions():
    from brew_hop_search.hop import promote_env
    env = promote_env({"HOMEBREW_HOP_FORMAT": "json", "BREW_HOP_DB": "/x", "PATH": "/bin"})
    assert env["BREW_HOP_FORMAT"] == "json"
    assert env["HOMEBREW_HOP_DB"] == "/x"
    assert env["PATH"] == "/bin"


def test_promote_env_never_overwrites():
    from brew_hop_search.hop import promote_env
    env = promote_env({"HOMEBREW_HOP_FORMAT": "json", "BREW_HOP_FORMAT": "table"})
    assert env["BREW_HOP_FORMAT"] == "table"


def test_bare_lists_verbs_with_feature_state(layers, capsys):
    from brew_hop_search.hop import main
    assert main([]) == 0
    out = capsys.readouterr().out
    assert re.search(r"search\s", out)
    assert re.search(r"peek\s.*experimental, off", out)
    layers.set_env("BREW_HOP_FEATURES", "peek")
    main([])
    assert "experimental, on" in capsys.readouterr().out


def test_unknown_verb_exits_2_with_list(capsys):
    from brew_hop_search.hop import main
    assert main(["frobnicate"]) == 2
    err = capsys.readouterr().err
    assert "unknown verb: frobnicate" in err and "search" in err


def test_gated_verb_off_exits_2_with_hint(layers, capsys):
    from brew_hop_search.hop import main
    assert main(["peek", "user/repo"]) == 2
    assert "BREW_HOP_FEATURES=peek" in capsys.readouterr().err


def test_gated_verb_on_but_not_installed(layers, capsys, monkeypatch):
    from brew_hop_search import hop
    layers.set_env("BREW_HOP_FEATURES", "peek")
    monkeypatch.setattr(hop, "find_executable", lambda verb, d: None)
    assert hop.main(["peek", "user/repo"]) == 2
    assert "brew-hop-peek is not installed" in capsys.readouterr().err


def test_execs_sibling_binary_with_argv_and_promoted_env(tmp_path):
    """End to end: a fake brew-hop-search on PATH receives argv intact and the twin env."""
    fake = tmp_path / "brew-hop-search"
    fake.write_text("#!/bin/sh\nprintf 'argv:%s\\n' \"$@\"\nprintf 'fmt:%s\\n' \"$BREW_HOP_FORMAT\"\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BREW_HOP", "HOMEBREW_HOP"))}
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    env["HOMEBREW_HOP_FORMAT"] = "json"
    r = subprocess.run([sys.executable, "-m", "brew_hop_search.hop", "search", "foo", "--bar"],
                       capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "argv:foo\nargv:--bar\n" in r.stdout      # argv passed through, in order
    assert "fmt:json" in r.stdout                     # HOMEBREW_HOP_FORMAT promoted to BREW_HOP_FORMAT


def test_in_process_fallback_when_no_binary(monkeypatch, capsys):
    from brew_hop_search import hop
    monkeypatch.setattr(hop, "find_executable", lambda verb, d: None)
    called = {}
    monkeypatch.setattr(hop, "_import_entry", lambda entry: (lambda argv: called.setdefault("argv", argv) or 0))
    assert hop.main(["search", "python"]) == 0
    assert called["argv"] == ["python"]


def test_help_forms_list_verbs(capsys):
    from brew_hop_search.hop import main
    for form in (["--help"], ["-h"], ["help"]):
        assert main(form) == 0
        assert "search" in capsys.readouterr().out


def test_project_scripts_declare_brew_hop():
    import tomllib
    from pathlib import Path
    data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["brew-hop"] == "brew_hop_search.hop:main"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run python -m pytest tests/test_hop.py -q --tb=line 2>&1 | tail -3` → `ModuleNotFoundError: brew_hop_search.hop`.

- [ ] **Step 3: Write `hop.py`**

```python
# src/brew_hop_search/hop.py
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""`brew-hop`: the git-style dispatcher behind `brew hop <verb>`.

Homebrew runs any `brew-<name>` on PATH as `brew <name>` (since 2010), so
`brew hop search python` reaches us with argv = ["search", "python"]. We
exec `brew-hop-<verb>` — next to this binary first, then PATH — with the
rest of argv untouched, falling back to importing the verb's entry point
in-process. Verbs are independent programs; this file only routes.

brew filters the environment to HOMEBREW_* before exec'ing us, so we
promote HOMEBREW_HOP_<X> to BREW_HOP_<X> (and back) for the child: a tool
may read either name and see the same value.
Spec: docs/specs/drafts/config-layers.md § `brew hop` dispatch.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Verb:
    name: str
    entry: str | None      # "pkg.module:function" for in-process fallback
    feature: str | None    # feature that must be on, or None
    doc: str


VERBS: tuple[Verb, ...] = (
    Verb("search", "brew_hop_search.cli:main", None, "search formulae, casks, taps, installed"),
    Verb("peek", None, "peek", "list an untapped tap from GitHub (brew-hop-peek)"),
)
_BY_NAME = {v.name: v for v in VERBS}


def promote_env(environ: dict) -> dict:
    env = dict(environ)
    for name, val in environ.items():
        if name.startswith("HOMEBREW_HOP_"):
            twin = "BREW_HOP_" + name[len("HOMEBREW_HOP_"):]
        elif name.startswith("BREW_HOP_"):
            twin = "HOMEBREW_HOP_" + name[len("BREW_HOP_"):]
        else:
            continue
        env.setdefault(twin, val)
    return env


def find_executable(verb: str, argv0_dir: str) -> str | None:
    name = f"brew-hop-{verb}"
    local = os.path.join(argv0_dir, name)
    if os.access(local, os.X_OK):
        return local
    return shutil.which(name)


def _import_entry(entry: str):
    mod, fn = entry.split(":")
    return getattr(importlib.import_module(mod), fn)


def _list_verbs(stream) -> None:
    from brew_hop_search.features import feature_on
    print("usage: brew hop <verb> [args…]      (or brew-hop, brew-hop-<verb>)", file=stream)
    print("", file=stream)
    width = max(len(v.name) for v in VERBS)
    for v in VERBS:
        tag = ""
        if v.feature:
            tag = f"  (experimental, {'on' if feature_on(v.feature) else 'off'})"
        print(f"  {v.name.ljust(width)}  {v.doc}{tag}", file=stream)
    print("", file=stream)
    print("  --help=features on any verb explains experiments", file=stream)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        _list_verbs(sys.stdout)
        return 0
    name, rest = argv[0], argv[1:]
    verb = _BY_NAME.get(name)
    if verb is None:
        print(f"brew hop: unknown verb: {name}", file=sys.stderr)
        _list_verbs(sys.stderr)
        return 2
    if verb.feature:
        from brew_hop_search.features import feature_on, enable_hint
        if not feature_on(verb.feature, tool=verb.name):
            print(f"brew hop {name}: " + enable_hint(verb.feature), file=sys.stderr)
            return 2
    env = promote_env(os.environ)
    exe = find_executable(name, os.path.dirname(os.path.abspath(sys.argv[0])))
    if exe:
        os.execve(exe, [exe, *rest], env)   # does not return
    if verb.entry is None:
        print(f"brew hop {name}: brew-hop-{name} is not installed", file=sys.stderr)
        return 2
    os.environ.update(env)
    fn = _import_entry(verb.entry)
    result = fn(rest)
    return int(result or 0)


if __name__ == "__main__":
    sys.exit(main())
```

`pyproject.toml`:

```toml
[project.scripts]
brew-hop = "brew_hop_search.hop:main"
brew-hop-search = "brew_hop_search.cli:main"
brewhs = "brew_hop_search.cli:main"
```

Note: `cli.main(argv)` accepts an argv list already (it's called that way in tests), so the in-process fallback passes `rest` straight through.

- [ ] **Step 4: Run; fix; whole suite**

Run: `uv run python -m pytest tests/test_hop.py -q --tb=short 2>&1 | tail -5` → PASS.
Run: `uv sync -q && uv run brew-hop` → prints the verb list (confirms the script entry).
Run: `uv run python -m pytest tests/ -x -q --tb=short 2>&1 | tail -1` → PASS.

- [ ] **Step 5: Docs**

`README.md`: after the install section, add:

```
### `brew hop`

Homebrew runs any `brew-<name>` on your PATH as `brew <name>`, so once
installed:

    brew hop search python      # same as brew-hop-search python
    brew hop                    # list verbs

Under `brew hop`, brew passes only `HOMEBREW_*` through, so set
`HOMEBREW_HOP_…` instead of `BREW_HOP_…` (`brew-hop-search --help=env`).
```

`docs/specs/drafts/config-layers.md`: in § Status add `**Shipped 2026-MM-DD:** table, harness, wiring, features, --help=env/features, man block, -C -v dump, brew-hop dispatcher (steps 1–5).` with today's date.

`CHANGELOG.md` Unreleased highlights, add:

```
- **`brew hop`.** A `brew-hop` dispatcher: `brew hop search python`
  runs `brew-hop-search`; `brew hop` lists verbs. Experimental verbs are
  listed with their on/off state and say how to enable themselves.
- **Features.** `BREW_HOP_FEATURES=clock` (or `BREW_HOP_FEATURE_CLOCK=1`,
  or `[hop] features`) switches experiments on by name; `--help=features`
  lists them. `--help=env` lists every setting, per scope, with defaults.
```

- [ ] **Step 6: Commit**

```
feat(hop): brew-hop dispatcher — `brew hop <verb>` execs brew-hop-<verb>, promotes HOMEBREW_HOP env

The subcommand layer lands at the process boundary, not inside one
argparse tree: `brew-hop` routes `brew hop search …` to the unchanged
`brew-hop-search` (next to itself, then PATH, then in-process), lists
verbs with their feature state when bare, and refuses unknown or
gated verbs with the list or the enable hint (exit 2). Because brew
filters the environment to HOMEBREW_*, the dispatcher promotes
HOMEBREW_HOP_<X> to BREW_HOP_<X> for the child. `peek` is registered
as a gated verb with no binary yet, so the routing is tested before
the tool exists.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

```bash
git add src/brew_hop_search/hop.py pyproject.toml uv.lock README.md docs/specs/drafts/config-layers.md CHANGELOG.md tests/test_hop.py
git commit -q -F /path/to/c8.txt
```

---

### Task 9: Close out — beads, push, hand-off

**Files:**
- Modify: `.beads/issues.jsonl` via `br`

- [ ] **Step 1: Full suite one last time**

Run: `uv run python -m pytest tests/ -q --tb=short 2>&1 | tail -1` → PASS; note the count in the hand-off.

- [ ] **Step 2: Beads**

```bash
br update bhs-o2d --status closed --notes "Shipped on feat/peek: settings.py table, settings_testing harness, wiring, features.py, --help=env/features, man block + gen script, -C -v dump, hop.py dispatcher. peek (bhs-u7e) unblocked."
br sync --flush-only
git add .beads/issues.jsonl
git commit -q -m "chore(beads): close bhs-o2d config-layers" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 3: Push and verify**

```bash
git push -u origin feat/peek
git status -sb | head -1     # must read: ## feat/peek...origin/feat/peek
```

- [ ] **Step 4: Hand-off note**

Append to `sessions/<today>-requests.md` (gitignored, local): the commit list, the test count, and that `peek` implementation is next and starts from `docs/specs/drafts/peek.md` rev 2 with `require_feature("peek", tool="peek", prog="brew hop peek")` as its first line.
