---
question: What should brew-hop-search try before declaring a stable 1.0, how might it evolve, and how do the CLI and the brew-hop-api read model coordinate versions?
date: 2026-09-14
kind: full-report
tldr: >
  1.0 should mean "the flag/verb surface, JSON envelope, schema version,
  and env/config names hold for two minors without a rename." Three
  changes are breaking enough that they must land first: the subcommand
  layer (with an implicit `search` verb that a config/env switch can turn
  off), `-i` as an adverb, and dropping the `-L` alias. Speculative growth
  is mostly new *sources* (advisories, analytics, receipts, Brewfiles,
  what-a-formula-ships) and new *verbs* (doctor, bundle, vulns, deps,
  serve), all gated by `brewver.FEATURES`. The API is a seedbed seedling
  with its own semver that pins a brew-hop-search range plus
  `SCHEMA_VERSION`; crossovers are declared in a table, never implied.
---

# Strategy toward 1.0

Companion to `sessions/2026-09-13-requests.md` § C (decisions parked) and
`docs/research/2026-09-13-brew-7-features.md` (what brew 7.0 exposes).
This is speculation with a spine: what we lean on, what we've opted out
of, what's in the ambiguous middle, and a sequencing proposal.

## 1. Where we stand (0.4.0-dev)

**Capabilities.** Offline-first FTS5 search over four sources (api,
installed, taps, local) with a real query grammar; cache-first reads with
background refresh and a sentinel-file trailing line; nine output formats
behind one meta envelope; outdated, history, cache status; per-source
TTLs; version gate for brew features; tap trust.

**Principles we actually use.**

| Principle | Where it shows |
|---|---|
| 12-factor layering: default < config < env < CLI | `defaults.py`, `_config.py`, `--stale`, `BREW_HOP_SEARCH_*` |
| Cache-first, refresh in the background | `cache-flow.md`, sentinel protocol |
| Cartesian specs (sources × verbs × adverbs × formats) | `cli-vocabulary.md`, INPUT/OUTPUT |
| Spec alongside code; expect-snapshot TDD | every feature commit |
| Small deps (sqlite-utils, packaging) | pyproject |
| Visible degradation, never silent | `brewver.skipped_report`, `--offline` errors |
| Least surprise | `-l` rename, `--offline`/`--refresh` conflict |

**Explicitly opted out.** Re-implementing brew verbs that mutate
(install/upgrade/uninstall); a rich TUI dependency (P4 bead, `less -S`
shim instead); telemetry; a resident daemon; parsing Ruby beyond a regex.

**Ambiguous middle** (decided in a draft, not shipped, or never decided):
subcommands (Option B, decided-next), `-i` as adverb (bhs-ox6), multi-root
and `detect` (locations.md), color (format-color.md), OSC 8 links,
interactive viewer, install-manager TUI, a brew-ops model.

## 2. What 1.0 promises

A major version is a contract, so name the contract:

1. **Surface.** Every flag and verb in `--help` keeps its name and
   meaning through 1.x. Deprecations get one minor of alias + hint, as
   `-L` did.
2. **Machine output.** The meta envelope keys (`ENVELOPE.md`), `--json`
   row fields, `-C --json`, exit codes (0 results/none, 1 runtime, 2
   usage). New keys may appear; none disappear.
3. **On-disk.** `SCHEMA_VERSION` only bumps with a migration note; the
   cache dir and DB path stay. `_meta` scalar rows are additive.
4. **Configuration.** `BREW_HOP_SEARCH_*` names and `config.toml` tables
   are stable; new ones are additive.

Rule of thumb for declaring it: **two consecutive minors with zero
renames on that surface.** 0.5 and 0.6 clean → 1.0.

### Breaking changes that must land *before* 1.0

- **Subcommand layer** (§ 3). Changes how bare positionals parse.
- **`-i` as an adverb** (bhs-ox6): `-ci` should mean "casks, restricted
  to installed, reporting *installed* versions." Today `-i` is a fifth
  source. Semantics change for `-i` users; do it in 0.5 with subcommands
  so both grammar changes ship together.
- **Drop the `-L` alias** (one minor after 0.4, per the rename commit).
- **Rename `--refresh=index` → `api`?** The source is called `api`
  everywhere except the refresh kind (`index`, short `x`). Decide once;
  the vocabulary spec (bhs-3g9) owns it.

## 3. Subcommands, with an escape hatch for the implicit verb

