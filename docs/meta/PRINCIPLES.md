---
title: Principles
date: 2026-11-12
kind: reference
tldr: >
  Six tables: design values, CLI vocabulary, output, releases and
  versioning, process, and collaboration with agents. Each row has a
  source and a status column. W means it was written down in the repo
  before this file; C means it lived only in chat, memory or the intent
  worktree; P means it was implied by practice only. The releases and
  collaboration tables are almost all C, which is why this file exists.
---

# Principles

The design values are documented at length in DESIGN-SYSTEM.md,
LEAST-SURPRISE.md, TASTE.md, COMPARABLES.md and INSPIRATIONS.md. This file
lists them in one line each and points there. The release, process and
collaboration rows were, until 2026-11-12, not reachable from the repo
tree; the status column shows which.

Status legend: W = written in-repo before this file (source cited).
C = written only in ClaudeCollab, memory, the intent worktree or session
notes. P = implied by practice only. "(branch)" means on the unmerged 0.4
lane; "(draft)" means in `docs/specs/drafts/`.

## Design values

| # | Principle | Rationale | Source | Status |
|---|---|---|---|---|
| D1 | Offline-first: the default search never calls `brew`; HTTP or local DB only. | `brew search` is slow because it shells out; the point of the tool is not to. | DESIGN-SYSTEM § Design Principles; TASTE; COMPARABLES § brew | W |
| D2 | The cache is a database: SQLite + FTS5, inspectable with `-C`, exposed by `--sql`. | Data you can query is data you can trust and debug. | DESIGN-SYSTEM; INSPIRATIONS § datasette | W |
| D3 | Read-only tool: no upstream writes, no `brew install`, no telemetry, no credentials. | A search tool with no write path has no blast radius. | DESIGN-SYSTEM; STABILITY § Security | W |
| D4 | Composition over features: `-q` for fzf, `-g` for awk, `--csv` for qsv, `--json` for jq. | Output is data; the shell does the rest. | DESIGN-SYSTEM; TASTE | W |
| D5 | Progressive disclosure: default is clean; details unlock with `-v`. | Noise is opt-in; the common case stays readable. | DESIGN-SYSTEM; specs/OUTPUT.md | W |
| D6 | Least surprise: self-healing cache, zero config, dates imply their own limits, stable contracts. | The user should never need to think about internals. | LEAST-SURPRISE (whole file) | W |
| D7 | Cache-first, refresh behind, return to the shell promptly; the timing line shows the cache earning its keep. | Latency is the feature; prove it on every run. | specs/features/cache-flow.md; drafts/timing.md | W |
| D8 | Visible degradation, never silent: a skipped brew feature is reported at `-v`, not no-op'd. | A silent no-op is a bug the user cannot see. | brewver.py; strategy-toward-1.0 § 1 | W (branch) |
| D9 | Small dependencies: argparse over click, raw ANSI over rich, sqlite-utils + packaging only. | A uv script should stay installable in seconds. | COMPARABLES § Intentionally Distant; pyproject.toml | W |
| D10 | Twelve-factor layering: default < config.toml < env < flag. | Env is for tests and CI, not daily use. | LEAST-SURPRISE § Zero-Config; drafts/config-layers.md | W |
| D11 | Mirror brew's mental model (`-f`/`-c`/`-i`), then go offline. | Users bring brew's vocabulary; do not make them learn a second one. | INSPIRATIONS § Input Design | W |
| D12 | Shake dead leaves off the tree: walk back requirements that create dead code paths. | "180 lines came out; 36 went in" (2026-04-22). | memory; sessions/2026-04-22 | C |
| D13 | Document taste by reference: what to adopt, keep distance from, where independently aligned. | A comparison doc is not a feature list; it is a position. | COMPARABLES; INSPIRATIONS header | W |

## CLI vocabulary

