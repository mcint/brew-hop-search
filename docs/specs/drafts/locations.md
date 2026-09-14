# locations — sources × roots, the all-cached aggregate, and `detect`

A location model for `brew-hop-search`: data lives in a **source**
(api / installed / taps / local) *within* a **root** (a Homebrew
installation — the default `brew`, a `zerobrew`, or any alternate
`HOMEBREW_PREFIX`). Today the tool assumes exactly one root (the
bare `brew` on `PATH`) and treats the four sources as separate
nouns. This spec adds the **root** axis, an **all-cached aggregate**
selector over sources, and a **`detect`** verb that discovers roots
and records them — by convenient name — in config.

## Status

**Draft** — extends [cli-vocabulary](cli-vocabulary.md) (bhs-3g9),
which establishes the source/verb/adverb cartesian and the staged
subcommand migration (Option A → B). This spec adds two cells that
draft doesn't cover: the **root** noun and the **all-cached**
aggregate. Implementation may discover heavy overlap with the
subcommand layer there — *let impl time decide* whether `detect`
and the root-selection adverb land as part of the Option B
subparser work or separately.

**Shipped 2026-09-13:** the `--cached` adverb form of the aggregate
(§ Aggregate) — expands to installed + taps + local, composes with
`-f`/`-c`, `--offline`, `--stale`. The `cached` subcommand spelling
waits on Option B. The "two aggregate copies" question below was
resolved the simple way for now: `--cached` includes `local_*` (brew's
own on-disk cache) and never our network-fed `formula`/`cask` tables,
so the promise "never the network index" is literal.

Roots/`detect` (§ Roots, § detect) are foundational but follow.

## Purpose

Three user-driven needs:

1. **"Search everything I already have locally."** Installed
   formulae+casks, tapped formulae, and the on-disk brew api cache —
   in one query, offline, no network. Today this is *expressible*
   (`bhs -itl python`, since sources are additive and any source
   flag suppresses the network default) but **unnamed** — there's no
   single intent-signal for "all my cached stuff."

