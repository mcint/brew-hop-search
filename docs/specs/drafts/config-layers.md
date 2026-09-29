---
title: config-layers — one settings table, three namespaces, a features list, and a test harness others can reuse
date: 2026-09-28
kind: draft-spec
status: draft — awaiting user review
tldr: >
  Replace the scattered `os.environ.get("BREW_HOP_SEARCH_…")` calls with one
  declarative settings table that generates env names, config.toml keys,
  `--help=env`, the man ENVIRONMENT section, and a non-defaults dump.
  Namespaces: family-wide `BREW_HOP_<KEY>`, tool-specific
  `BREW_HOP_SEARCH_<KEY>` / `BREW_HOP_PEEK_<KEY>`, each mirrored as
  `HOMEBREW_HOP…` because `brew hop` strips every non-HOMEBREW_* variable.
  Precedence: flag > tool env > family env > config [tool] > config [hop] >
  default. Booleans and NO_ negations follow brew. `FEATURES=peek,…` is one
  comma list (a deliberate departure from brew's one-var-per-feature, with
  per-feature aliases accepted). A parametrized harness tests every key's
  precedence automatically and ships importable for sibling tools.
---

# config-layers

`brew-hop-search` already layers `default < config.toml < env < flag`
(`defaults.py`, `_config.py`, `--stale`). It does so one setting at a
time, by hand, in five files. The next tool in the family (`peek`), the
`brew hop` entry point, and the user's wish for `BREW_HOP_*` alongside
`BREW_HOP_SEARCH_*` and `BREW_HOP_PEEK_*` make that a table job.

## Status