| # | Principle | Rationale | Source | Status |
|---|---|---|---|---|
| V1 | Sources are composable and additive; filters are restrictive. | Two sources means more results; a filter means fewer. | DESIGN-SYSTEM § Consistency Rules; specs/INPUT.md | W |
| V2 | Lowercase = sources and adverbs (`-f -c -i -t -l`, `-q -v -g`); UPPERCASE = verbs and info (`-O -H -C -V -T`). | One rule tells the hand where a flag lives. | drafts/cli-vocabulary.md; `ce34649` | W (draft) |
| V3 | Every cell of the cartesian (sources x verbs x adverbs x formats) has one name, and every name sits in one cell. | No flag means two things; no thing has two flags. | cli-vocabulary.md § Purpose | W (draft) |
| V4 | Renames keep the old spelling one release as a hidden alias with a stderr hint. | Scripts get one cycle to follow. | `ce34649`; strategy § 2.1 | W (branch) |
| V5 | Verbosity is uniform: `-v` = provenance, `-vv` = what the tool did, `-vvv` = raw material, on every verb. | Learn the ladder once. | DESIGN-SYSTEM rule 1; VERBOSITY.md | W |
| V6 | Each `-v` level adds to stderr, never stdout; machine formats ignore the ladder. | Pipes stay clean at any verbosity. | VERBOSITY.md rule 2; LEAST-SURPRISE § Piped output | W |
| V7 | The invitation is explicit: when the tool knows more than it said, it says so in five words or fewer, once. | `(-v for sources)` beats a manual. | VERBOSITY.md rule 3 | W (branch) |
| V8 | Every spelling a hand reaches for should resolve: `brew-hop-search`, `brewhs`, `brew-hs` / `brew hs`, `brew hop <verb>`. | Discoverability is spelled, not documented. | drafts/short-names.md; `6bd145e` | W + C |
| V9 | The user's spelling in the request outranks the spec's. | The request is data about the user's hand. | intent INTENT § Parked | C |
| V10 | `-i` is becoming an adverb (installed-restricted), not a fifth source. | Installed is a filter on sources, not a source. | bead bhs-ox6; strategy § 2.1 | C / W (branch) |
| V11 | Duration syntax (`30m`, `6h`, `1d`) and the `KIND[,KIND]` selector are shared across flags. | One grammar for time and for kinds. | DESIGN-SYSTEM rule 4; cache-flow.md | W |

## Output

| # | Principle | Rationale | Source | Status |
|---|---|---|---|---|
| O1 | Default is human-optimal: results to stdout, status to stderr, no spinners in stdout. | Stdout is for the next program. | TASTE § Coherent Desire | W |
| O2 | Output-as-document: `# ` section headers with counts and the install hint, `-- ` comments, diffable structure. | Readable raw and readable in a diff. | sessions/2026-04-07; specs/OUTPUT.md | W |
| O3 | Format stability is a contract: snapshot tests lock the default; `--json` schema is versioned; fields are added, never removed; CSV column order fixed. | Scripts written against 0.3 keep working. | LEAST-SURPRISE § Format stability; STABILITY; AUDIENCES | W |
| O4 | Plain when piped, decorated on a TTY; `-q` is pipe-safe; respect `NO_COLOR` / `FORCE_COLOR`. | Colour is for eyes, not for awk. | LEAST-SURPRISE § Piped output; drafts/format-color.md | W |
| O5 | Exit codes: 0 success including zero results; 1 runtime error; 2 usage. | "No results" is an answer, not a failure. | LEAST-SURPRISE § Exit codes | W |
| O6 | All `--json` output wraps in a self-describing `meta` envelope; absent fields are omitted, not null. | A consumer can tell what it got without a schema lookup. | specs/ENVELOPE.md | W |
| O7 | Do not call our own result "fast" or "local" in labels; say "bhs". | Name the source, not the claim. | `89d4f5f`; memory 2026-04-09 | C |
| O8 | A diff mode shows both sides with markers; it does not swap sources. | The comparison is the value. | memory 2026-04-09 (`--brew-verify`) | C |
| O9 | Cutting content off is non-unix; prefer wrapping, pagers, or telling the user `-n0` exists. | Truncation hides data; a hint does not. | sessions/2026-05-31; drafts/output-readability.md | C / W (draft) |

