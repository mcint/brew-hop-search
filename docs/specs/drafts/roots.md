---
title: roots — more than one Homebrew installation, and detect
date: 2026-11-19
kind: spec-draft
tldr: >
  A root is one Homebrew installation (the default brew, a zerobrew, any
  HOMEBREW_PREFIX). Searches select sources × roots; `--root NAME|PATH`
  picks one, `detect` finds roots and names them in config. Split out of
  locations.md; parked. Stance: support a root completely or not at all.
---

# roots — more than one Homebrew installation, and `detect`

## Status

**Draft**, split out of [locations](locations.md) on 2026-11-19.
Not scheduled: parked until the owner picks it up.

## Stance (owner, 2026-11-19)

The motivating second root is real: the owner ran zerobrew for a while
and likes its premise (a Rust core, very fast installs), but was put off
by how it was built: incomplete support, no way to upgrade, care taken
only after it was needed. This project should be a complement and an
opposite: support a root completely or not claim it, and treat the
"edge cases" a large pool of users will hit as the design, not as
follow-ups. What we learn here may be worth offering back.

## Purpose

1. **Alternate Homebrew roots (zerobrew, custom prefix).** Every
   brew path today resolves through a bare `brew` on `PATH`
   (`history.py` `brew --repository`, `defaults.py`
   `$(brew --cache)` / `$(brew --repo)`). A second install — a
   [zerobrew](https://github.com/zerobrew), a portable prefix, a
   CI sandbox — is invisible. Users shouldn't have to pass raw
   paths repeatedly.

2. **A reusable detect+name step.** A `detect` verb that finds the
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

## Examples

```
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

- [locations](locations.md): the all-cached aggregate, which a
  multi-root search widens to more columns.
- [cli-vocabulary](cli-vocabulary.md) (bhs-3g9): `--root` and `detect`
  should slot into the Option B subcommand plan.
- bhs-38h: scrub brew subprocess env (bad-citizen roots).