**Draft** — from the 2026-09-28 conversation ("composable ways to handle
the 12-factor env var / config stuff … make sure our testing there is
generalized, buttoned up, and ready for others to use"). Grounded in
[research: brew env config & external commands](../../research/2026-09-28-brew-env-config-and-external-commands.md).
Consumers: [peek](peek.md) (first tool-specific namespace),
[cli-vocabulary](cli-vocabulary.md) § Option B (`brew hop` dispatch),
[cache-flow](../features/cache-flow.md) (the `DURATION` trial becomes a
table row). Supersedes the `BREW_HOP_SEARCH_DRAFT=1` gate proposed in
`research/2026-09-14-strategy-toward-1-0.md`.

## Purpose

1. **One place.** A setting is declared once — name, kind, default,
   scope, one-line doc — and everything else is derived: the env names
   in every namespace, the `config.toml` key, the `--help=env` section,
   the man page's ENVIRONMENT section, the `-C -v` / `config` dump.
   Today `defaults.py` docstrings, `help_ui`, the man page and
   `_config.py` each carry their own partial list.
2. **Survive `brew hop`.** `bin/brew` runs external commands with the
   environment filtered to `HOMEBREW_*` (verified: `BREW_HOP_X=1` does
   not arrive, `HOMEBREW_HOP_X=1` does). Every name therefore has a
   `HOMEBREW_HOP…` twin, or `brew hop peek` silently ignores the user's
   config.
3. **Composable namespaces.** `BREW_HOP_FORMAT` sets the family default;
   `BREW_HOP_PEEK_FORMAT` overrides it for one tool. Same for
   `config.toml` tables.
4. **Tests that scale.** Adding a row must add its precedence tests for
   free, and a sibling tool must be able to `from brew_hop.settings.testing
   import layers` and get the same guarantees.

## Design

### Names

| layer            | search                    | peek                    | family (any tool)   |
|------------------|---------------------------|-------------------------|---------------------|
| env, direct      | `BREW_HOP_SEARCH_<KEY>`   | `BREW_HOP_PEEK_<KEY>`   | `BREW_HOP_<KEY>`    |
| env, via `brew hop` | `HOMEBREW_HOP_SEARCH_<KEY>` | `HOMEBREW_HOP_PEEK_<KEY>` | `HOMEBREW_HOP_<KEY>` |
| config.toml      | `[search] key`            | `[peek] key`            | `[hop] key`         |
| flag             | `--key` where one exists  | same                    | —                   |

`HOMEBREW_HOP…` and `BREW_HOP…` are **aliases at the same layer**. When
both are set to different values, `BREW_HOP…` wins (it can only have
been set by someone running the binary directly, which is the more
specific situation) and `-v` prints one line:
`# [env] BREW_HOP_FORMAT=json overrides HOMEBREW_HOP_FORMAT=table`.

Existing names keep working: `BREW_HOP_SEARCH_*` is the search
namespace, `BREW_HOP_SEARCH_CONFIG` still points at the file. Nothing
is renamed by this spec.

### Precedence

```
flag  >  tool env  >  family env  >  config [tool]  >  config [hop]  >  default
```

Env beats config at every scope, so a family env var beats a
tool-specific config key — the 12-factor rule (env is the deployment,
config is the install) is kept over "more specific wins". Written
out, for `FORMAT` in `peek`:

```
--json  >  BREW_HOP_PEEK_FORMAT  >  BREW_HOP_FORMAT  >  [peek] format  >  [hop] format  >  "default"
```

`config.toml` stays at `~/.config/brew-hop-search/config.toml` until the
package renames (then `~/.config/brew-hop/`, with the old path read as a
fallback for one release). `brew.env`-style files are **not** adopted:
we have a config file already, and brew's is `HOMEBREW_*`-only anyway.

### Kinds and parsing

| kind       | parse                                                     | example |
|------------|-----------------------------------------------------------|---------|
| `bool`     | brew's rule: set and not in `false no off nil 0` (case-insensitive) → on; empty == unset | `NO_TIMING=1` |
| `duration` | existing `parse_duration` (`30s 5m 6h 1d`)                | `STALE_API=6h` |
| `enum`     | canonical + aliases table (today's `_FORMAT_ALIASES`)      | `FORMAT=long` → `multi` |
| `list`     | **comma**-separated, whitespace trimmed, empties dropped   | `FEATURES=peek,clock` |
| `path`     | `~` and `$VAR` expanded                                    | `DB=~/x.db` |
| `str`      | as is                                                     | `UA=…` |
| `secret`   | as `str`; never echoed — dumps print `set`                 | `GITHUB_TOKEN` |

Comma, not brew's space, for lists: `--refresh=KIND,KIND` and
`--stale=KIND:DUR,…` already made commas the house separator; a
setting that mirrors a flag must parse the same text.

Default-on booleans get a `NO_` name, as brew does (`NO_TIMING`,
`NO_COLOR`), never a `TIMING=0`. The table declares the positive
concept and the generator emits the `NO_` env name.

### Features

```
BREW_HOP_FEATURES=peek,clock          # comma list, family scope
BREW_HOP_FEATURE_PEEK=1               # per-feature alias, also accepted
[hop] features = ["peek", "clock"]    # config form
```

A **feature** is an experimental surface — a whole tool (`peek`), a
verb, or a behavior (`clock` durations) — that is shipped but off by
default, may rename freely, and is excluded from the 1.0 promise. This
replaces the `BREW_HOP_SEARCH_DRAFT=1` blanket switch: the user picks
which experiments to live with.

Brew has no such list (one variable per feature; research § 1). The
list is a deliberate departure, for two reasons: one string is what a
user pastes into a `brew.env`/shell rc/CI line and what a bug report
quotes; and Cargo, Node and Python all made "features" a list the
reader already knows. The per-feature alias keeps brew's shape
available for people who prefer it. Unknown feature names warn at
`-v` and are otherwise ignored, so an old binary tolerates a new
config.

Surfacing: `--help=features` lists every feature with `on`/`off` and
one line each; a gated surface that is off says how to turn it on
(`peek is experimental — BREW_HOP_FEATURES=peek to enable`, exit 2)
rather than pretending not to exist; `-C -v` prints the enabled set.

### The table

```python
# brew_hop_search/settings.py  (moves to brew_hop/settings.py with the rename)
SETTINGS = [
    Setting("format",     "enum",     "default", scope="hop",    aliases=_FORMAT_ALIASES,
            doc="default output format when no format flag is given"),
    Setting("features",   "list",     [],        scope="hop",
            doc="experimental surfaces to enable (see --help=features)"),
    Setting("duration",   "enum",     "compact", scope="hop",    aliases={"compact": (), "clock": ()},
            doc="how ages/TTLs render: compact (40m old) or clock (-0:40:12)"),
    Setting("timing",     "bool",     True,      scope="hop",    negate=True,
            doc="the `# [time]` footer"),
    Setting("stale_api",  "duration", "6h",      scope="search", doc="index TTL"),
    Setting("stale_installed", "duration", "1h", scope="search"),
    Setting("stale_taps", "duration", "1h",      scope="search"),
    Setting("stale_local","duration", "1h",      scope="search"),
    Setting("stale_peek", "duration", "15m",     scope="peek"),
    Setting("db",         "path",     DB_PATH,   scope="hop"),
    Setting("config",     "path",     CONFIG_PATH, scope="hop", env_only=True),
    Setting("ua",         "str",      None,      scope="hop"),
    Setting("limit",      "str",      "20",      scope="search"),
    Setting("github_token", "secret", None,      scope="hop",
            doc="GitHub API token; else `gh auth token`; else anonymous"),
    …
]
```

`scope` is where the *default* lives; every setting is still
overridable in every narrower namespace (`BREW_HOP_PEEK_DB` works).
`settings.get("format", tool="peek")` does the whole resolution and
records *which layer answered*, so `-v` and the dump can say
`format = json (BREW_HOP_PEEK_FORMAT)`.

Generated from the table:

- `--help=env` — one block per scope, env name, default, doc; the
  `HOMEBREW_HOP…` twin mentioned once at the top, not per row.
- man page § ENVIRONMENT — same text, roff-ed at build time
  (`docs/brew-hop-search.1.md` gains a generated marker block).
- `-C -v` (and later `bhs config`) — non-defaults only, `set` for
  booleans and secrets, brew-`config`-style.
- `BREW_HOP_SEARCH_*` compatibility: the search-scope names are exactly
  today's names, so nothing the user has exported breaks.

`defaults.py` keeps its function names (`stale_api_seconds()` …) as thin
wrappers over `settings.get`, so the sources don't change.

### `brew hop` dispatch (the entry point, not a subcommand)

```
brew-hop <verb> [args…]      # `brew hop search python`, `brew hop peek user/repo`
brew-hop                     # lists verbs: search, peek (experimental), …
```

`brew-hop` is a **dispatcher**, git-style: it looks for `brew-hop-<verb>`
on `PATH` (and next to itself) and `exec`s it with the remaining argv;
failing that it imports the verb's `main` in-process. `brew-hop-search`
is the existing CLI unchanged; `brew-hop-peek` is its own entry point.
Neither knows about the other. This is the subcommand layer the
cli-vocabulary draft calls Option B, landed at the process boundary
instead of inside one argparse tree — which is why `peek` can ship
without `brew-hop-search` growing a verb.

Because brew filters the environment, the dispatcher also **promotes**
`HOMEBREW_HOP…` to `BREW_HOP…` in the child's environment when the
latter is unset, so a tool may read either name and see the same
value. Direct invocation gets the same promotion for symmetry.

Distribution: `brew-hop`, `brew-hop-search`, `brew-hop-peek`, `bhs` as
`[project.scripts]`; the tap Formula installs all four. A tap `cmd/`
copy is *not* shipped (it would fall under 6.0 tap trust and add
nothing over PATH dispatch).

### Testing — the reusable harness

`brew_hop_search/settings_testing.py` (importable by sibling tools):

```python
@pytest.fixture
def layers(tmp_path, monkeypatch):
    """Clean slate: no BREW_HOP*/HOMEBREW_HOP* in env, config at tmp."""
    ...
    yield Layers(set_env=…, set_config=…, set_flag=…)

# Auto-parametrized over SETTINGS: every row gets, without writing a test:
#   default          → declared default
#   config [hop]     → beats default
#   config [tool]    → beats [hop]
#   family env       → beats both config tables
#   tool env         → beats family env
#   HOMEBREW_HOP twin→ equals BREW_HOP form; BREW_HOP wins a conflict, -v says so
#   kind parsing     → bool falsy list, list commas, enum aliases, path expansion
#   secret           → dump prints `set`, never the value
#   flag (if any)    → beats everything
```

Plus the generated-docs round trip: `--help=env` and the man
ENVIRONMENT block are snapshotted, and a test fails if a `SETTINGS` row
is missing from either. `tests/test_config.py` and `test_defaults.py`
fold into this; existing env-var tests keep passing unchanged because
the names are unchanged.

## Examples

```sh
# family default, one tool overridden
export BREW_HOP_FORMAT=table
export BREW_HOP_PEEK_FORMAT=json

# under brew (env is filtered to HOMEBREW_*):
HOMEBREW_HOP_FEATURES=peek brew hop peek steipete/tap
# direct:
BREW_HOP_FEATURES=peek brew-hop-peek steipete/tap
bhs --help=env                 # every setting, every namespace, defaults
bhs --help=features            # what's experimental, what's on
bhs -C -v                      # non-default settings and where each came from
```

```toml
# ~/.config/brew-hop-search/config.toml
[hop]
format = "default"
features = ["peek"]
duration = "clock"

[search]
stale_api = "12h"

[peek]
format = "json"
```

## Migration

1. `settings.py` + harness, table populated from today's names; all
   existing tests green (names unchanged).
2. `defaults.py` / `_config.py` / `timing.py` / `cache.py` / `__init__.py`
   read through the table.
3. `--help=env`, man block, `-C -v` dump generated.
4. `FEATURES` + `--help=features`; the `DURATION=clock` trial and `peek`
   become the first two features.
5. `brew-hop` dispatcher + `[project.scripts]`.

Each step is a commit with its spec delta; 1–3 are pure refactor and
can ship in 0.4.x, 4–5 arrive with `peek`.
