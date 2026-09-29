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
