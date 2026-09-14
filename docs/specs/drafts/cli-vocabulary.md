# cli-vocabulary

A grammar audit of `brew-hop-search`'s CLI surface and a proposal
to resolve the noun/adverb confusion (`-L` is the symptom).
Considered: keep the current short-flag surface and rename for
clarity, vs. add subcommands for verb-first scoping.

## Status

**Draft; Option A shipped 2026-09-13** (0.4.0-dev): `-L` → `-l` with a
one-release hidden alias, `--offline` adverb (conflicts with
`--refresh`), and `--stale` honored by every source with the
`KIND:DUR[,…]` selector. Option B (subcommands) is next; see
`sessions/2026-09-13-requests.md` § C1 for the proposed staging
(draft verbs behind `BREW_HOP_SEARCH_DRAFT=1`). Bead bhs-3g9. Drives changes referenced by
[timing](timing.md), [installed-indicator](installed-indicator.md),
and the next steps for `--stale` universalization. Pulls from the
cross-project seed
`~/dev-llm/claude-collab/cli-ux/cli-grammar.md` (parts-of-speech
framing).

## Purpose

User feedback (2026-05-28): "I'm confused by `-L`, why uppercase. Is
it a noun, alongside `f, c, i, t`, semantically? Or is it an adverb
to insist that `f, c` searches only act locally?" That confusion is
real and structural: `-L` *is* doing two jobs today and the surface
doesn't signal which.

Same audit for `-f`, `-c`, `-i`, `-t`, `--refresh`, `--stale`,
`--brew-verify`, etc. The cartesian (sources × verbs × modifiers ×
formats) is the lens — every cell should have one clear name, and
every name should sit in one cell.

## The cartesian, as it is today

### Sources (nouns) — *where the data comes from*

| Flag | Underlying table(s) | Origin |
|------|---------------------|--------|
| *(default)* | `formula`, `cask` | formulae.brew.sh aggregate JSON |
| `-L` / `--local` | `local_formula`, `local_cask` | `$(brew --cache)/api/<kind>/*.json` — brew's per-package cache |
| `-i` / `--installed` | `installed_formula`, `installed_cask` | `brew info --json=v2 --installed` |
| `-t` / `--taps` | `tap` | filesystem walk of `$(brew --repo)/Library/Taps/**/*.rb` |

### Kind filters (adjectives) — *narrow which slice*

| Flag | Effect |
|------|--------|
| `-f` / `--formula(e)` | Formulae only |
| `-c` / `--cask(s)` | Casks only |
| *(both/none)* | Both kinds |

### Verbs — *what to do*

Today there are no explicit verb subcommands; verb is encoded in
flags that don't sit in a verb group:

| Flag | Verb |
|------|------|
| *(default — query positional)* | `search` |
| `-O` / `--outdated` | `outdated` |
| `-H` / `--history` | `history` |
| `-C` / `--cache-status` | `status` |
| `-V` / `--version` | `version` |
| `--refresh[=DUR\|KIND]` | `refresh` (modifier + command) |

### Modifiers (adverbs)

| Flag | Effect |
|------|--------|
| `-q` / `--quiet` | verbosity adverb |
| `-v` / `-vv` | verbosity adverb |
| `--refresh` | freshness adverb (or verb, see below) |
| `--stale DUR` | freshness adverb (currently *only honored by `formula`/`cask`*) |
| `--brew-verify` | accuracy adverb (only for `outdated`) |
| `--no-timing` | output adverb |

### Output formats

| Flag | Effect |
|------|--------|
| `-g` / `--grep`, `-q`, `--json`, `--csv`, `--tsv`, `-T`, `--sql`, `--multi` | mutually-exclusive renderers |

## The two problems the cartesian exposes

### Problem 1 — `-L` is overloaded

`-L` is a *source* (its `local_formula`/`local_cask` tables are
indexed from brew's per-package JSON files, distinct from the
formulae.brew.sh aggregate). But the code also treats `-L` as the
adverb "offline" — e.g., in the outdated path, `if not args.local:
api.ensure_cache(...)` skips the network refresh.

These two meanings are *correlated* (the local source is offline by
definition) but not identical:

- A user who wants *only* "skip the network this once" while still
  searching the formulae.brew.sh aggregate tables has no way to
  express it.
- A user who wants *only* "search the local-cache tables" but
  doesn't care whether the formulae.brew.sh tables also got a bg
  refresh queued has no way to disable the second behavior.

### Problem 2 — `--stale` is source-asymmetric

`--stale DUR` is documented as a freshness adverb, but it's only
threaded into `api.ensure_cache` (formula/cask). The installed,
taps, and local sources have their own stale thresholds
(`stale_installed_seconds`, etc.) that `--stale` doesn't touch.
The cartesian view makes this obvious: an adverb that only attaches
to one of four nouns is a vocabulary bug.

