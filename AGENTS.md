# Agent Instructions

Rules for any agent working in this repository. Short on purpose; the
reasoning and history live in `docs/meta/`.

## Releases and branches (the owner's acts)

- Declaring a version is the owner's act. Never create or push a
  `vX.Y.Z` tag, never `gh release`, never `uv publish`, never move `main`.
- Stop at "ready to tag": changelog written, VERSION promoted, suite
  green, `dist/` built, and the exact commands printed for the owner.
- Before any outward act (push, tag, release, PR, force-move, delete), ask
  one closed question with a stated default and wait. A mood ("feels like
  time for a release") is not an authorization.
- `main` holds only tagged releases, fast-forwarded by the owner. Agents
  never push it.
- `dev` is the integration lane. Agents may push fast-forward commits and
  `feat/*` branches once the suite passes.
- Pre-release or agent-marked tags may be pushed (`-rcN`; `proposed/…`
  once the convention is settled). Plain `vX.Y.Z` may not.
- Never hand-run a step that `scripts/release.sh` deliberately skipped.
  `--skip-publish` also skips ff-main and the post-bump, on purpose.
- PyPI publishing is local (`make publish`) and the owner's. The Actions
  `pypi-publish` job has never succeeded (bead bhs-59v). Do not route
  around it.

## Working tree

- Work in `.claude/worktrees/*`. Never check out or move the owner's
  working tree.
- Coordinate locally first. The `draft/intent` worktree
  (`.claude/worktrees/intent`) holds the branch map, decisions and parked
  questions. `draft/*` branches never push.
- `feature-requests.txt` and `sessions/` are the local inbox and record
  (gitignored). Read the newest `sessions/*request*` before answering
  "what's pending".

## Code, specs, tests, commits

- Spec first or alongside, never last. A new feature ships with a new
  red-green snapshot test in the same commit.
- Conventional Commits with scope; small scoped commits; never amend or
  rebase shared history without asking.
- Pin the dev interpreter with `.python-version`; the CI matrix, not the
  pin, sets `requires-python`.
- Lowercase flags are sources and adverbs, UPPERCASE are verbs and info.
  Renames keep a hidden alias with a stderr hint for one release.
- `-v` adds provenance, `-vv` what the tool did, `-vvv` raw material;
  always to stderr; machine formats ignore the ladder.
- Default output is clean and never calls `brew`; details and
  subprocesses are opt-in.

## Issue tracking

- `br` (beads) is the tracker; `bd` is retired. After changes:
  `br sync --flush-only`, then `git add .beads/ && git commit`. Full
  workflow: `AGENTS.beads_viewer.md`.