Option B from `cli-vocabulary.md`, refined by two constraints you named:
it shouldn't spoil the fast path (`bhs python`), and an implicit default
verb à la `llm prompt` is acceptable only if it can be switched off.

**Grammar.** `bhs [global adverbs] <verb> [verb args]`. Verbs: `search`
(default), `installed`, `taps`, `local`, `cached`, `outdated`, `history`,
`status`, `refresh`, `version`, and later `doctor`, `bundle`, `vulns`,
`deps`, `detect`, `serve`. Flags remain sticky aliases for one release
(`-i` ↔ `installed`, `-C` ↔ `status`, ...).

**Implicit verb.** If the first non-flag token is not a known verb, the
whole positional list is a `search` query. Three mitigations for the
`llm prompt` annoyance:

1. **Off switch, 12-factor.** `[cli] implicit_verb = false` in config, or
   `BREW_HOP_SEARCH_IMPLICIT_VERB=0`. When off, `bhs python` errors:
   `no verb; did you mean: bhs search python` (exit 2). Scripts that want
   strictness set the env var once.
2. **Collision escape.** A package literally named like a verb (`status`,
   `version`) is reachable as `bhs search status` or `bhs -- status`.
   Verbs win bare; the hint line at `-v` says when the implicit verb
   fired (`# [cli] implicit verb: search`).
3. **Discoverability.** Bare `bhs` lists verbs, not only the four hints
   it prints today; `--help=verbs` is a section.

**Draft verbs behind an env gate.** `BREW_HOP_SEARCH_DRAFT=1` exposes
verbs marked draft (listed in `--help` with a `(draft)` tag when the env
is set, hidden otherwise). This is the same shape as
`#[cfg(debug_assertions)]` flags in slapchop and keeps 1.0's promise
scoped to non-draft verbs. Drafts can rename freely.

**Implementation shape.** One argparse parent parser holds the global
adverbs; `add_subparsers(dest="verb", required=False)`; a pre-parse pass
inserts `search` when the first positional is not a verb and the switch
is on. Contextual `-h` already introspects the parser and will pick up
subparsers.

## 4. Speculative evolution

Ranked by how well each fits "small, fast, offline, cached." Items say
which principle they lean on and what they'd cost.

### 4.1 New sources (read-only, cacheable, fit the model exactly)

| Source | Data | Why | Gate |
|---|---|---|---|
| **advisories** | `formulae.brew.sh/api/advisories.json` (OSV, 14 MB gz) | `bhs vulns` offline; `--vulns` filter on search results; per-formula open/patched counts | 7.0.0 (data is public; the *flags* mirror `brew vulns`) |
| **analytics** | `/api/analytics/install/30d.json` etc. | Popularity as a *ranking signal* for search, and a "trending" verb. Cheap, cacheable daily | none |
| **receipts** | `brew list --installed-on-request` / `--poured-from-bottle`; `INSTALL_RECEIPT.json` | Mark dependency-only installs in `-i`; "leaves" view; bottle vs source | 7.0.0 for the flags; receipts are files |
| **Brewfile** | `brew bundle dump` output, or a user path | Diff declared vs installed; "what my dotfiles want that isn't here" | 6.0.0 (`trusted:` lines) |
| **ships** | `$(brew --prefix)/opt/<f>/{bin,share/man,etc}` walk | "which formula gives me command X"; man pages; persisted `etc/`/`var/` state across reinstall | none; cost is a filesystem walk per installed formula |
| **deps graph** | already in `raw` (`dependencies`, `build_dependencies`) | `bhs deps X` / `bhs uses X` offline from the index; no `brew deps` subprocess | none; a derived table |

### 4.2 New verbs (mostly over the sources above)

- `doctor` — run `brew doctor --json`, store each run, `doctor --diff`
  against the previous. Health, not search; belongs under the subcommand
  layer, never a flag.
- `bundle dump|diff|show` — thin over `brew bundle`, plus the Brewfile
  source. `-v` prints the brew commands as they run (your 22:17 request).
- `vulns` — over the advisories source; flags follow `brew vulns`.
- `deps` / `uses` — offline graph from `raw`.
- `detect` — roots (locations.md).
- `serve` — hand off to brew-hop-api when installed (§ 6); the CLI
  stays dependency-light.

### 4.3 A brew-ops model (keep it a dict until it earns a schema)

`brewver.FEATURES` is the seed. The natural extension is one table per
brew operation we shell out to:

```
op            argv                                   min   reads/writes  json  ttl-class
info          brew info --json=v2 --installed        -     r             v2    installed
tap-info      brew tap-info --installed --json=v1    6.0   r             v1    taps
list-receipts brew list --installed-on-request       7.0   r             -     installed
doctor        brew doctor --json                     7.0   r             yes   on-request
bundle-dump   brew bundle dump --file=-              -     r             -     on-request
```

Three consumers would read it: the version gate, the TTL table in `-C`,
and help text. Until the third exists it's over-engineering; the
gate is enough. Re-evaluate when `doctor` lands.

### 4.4 Performance and caching

The timing footer and `refresh.log` already produce the data; measure
before optimizing. Candidates, in likely payoff order:

1. **Conditional GET** on `formula.json`/`cask.json` (`If-None-Match` /
   `If-Modified-Since`) — skips a 30 MB download when nothing changed.
   Needs a check that formulae.brew.sh emits validators (UNVERIFIED).
2. **Raw-column promotion**: columns for the fields `-T`/`--multi` show,
   so display never parses `raw` for the common path.
3. **Per-source TTL tiers** exist; a "refresh cadence" view in `-C -vv`
   (last N refresh durations from `refresh.log`) would make tuning
   visible.
4. **Not a daemon.** The bg-subprocess + sentinel model is enough; a
   resident process is opted out until measurements say otherwise.

### 4.5 Distribution

- **`brew hop-search` as an external command.** Homebrew runs any
  `brew-<name>` executable on `PATH` as `brew <name>`. Shipping a
  `brew-hop-search` shim (we already install that binary name) means
  `brew hop-search python` works today with zero code. Worth a README
  line and a Formula test; it's the most brew-native "command
  suggestion" available.
- The tap Formula and PyPI stay the two channels.

### 4.6 Agent-facing surface

An MCP server or `--json` contracts good enough that agents use them is
plausible and cheap *once the API exists*: the API is the read model;
MCP is a transport. Not a CLI concern.

## 5. Sequencing proposal

| Version | Contents | Breaking? |
|---|---|---|
| **0.4.0** | this branch: Option A, `--cached`, brewver, tap trust, `SCHEMA_VERSION` | `-L` → `-l` (aliased) |
| **0.5.0** | subcommand layer + implicit-verb switch + draft gate; `-i` as adverb; drop `-L`; `index`→`api` rename if taken | yes — the last grammar break |
| **0.6.0** | sources: advisories, analytics, receipts; verbs: `vulns`, `deps`/`uses` (draft) | no |
| **0.7.0** | multi-root + `detect`; `doctor`, `bundle` (draft → stable) | no |
| **1.0.0** | after two clean minors; drafts either promoted or removed | contract begins |

Patch tags along the way: `make bump-release` strips `-dev`, then
`make tag` (rc) or `make tag-release`. Note `build-tag.sh` derives the
tag from `VERSION` verbatim, so tagging while it reads `0.4.0-dev` yields
`v0.4.0-dev-rc1`; strip first.

## 6. CLI ↔ API version coordination

The API (`ClaudeCollab/brew-hop-api`, seedling) reads the CLI's sqlite
directly and imports `brew_hop_search.search` for the query grammar.
Two coupling points, two anchors:

- **On-disk shape** → `cache.SCHEMA_VERSION`, stamped in `_meta`. The
  API declares the schema versions it understands.
- **Python surface** → the API pins a `brew-hop-search` version range
  (`>=0.4.0.dev0,<0.5`) and checks it at startup.

**Policy: independent semver, declared crossovers.** The API's version
says nothing about the CLI's; the compatibility table in the API's
README does. `/health` reports `compat` with reasons rather than
refusing to serve. When the CLI bumps `SCHEMA_VERSION`, the API gets a
minor that adds the new number to its supported set; when the CLI
crosses a major, the API bumps its range. Snapshots "match" when both
anchors agree — never by having the same version number.

| brew-hop-api | brew-hop-search | SCHEMA_VERSION |
|---|---|---|
| 0.1.x | >=0.4.0.dev0,<0.5 | 1 |

## 7. Skip list (so the fun stays bounded)

Reimplementing install/upgrade; a package manager UI; a daemon by
default; a plugin system; a web UI in this repo (it belongs in the API
seedling, and only if the API earns it); telemetry; supporting brew < 4
(the internal JSON API era).