This is the underlying issue the user flagged ("support for
`--stale` and `--refresh` on all the options"). The grammar fix and
the `--stale` universalization are the same fix.

### Problem 3 — capitalization signals nothing

`-i`, `-t` are lowercase; `-L` is uppercase. `-q`, `-v` are
lowercase (modifiers); `-V`, `-O`, `-H`, `-T`, `-C` are uppercase
(verbs/info). `-f`, `-c` are kind filters, lowercase.

The pattern *almost* maps to "lowercase = source/modifier,
uppercase = verb/output," but `-L` (source) is uppercase and breaks
it. Either fully commit to a scheme or stop using case as
information.

## Options on the table

### Option A — minimal: rename `-L`, split its two roles

- Rename `-L` / `--local` → `-l` / `--local` (lowercase, matching
  `-i`, `-t`). The noun reading stays.
- Add `--offline` (no short letter) as a *separate* adverb that
  forbids network. `-L` users get a deprecation period; `--offline`
  composes with any source flag.
- Extend `--stale DUR` to honor *every* source (today: just
  formula/cask). Add `--stale=KIND:DUR[,KIND:DUR]` selector form
  matching `--refresh=KIND`'s shape.

Pros: smallest disruption. Existing muscle memory mostly survives.
Vocabulary becomes consistent. Two distinct ideas get two distinct
flags.

Cons: doesn't address the absence of explicit verbs (`search` is
still implicit). Doesn't help with `-O`/`-H`/`-C` reading as
"info" but actually being verbs.

### Option B — add subcommands without removing flags

Introduce verb subcommands; keep the flag surface as a sticky alias
that maps to them. Both spellings remain.

```
bhs search python                  ↔ bhs python
bhs installed [query]              ↔ bhs -i [query]
bhs taps [query]                   ↔ bhs -t [query]
bhs local [query]                  ↔ bhs -L [query]  (after rename, -l)
bhs outdated                       ↔ bhs -O
bhs history <name>                 ↔ bhs -H <name>
bhs status                         ↔ bhs -C
bhs refresh [KIND...]              ↔ bhs --refresh[=KIND]
bhs version [-V]                   ↔ bhs -V
```

Adverbs work everywhere:

```
bhs installed --offline python
bhs search --stale 1h python
bhs refresh installed --max-age 6h
```

Pros: makes verbs explicit. Better `--help` organization (per-verb
help screens). Matches `gh`, `git`, `kubectl` conventions. Scales
when the next verb arrives (e.g. `bhs install` if we ever cross into
install-manager territory — see
[output-readability](output-readability.md)).

Cons: bigger surface area (twice the help to write). Some users will
mix the two and `bhs -i installed python` won't be obvious behavior.

### Option C — full subcommand migration, deprecate short-only flags

Same as B but the short flags become deprecated. Old `bhs -i` works
for one minor version with a `→ try \`bhs installed\`` hint, then
removed.

Pros: one canonical surface. No mixed-mode confusion.

Cons: muscle memory cost. We *are* the small-and-fast tool;
`brew-hop-search installed python` is more keystrokes than `brew
hop-search -i python`. May undermine the pitch.

### Option D — keep flags only, fix vocabulary

No subcommands. Apply Option A's renames. Improve `--help`
organization (sources / verbs / modifiers / output groups —
already mostly done; tighten labels). Lean on the existing
verbosity ladder to surface deeper docs (`-h verbs`, `-h sources`,
etc.).

Pros: keeps the keystroke advantage. Easier change.

Cons: doesn't fundamentally fix the "every command is implicit
search" awkwardness if/when we add new verbs.

## Recommendation

**Option A + Option B together, staged.** A immediately, B over
the next few sessions. C is a longer-horizon decision pending
adoption signal.

Concretely:

1. **Now (Option A):**
   - Lowercase `-L` → `-l`; document the change; keep `-L` as a
     hidden alias for one release.
   - Add `--offline` adverb (no short). Wire it through all source
     paths to skip network refresh; defaults to off.
   - Universalize `--stale` to take all source kinds. Selector form
     `--stale=KIND:DUR[,KIND:DUR]` matches `--refresh=KIND`. Bare
     `--stale DUR` applies the duration to whichever sources this
     invocation touches.
2. **Next (Option B):**
   - Add subcommand layer. `bhs search`, `bhs installed`, `bhs
     taps`, `bhs local`, `bhs outdated`, `bhs history`, `bhs
     status`, `bhs refresh`, `bhs version`.
   - Each subcommand inherits the global adverb set (`--quiet`,
     `--verbose`, `--offline`, `--stale`, `--refresh`, format flags,
     etc.) via a shared parent parser.
   - Old flags continue to work, dispatching to the corresponding
     subcommand.
3. **Later (Option C decision):**
   - After 1-2 minor versions of B, decide whether to deprecate the
     flag-only surface. Driver: actual user telemetry / `gh issue`
     traffic, not preemptive.

## Capitalization rule (proposed)

Once Option A lands, codify:

| Case | Role |
|------|------|
| lowercase | sources (`-f`, `-c`, `-i`, `-t`, `-l`), adverbs (`-q`, `-v`, `-g`), format renderers (`-g`) |
| UPPERCASE | verbs/info-only (`-O`, `-H`, `-C`, `-V`, `-T`), and dangerous/special-purpose adverbs (rare) |