## Releases and versioning

The April and November incidents in HISTORY.md are the why for R1 to R5
and R8 to R11, R15 and R16. RELEASING.md is the procedure.

| # | Principle | Rationale | Source | Status |
|---|---|---|---|---|
| R1 | Declaring an official version (tag `vX.Y.Z`, GitHub release, PyPI publish, moving `main`) is the owner's act, after they review the tests. Agents prepare and stop. | 2026-11-08: two releases cut on a mood, both reversed. | memory 2026-11-08; INTENT § Reversed | C only |
| R2 | No outward push without an explicit ask; "a release or a few" is a mood, not an authorization. One closed question with a stated default, then wait. | The protocol existed since 2026-04-27 in a gitignored note. | sessions/2026-04-27; memory 2026-11-08 | C only |
| R3 | `main` holds only tagged releases, fast-forwarded from `dev` at release time, never ahead of what is published. | A visitor on `main` sees something installable. | release-flow.md § Invariants; release.sh step 6; owner 2026-11-12 | W (mechanics) / C (meaning) |
| R4 | `dev` is the integration lane; commit and push freely; always green. | One place where the block forms. | release-flow.md; BRANCH-MODEL.md | C |
| R5 | Tag once, build from the tagged HEAD, publish idempotently, then move `main`, then bump to `-dev`. | 2026-04-19: four tags on one commit. | `bc90a92`; DEVELOPMENT.md | W |
| R6 | HEAD of `dev` never shares its version with a published release; `-dev` is the marker. | A wheel built from `dev` can never impersonate a release. | DEVELOPMENT.md § Version invariant; `55b0b4e` | W |
| R7 | Every wheel knows its commit (`_build_info.py`); guards verify identity, not approximations. | Tag and artifact never fracture. | `338f888`; hatch_build.py | W |
| R8 | A tag ships a green suite or it is not a tag; `--no-verify` is a debt due at the next release. | Tests gate deploys. | intent principles.md; release.sh step 1 | C |
| R9 | Release from a worktree branch, never the owner's checkout; a release is a ref update (`git fetch . x:main`), not a checkout. | The owner's tree is theirs. | git-coord ff-without-checkout.md | C |
| R10 | Linear history on `main`; fast-forward or rebase, never merge commits. | `git log main` reads as a release list. | git-coord linear-history.md | C |
| R11 | Pre-release (`-rcN`) and visibly agent-marked (`tag-draft/`) tags may be pushed; official tags may not. | The marker in the name is what makes it safe. | memory 2026-11-08; BRANCH-MODEL.md | C |
| R12 | README is a release artifact: regenerated from live output at the tag step under a clean env. | The README shows what the tag does, not what dev did. | `ccdd8c4`; scripts/build-readme.sh | W |
| R13 | The tag message carries the commit list; CHANGELOG.md is the curated narrative. | Two audiences, two documents, one source. | CHANGELOG header; `bcfd471` | W + C |
| R14 | PEP 440; minor for widened or renamed surface, patch for fixes, major only after two minors with zero renames. | A rename is a minor, even with aliases. | `ad892fc`; strategy § 2 | W (branch) |
| R15 | Credentials and publisher config are the owner's keys; report the failing job with its exact claims, do not route around it. | Ten failed publish runs are a fact to report, not a wall to climb. | intent principles.md; bead bhs-59v | C |
| R16 | Ship a block, not a trickle: one release per cycle with one changelog narrative. | "It's a block of features." | INTENT § Reversed | C |
| R17 | Pin the dev shell (`.python-version`); measure the floor (CI matrix); the pin never narrows `requires-python`. | A pin is a convenience, a matrix is evidence. | `056a73c`; INTENT § Decided | C + W (file) |

## Process: specs, tests, commits, issues