2. **Alternate Homebrew roots (zerobrew, custom prefix).** Every
   brew path today resolves through a bare `brew` on `PATH`
   (`history.py` `brew --repository`, `defaults.py`
   `$(brew --cache)` / `$(brew --repo)`). A second install — a
   [zerobrew](https://github.com/zerobrew), a portable prefix, a
   CI sandbox — is invisible. Users shouldn't have to pass raw
   paths repeatedly.

3. **A reusable detect+name step.** A `detect` verb that finds the
   roots on a machine and writes them to config under friendly,
   updatable names (`default`, `zero`, `ci`) — so later invocations
   say `--root zero`, not `--root /opt/zerobrew`. This may be useful
   beyond search: formula/cask authors and brew-core devs who juggle
   multiple prefixes could reuse the same detection + named-root
   config.

## Model: the source × root grid

| | **default** root | **zero** root | … |
|--|--|--|--|
| **api** (formulae.brew.sh aggregate) | ✓ | ✓ | |
| **installed** (`brew info --installed`) | ✓ | ✓ | |
| **taps** (`Library/Taps/**`) | ✓ | ✓ | |
| **local** (`$(brew --cache)/api`) | ✓ | ✓ | |

- **Source** answers *what kind of store* (existing noun, unchanged).
- **Root** answers *which Homebrew installation* (new noun,
  orthogonal). Default behavior = single root, the current one, so
  nothing changes for existing users.
- A query selects a **rectangle** of this grid: some sources × some
  roots. Today the rectangle is always one column (the implicit
  root). All-cached selects all *offline* sources; multi-root widens
  to more columns.

## Aggregate — the all-cached selector (live thread)

### What exists today

Sources are additive (`cli.py`: "Sources are additive: `-i -t`
searches installed + taps"), and any source flag suppresses the
default api/network path. So:

```
bhs -itl python        # installed + taps + local, offline, f+c
```

already *is* the all-cached search. Missing: a name that is an
explicit intent-signal (per the
[flag-intent principle](cli-vocabulary.md) — a long flag should be
unambiguous, never "funny").

### Proposed surface

A single explicit selector for "all offline sources in the active
root(s)":

```
bhs --cached python            # adverb form
bhs cached python              # subcommand form (Option B layer)
```

`--cached` expands to *all sources that can answer without network*:
`installed`, `taps`, `local`. It composes with `-f`/`-c` kind
filters and all adverbs/formats. It is **explicit and
deterministic** — it does not silently include the network `api`
source, and it does not depend on the user remembering to stack
`-itl`.

### Overlap to resolve at impl time

There are *two* cached copies of the brew.sh aggregate: our own
`formula`/`cask` sqlite tables (populated by the network fetch) and
`local_formula`/`local_cask` (brew's on-disk `api/` cache, the `-l`
source). For `--cached` we want whichever aggregate is present
without touching the network. Open question (§ below) — pick one as
canonical, or union with dedup.

## Roots — multi-root / zerobrew

### Resolution today

All brew interaction is via a bare `brew` subprocess. To support
roots, introduce a single chokepoint that yields, per root:

- the `brew` binary (or `HOMEBREW_PREFIX`) to invoke,
- the derived `--cache` / `--repository` paths,
- a stable cache namespace so one root's index doesn't clobber
  another's (table prefix or separate sqlite file per root),
- **a sanitized environment** for the subprocess (see below).

### Bad-citizen roots and env hygiene

Some installs are poor environment citizens — **zerobrew** is the
worked example. It exports a `SSL_CERT_FILE` that points at a path
which may not exist (`/opt/zerobrew/opt/ca-certificates/.../cacert.pem`),
making every `brew` subprocess warn to stderr; that noise bled into
the README generator (`scripts/build-readme.sh`, fixed by dropping a
dangling `SSL_CERT_FILE` before capture). But the pollution isn't
only `SSL_CERT_FILE`: a bad-citizen root also perturbs **`brew
update`** and **tap resolution** — so an ambient zerobrew in the
shell can quietly steer which `brew`, which taps, and which update
channel bhs's `installed`/`taps`/`outdated` subprocesses see.

This is *why* `--root` must select a root **explicitly and with a
clean env**, not inherit whatever the ambient shell was polluted
with. The per-root chokepoint should:

- invoke the root's own `brew` binary by absolute path (never rely
  on `PATH` ordering, which a bad citizen can hijack),
- run with a minimized / normalized env — at least scrub a dangling
  `SSL_CERT_FILE`/`SSL_CERT_DIR`, and set `HOMEBREW_PREFIX` /
  `HOMEBREW_REPOSITORY` to the chosen root rather than letting an
  inherited value win,
- treat the *default* (ambient) root the same way once multi-root
  lands, so results are reproducible regardless of which shell ran
  bhs.

The narrower, ship-now slice of this — sanitize the env on every
brew subprocess even before multi-root exists — is worth doing
independently (it's the cause-fix behind the README contamination).

### Selection surface

```
bhs --root zero python              # named root from config
bhs --root /opt/zerobrew python     # ad-hoc path, no config needed
bhs --root default,zero python      # union across roots (ties into --cached)
bhs --all-roots --cached python     # every configured root, offline
```

`--root` is an **explicit adverb** — roots are never auto-searched
without being named (per flag-intent: no surprise scope). Config
provides the *names*; nothing is searched implicitly beyond the
default root.

## `detect` — discover and name roots

A verb that finds Homebrew installations on the machine and writes
them to config under friendly, updatable names.

```
bhs detect                     # scan, print what was found (dry, no write)
bhs detect --write             # persist discovered roots to config
bhs detect --name zero /opt/zerobrew   # name a specific prefix
```

Detection heuristics (candidate, refine at impl):
`$HOMEBREW_PREFIX`, `brew --prefix` on `PATH`, common prefixes
(`/opt/homebrew`, `/usr/local`, `~/.linuxbrew`, zerobrew's prefix),
and any `bin/brew` reachable on `PATH`.

### Config shape (toml)

Roots live in the existing config file (see [INPUT](../INPUT.md) /
`_config.py`), named and updatable:

```toml
[roots.default]
prefix = "/opt/homebrew"

[roots.zero]
prefix = "/opt/zerobrew"
brew = "/opt/zerobrew/bin/brew"   # optional explicit binary

[roots.ci]
prefix = "~/.cache/ci-brew"
```

`default` is the fallback when `--root` is omitted; updatable means
re-running `detect --write` reconciles rather than clobbers
(preserve user-chosen names, refresh paths). This detect+named-root
config is the piece that may have value to **formula/cask authors
and brew-core devs** independent of search — worth keeping the
detection + config writer factored so it could be lifted out (Unix
composability).

## Adjacent: fzf-filter view (cross-reference, not specced here)

An interactive mode that dumps all formula/cask/tap content
line-by-line into a buffer for `fzf`-style filtering — with type
selection (formula vs cask vs tap), interactive narrowing, and
potentially batch install / uninstall / `brew bundle` generation —
is a natural consumer of the all-cached aggregate. It overlaps
strongly with **bhs-ydv** (install-manager / multi-select TUI,
aptitude-shaped) and **bhs-9dh** (`bhs -I` → pager shim). Tracked
there; this spec only notes that `--cached` / the grid is its data
source. Care needed so fzf filters can still pick type and the
aggregate carries a source/kind tag per line.

## Examples

```
# all-cached (live thread)
bhs --cached python              # everything offline, default root
bhs --cached -c editor           # casks only, offline
bhs cached editor                # subcommand spelling (Option B)

# roots
bhs --root zero wget             # search the zerobrew install
bhs --root /opt/zerobrew wget    # ad-hoc prefix, no config
bhs --all-roots --cached git     # every configured root, offline

# detect / config
bhs detect                       # show discovered roots (dry)
bhs detect --write               # persist to config
bhs detect --name zero /opt/zerobrew
```

## Open questions

- **Aggregate canonicalization** — for `--cached`, prefer our
  `formula`/`cask` tables, prefer brew's `local_*`, or union+dedup?
  (The "let impl decide overlap" point.)
- **`--cached` vs default with no network** — is `--cached` just
  `--offline` (from cli-vocabulary Option A) plus all-sources? Or
  distinct? Reconcile the two adverbs so they don't both half-mean
  "offline."
- **Per-root cache isolation** — table-prefix (`zero__installed_*`)
  vs separate sqlite file per root. File-per-root is simpler to
  reason about and to nuke; prefix keeps one db. Decide at impl.
- **`detect` scope** — does it also detect *taps* and *installed
  counts* per root for a summary, or only locate prefixes? Start
  minimal (locate + name); richer summary later.
- **Naming collisions** — `--root default,zero` union ordering and
  dedup of identically-named formulae across roots in output.
- **Lift-out** — is the detect+named-root config worth shipping as a
  tiny standalone (`brew-roots`?) for non-search reuse, or kept
  internal until a second consumer appears? (>5% reuse test.)

## Cross-references

- [cli-vocabulary](cli-vocabulary.md) (bhs-3g9) — the subcommand
  migration and flag-intent principle this builds on; the `--root`
  adverb and `cached`/`detect` verbs should slot into its Option B
  parent-parser/subparser plan. Impl decides overlap.
- bhs-ydv — install-manager / multi-select TUI (the fzf-filter view's
  home).
- bhs-9dh — `bhs -I` interactive pager shim.
- bhs-qms — `--offline` adverb; must reconcile with `--cached`.
- bhs-6yt — universalize `--stale` across sources; the root axis
  multiplies the same surface.
- [INPUT](../INPUT.md) — config precedence the `[roots.*]` table
  joins.

## Spec status

**Drafted:** location model (source × root grid), all-cached
aggregate surface + overlap note, root resolution + selection,
`detect` verb + toml config shape, fzf cross-reference, examples,
open questions.

**Open until implementation:** aggregate canonicalization,
`--cached`/`--offline` reconciliation, per-root cache isolation,
`detect` depth, lift-out decision.