`-T` for `--table` is fine under this rule — it's a renderer-as-verb
("render the results as a table") and distinguishes from the
lowercase `-t` (taps source).

## `--offline` semantics

```
bhs --offline python              # search api tables, no bg refresh
bhs -i --offline python           # search installed, don't bg-refresh installed
bhs -t --offline python           # search taps, don't rescan
bhs -l --offline python           # redundant (the local source IS offline) but allowed
bhs --offline --refresh python    # CONFLICT — refuse with clear error
```

`--offline` and `--refresh` are mutually exclusive — one says "no
network", the other says "go to network." Error message:
`--offline and --refresh conflict. Drop one.`

## Migration table (Option A only)

| Today | After Option A |
|-------|----------------|
| `bhs -L python` | `bhs -l python` (canonical) or `bhs -L python` (alias for 1 release) |
| *(no expression of "skip network this invocation, search api tables")* | `bhs --offline python` |
| `bhs --stale 1h python` | unchanged — applies to api (formula/cask) |
| *(no per-source stale)* | `bhs --stale=installed:5m -i python` |
| `bhs --stale=all:1h --refresh ...` | rejected, conflict |

## Examples after the full Option B layering

```
bhs python                        # implicit `search`, default sources
bhs search python                 # explicit
bhs installed                     # list all installed
bhs installed python              # search installed for python
bhs installed --json python       # same, json
bhs taps python
bhs local python
bhs outdated
bhs outdated --brew-verify
bhs history python
bhs status                        # cache-status
bhs status --json
bhs refresh installed             # explicit refresh subcommand
bhs refresh all
bhs refresh installed --stale 5m  # refresh only if older than 5m
bhs version
bhs version -vv                   # detailed version info
```

## Cross-references

- [timing](timing.md): the label vocabulary used there (`installed:f`
  etc.) should follow whatever spelling this spec picks. Once
  Option A lands, the `cache:` prefix stays dropped, but the source
  side becomes consistent (`local:f` not `L:f` or `local_formula`).
- [installed-indicator](installed-indicator.md): uses the same source
  names in its per-format tables.
- [format-color](format-color.md): no direct overlap, but the
  `--color` flag follows the same "lowercase adverb" convention
  proposed here.
- [locations](locations.md): adds two cells this cartesian doesn't
  cover — the **root** noun (multi-root / zerobrew) and the
  **all-cached** aggregate selector over sources — plus a `detect`
  verb. Its `--root` adverb and `cached`/`detect` verbs are meant to
  slot into Option B's subparser plan; impl decides overlap.
- claude-collab seed: `~/dev-llm/claude-collab/cli-ux/cli-grammar.md`
  — this spec is the first concrete application of the
  parts-of-speech framing.

## Open questions

- **Implicit `search` verb (Option B).** Resolved in principle in
  `docs/research/2026-09-14-strategy-toward-1-0.md` § 3: keep the fast
  path (`bhs python` = `bhs search python`), but make it switchable —
  `[cli] implicit_verb = false` / `BREW_HOP_SEARCH_IMPLICIT_VERB=0`
  turns it into a usage error with a hint; verbs win bare and
  `bhs -- <name>` / `bhs search <name>` reach a package that collides
  with a verb; `-v` prints when the implicit verb fired. Draft verbs
  hide behind `BREW_HOP_SEARCH_DRAFT=1`.
- **`-l` collision with shell tools?** Some tools use `-l` for
  "long". We don't have a long-format conflict yet (`--multi`
  / `--long` is the long format). Probably fine; flag for review at
  implementation.
- **Subcommand discovery** — `bhs --help` would list subcommands;
  do we also show the legacy flags inline or hide them under
  `bhs --help=flags`? Probably hide-by-default to push the
  subcommand surface forward, but bare `bhs` (no args) hint line
  should mention both for one release.
- **Two-step migration cost** — landing A and B as separate
  releases means two visible changes. Could be one PR with both;
  decide based on size when implementation starts.
- **`bhs refresh` vs `bhs --refresh` already-implemented standalone
  command** — the existing `--refresh=KIND` *without query* already
  acts as a refresh command. Option B's `bhs refresh KIND` is the
  same thing with a more honest name. Migration: alias them; the
  flag form prints a one-time hint `(try \`bhs refresh\` instead)`.

## Spec status

**Drafted:** cartesian audit, problem statement, four options with
pro/con, recommendation (A now, B next), capitalization rule,
`--offline` semantics, migration table.

**Open until implementation:**
- Does `bhs -i installed python` (mixing flag form + subcommand
  form for the same source) parse as a search for the literal
  "installed python" in installed, or error? Recommend error with
  a hint.
- Naming for the verb-subcommand parent class in argparse —
  `add_subparsers(dest="command", required=False)` and then a
  fallback to `search` when no subcommand given.
- Whether `bhs` (no args, no flags) prints the existing hint screen
  or a `bhs --help` short. Current behavior is the former; Option B
  may want the latter for discoverability.