| # | Principle | Rationale | Source | Status |
|---|---|---|---|---|
| P1 | Spec first, or alongside in the same commit, never last. Implementation-ready drafts live in `docs/specs/drafts/`; "should we build this?" is a bead. | Intent versioned with implementation. | TASTE ask 12; DESIGN-SYSTEM § Spec Lifecycle; memory | W |
| P2 | Cartesian specs: Feature x Input x Output x Envelope; a new feature needs only a Feature Doc. | Guides written once apply everywhere. | DESIGN-SYSTEM | W |
| P3 | New feature = new test, red-green; a snapshot test's first run with no snapshot is red; the snapshot is the pre-registered intent. | The test says what was meant before the code says what was done. | global CLAUDE.md § Testing (origin here, 2026-04-19) | C (global) / W (practice) |
| P4 | Tests never spawn brew; `BREW_HOP_SEARCH_DB` isolates; `pytest -vv` shows the expected output. | The suite runs anywhere, and documents itself. | sessions/2026-04-07; AUDIENCES § Developers | W |
| P5 | Commit early, often, scoped by concern; the body says why; Conventional Commits with scope. | Easier to squash than to separate. | memory 2026-04-09; log from `ce34649` | C + P |
| P6 | Never amend without asking; new commits; proportionate messages. | Shared history is shared. | memory | C |
| P7 | Pre-commit runs the suite; `--no-verify` only for re-scoping a tree that was just tested. | Every commit is green or says why not. | release/hooks/pre-commit; memory | W + C |
| P8 | `br` (beads) is the tracker; `.beads/` is tracked by the owner's choice; `br sync --flush-only` then a manual commit; `bd` is retired. | Issues close to the code. | AGENTS.md; `4888712` | W |
| P9 | `feature-requests.txt` and `sessions/` are the local inbox and record; both untracked; dated one-liners are data about the owner's spelling. | The inbox is private; the spelling is signal. | sessions/2026-09-13, 09-28 | C |
| P10 | Research traces persist under `docs/research/` with frontmatter and a tldr; read `head -15` first. | Never fully reused is fine; the trace is the point. | docs/research/* (branch) | W (branch) |
| P11 | Level-set process depth before ceremony; native execution over subagents unless asked. | A mid-sized change does not need the full ladder. | global CLAUDE.md § Process depth (origin here, 2026-09-28) | C |
| P12 | The root reads as "a Python CLI with docs and tests" on first `ls`; release machinery gets its own directory with a scoped README. | The root "is unsettling" (owner, 2026-11-08). | intent specs/root-layout.md | C |

## Collaboration with agents

| # | Principle | Rationale | Source | Status |
|---|---|---|---|---|
| A1 | Scope is the owner's; mechanics are the agent's. Before a delete, a cross-repo change, a trust-boundary change, or anything outward: one closed question with a stated default. | The owner decides what; the agent decides how. | global CLAUDE.md § Coordination state; memory 2026-11-08 | C |
| A2 | Small: ship with spec and test in one commit. Large: spec, bead, wait for review. | Size decides ceremony. | intent collaboration.md | C |
| A3 | When the surface is in question, do not build the plumbing. | Remote-tap parked on `-t` vs `--tap=`. | intent principles.md | C |
| A4 | Articulate locally first: the `draft/intent` worktree (INTENT.md, refs/, specs/, sessions/) before anything moves outward; `draft/*` is hook-refused on push. | Intent is cheaper to correct before it is pushed. | global CLAUDE.md; hooks/pre-push | C |
| A5 | Never move the owner's checkout; work in `.claude/worktrees/*`. | The owner's tree is theirs. | INTENT § Decided | C |
| A6 | Check `sessions/*request*` on status queries and diff against beads. | The inbox is the ground truth for "what's pending". | memory | C |
| A7 | Pull-discovery of cross-project learnings, not push. | Check when relevant, not every session. | global CLAUDE.md | C |
| A8 | The RULE 0 and no-destructive-git rules in agents/beads-viewer.md are upstream text copied verbatim; the project has neither endorsed nor rejected them. | Know which rules are ours. | agents/beads-viewer.md line 1 | W (unowned) |
