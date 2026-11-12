---
title: Branch model
date: 2026-11-12
kind: spec
tldr: >
  Three kinds of ref. `main` is the default branch and holds exactly the
  tagged releases, moved only by the owner. `dev` is where the block for
  the next version forms. Agents may push `<type>/<slug>` branches, `-rcN` and `tag-draft/*`
  tags. CI runs the suite on every branch and PR; the release workflow
  tests before it publishes. Not full git-flow: no `release/*` branches,
  no `hotfix/*` until a shipped version needs one.
---

# Branch model

What the owner asked for (2026-11-12): "I want main to only show releases,
perhaps I should make release my default branch. I want to add an actions
test running for deploys. I don't quite know if I want to go full git-flow
but something more this direction."

## Refs and who moves them

| ref | holds | moved by | pushed by agents? |
|---|---|---|---|
| `main` | one commit per release, each tagged `vX.Y.Z`; fast-forward from `dev` at release time | the owner | never |
| `dev` | the forming block for the next version; always green | owner and agents | yes, fast-forward only |
| `<type>/[<group>/]<slug>` | one feature, fix, doc or chore; PR or fast-forward into `dev` | agents and owner | yes |
| `vX.Y.Z` tag | official version | the owner, after reviewing the test run on the release commit | never |
| `vX.Y.Z-rcN` tag | candidate for review; builds, publishes to TestPyPI only | agents or owner | yes |
| `tag-draft/vX.Y.Z` tag | "an agent thinks this is the release commit"; no workflow fires | agents | yes |
| `draft/*` | local intent, scratch | anyone | hook-refused |

## Branch names

Decided 2026-11-12: branch names hew to Conventional Commits. The first
segment is the type that the branch's squashed commit would carry: `feat`,
`fix`, `docs`, `chore`, `ci`, `test`, `refactor`, `spec`. The last segment
is a short kebab-case slug. An optional middle segment groups branches by
session, date or theme, where taste wants it: `feat/brew-hs`,
`fix/foreign-git-tree`, `docs/meta`, `chore/2026-11-12/dev-rebuild`,
`feat/vocab/offline-adverb`. The type is the contract; the group is free.
`main` and `dev` are the only bare names; `draft/*` is local-only
(hook-refused on push); `tag-draft/` and `v` are tag namespaces, not
branches. Branches that predate the rule (`dev-clean2`,
`backlog-0.4-clean`, `statusline-history`) keep their names until deleted.

## Default branch

Decided 2026-11-12: `main` stays the default branch and is the release
branch. Visitors land on the latest release, which is what "main only
shows releases" already implies, and GitHub's default-branch conventions
(README render, PR base) favour it. The owner protects it: pushes
restricted to the owner, no force-push, CI check required. PRs target
`dev`, set per PR or by a repo rule.

The alternative, renaming to `release` and making `dev` the default, was
set aside. The word "release" is already taken by tags and by the proposed
`release/` directory for the scripts; a third use muddies it, and every
link to `main`, the CI trigger, and `git fetch . dev:main` would change.

## Workflows

- `ci.yml`: on push to any branch and on PR. `uv sync`, suite, smoke test,
  matrix 3.9/3.12/3.13. Today it runs only on `main` and PRs, so `dev` and
  work-branch pushes go untested; the trigger widens to all branches.
- `release.yml`: on `v*` tags only. Job order: test (same matrix, at the
  tag), then build, then publish. `-rc*` tags publish to TestPyPI; plain
  `vX.Y.Z` to PyPI via trusted publishing once configured (bead bhs-59v).
  GitHub release created with generated notes. `tag-draft/*` tags match no
  workflow.

## Release procedure

See RELEASING.md for the owner's command sequence and the reasoning. In
short: `make release --skip-publish` on `dev`, push `dev`, review, push
`vX.Y.Z`, `git fetch . dev:main && git push origin main`. Agents stop
before the tag push and may leave a `tag-draft/vX.Y.Z` pointer on the same
commit.

## Not git-flow

No long-lived `release/*` branches: the block is small and review happens
on `dev`. No `hotfix/*` until a shipped version needs a patch that cannot
wait for the next block. No `develop` rename. History on `main` is
linear: fast-forward or rebase, never merge commits.

## Open

- Direct pushes to `dev` by agents, or PRs only? Default: PRs for
  features, direct fast-forward for chores, both after the suite.
- Where does the version bump live: a commit on `dev` before the tag (as
  today) or set by the tag (hatch-vcs style)? Default: as today. The
  VERSION file is the single source and `-VVV` reads it.
