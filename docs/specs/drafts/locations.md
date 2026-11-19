# locations — the all-cached aggregate

Data lives in a **source** (api / installed / taps / local). Today the
four sources are separate nouns. This spec names the **all-cached
aggregate**: one selector for "everything I already have locally".
The second axis, *which Homebrew installation* (a **root**), is
[roots](roots.md).

## Status

**Draft.** Split 2026-11-19 (owner, on #39): this file keeps the
**all-cached aggregate**; roots and `detect` moved to
[roots](roots.md), their own draft. `--offline` and `--cached`
(= `-itl`) are built on the 0.4 lane; this spec is revised against
them before it merges.

## Purpose

**"Search everything I already have locally."** Installed
   formulae+casks, tapped formulae, and the on-disk brew api cache —
   in one query, offline, no network. Today this is *expressible*
   (`bhs -itl python`, since sources are additive and any source
   flag suppresses the network default) but **unnamed** — there's no
   single intent-signal for "all my cached stuff."

(Roots and `detect`: see [roots](roots.md).)

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
```

## Open questions

- **Aggregate canonicalization** — for `--cached`, prefer our
  `formula`/`cask` tables, prefer brew's `local_*`, or union+dedup?
  (The "let impl decide overlap" point.)
- **`--cached` vs default with no network** — is `--cached` just
  `--offline` (from cli-vocabulary Option A) plus all-sources? Or
  distinct? Reconcile the two adverbs so they don't both half-mean
  "offline."

## Cross-references

- [cli-vocabulary](cli-vocabulary.md) (bhs-3g9) — the subcommand
  migration and flag-intent principle this builds on; a `cached` verb
  should slot into its Option B parent-parser/subparser plan.
- [roots](roots.md) — a multi-root search widens the aggregate to more
  columns.
- bhs-ydv — install-manager / multi-select TUI (the fzf-filter view's
  home).
- bhs-9dh — `bhs -I` interactive pager shim.
- bhs-qms — `--offline` adverb; must reconcile with `--cached`.
- bhs-6yt — universalize `--stale` across sources.

## Spec status

**Drafted:** all-cached aggregate surface + overlap note, fzf
cross-reference, examples, open questions.

**Open:** aggregate canonicalization (dedup or per-source), and
revising against `--offline` / `--cached` as built on the 0.4 lane.
