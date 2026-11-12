---
title: Releasing
date: 2026-11-12
kind: procedure
tldr: >
  Declaring a version is the owner's act: pushing a `vX.Y.Z` tag, creating
  the GitHub release, uploading to PyPI, and moving `main`. Agents prepare
  the release on `dev` and stop at "ready to tag". Publishing is local today
  because the Actions publish job has never had a trusted publisher; the
  owner runs `make publish` after the tag. `-rcN` and `proposed/vX.Y.Z` tags
  are the visible markers for anything that is not an official version.
---

# Releasing

DEVELOPMENT.md and `scripts/release.sh` describe the mechanics. This file
says who does what and why. HISTORY.md tells the two incidents the rules
come from.

## Who does what

| Step | Actor |
|---|---|
| Write the changelog narrative, promote VERSION, run the suite, regenerate README, build `dist/`, create a local tag | agent or owner |
| Push `dev` and `<type>/<slug>` work branches after the suite passes | agent or owner |
| Push an `-rcN` or `proposed/vX.Y.Z` tag | agent or owner |
| Review the test run on the release commit | owner |
| Push `vX.Y.Z` | owner only |
| `make publish` to PyPI | owner only |
| Fast-forward `main` and push it | owner only |
| Post-release bump to the next `-dev` version on `dev` | agent or owner |

Agents stop before the `git push origin vX.Y.Z` line, always.

## Refs

| ref | holds | moved by | pushed by agents? |
|---|---|---|---|
| `main` | one commit per release, each tagged `vX.Y.Z`; fast-forwarded from `dev` | the owner | never |
| `dev` | the forming block for the next version; always green | owner and agents | yes, fast-forward only |
| `<type>/[<group>/]<slug>` | one feature, fix, doc or chore; merges into `dev` (BRANCH-MODEL.md § Branch names) | agents and owner | yes |
| `vX.Y.Z` tag | official version | the owner, after reviewing the test run | never |
| `vX.Y.Z-rcN` tag | candidate for review; builds, publishes to TestPyPI only | agents or owner | yes |
| `proposed/vX.Y.Z` tag | "an agent thinks this is the release commit"; no workflow fires | agents | yes |
| `draft/*` | local intent, scratch | anyone | hook-refused |

`main` is the default branch and is protected: only the owner pushes it,
no force-push, CI check required. See BRANCH-MODEL.md for the reasoning.

## The owner's sequence

From `dev`, on the release commit:

```
make release --skip-publish   # promote, test, README, local tag, build
git push origin dev
# review: git log v0.3.7..dev, the Actions run on dev, the dist/ wheel
git push origin vX.Y.Z        # the declaration; Actions tests, builds, publishes
git fetch . dev:main && git push origin main
```

Until trusted publishing is configured, `make publish` runs locally
between the tag push and the `main` move.

`--skip-publish` also skips the fast-forward of `main` and the post-bump
on purpose. Never hand-run a step the script deliberately skipped. That is
exactly what happened on 2026-11-08 (`git fetch . release/0.3.8:main` by
hand after `--skip-publish`), and it is why `origin/main` ended up at an
untagged commit.

## Why main moves last

`release.sh` step 6 fast-forwards `main` only after a real PyPI publish.
The invariant is "main is at most the published version", at every
moment. If publish fails, `main` still points at the last version anyone
can install. A visitor who lands on `main` sees a release that exists, and
`git fetch . vX.Y.Z:main` is a ref update, not a checkout, so the owner's
working tree is never touched. The order was set by `bc90a92` after the
2026-04-19 quadruple tag; see HISTORY.md.

## Why publishing is local today

`.github/workflows/release.yml` has a `pypi-publish` job that uses OIDC
trusted publishing. It has failed on all ten tags ever pushed with
`invalid-publisher`, because the trusted publisher was never configured on
pypi.org (bead bhs-59v, planned since `sessions/2026-04-03`). The `build`
and `github-release` jobs succeed, which is why GitHub releases exist.
Every PyPI upload so far was `make publish` from the owner's machine, 3
to 12 minutes after the GitHub release.

Configuring the publisher would change one thing: after the owner pushes
`vX.Y.Z`, Actions would test, build and upload in one run, and `make
publish` would become the fallback. It would not change who pushes the
tag. Credentials and publisher config are the owner's keys; an agent that
hits the failing job reports its exact claims and does not route around
it.

Until then the release workflow should at least run the suite before the
build job, so a tag that fails tests publishes nothing (see Open).

## rc, proposed, official

- `vX.Y.Z-rcN`: a candidate. The workflow fires, tests, builds, and
  publishes to TestPyPI only. Agents may push one when the block looks
  complete and the suite is green.
- `proposed/vX.Y.Z`: a pointer. "An agent thinks this commit is the
  release." No workflow matches it. Agents may push one on the commit they
  stopped at, so the owner can `git log proposed/vX.Y.Z` and decide.
- `vX.Y.Z`: the declaration. Owner only. Tests, builds, GitHub release,
  PyPI.

The marker must be visible in the tag name so nobody mistakes a candidate
for a version.

## What the next release is

The next official version ships `brew <subcmd>` support (`brew-hs`, so
`brew hs` works) and keeps the `bhs` / `brewhs` / `brew-hop-search` UX.
Later releases may deprecate `-L` while adding `--offline`. The `brew-hop`
namespace (name may become `brew-hopp`, `brew-hopb` or `brew-hopt` to
avoid interfering with other tools) is grown carefully and separately; see
DECISIONS.md. Which version number the next release takes (0.3.8, a
0.3.8/0.3.9 split, or 0.4.0) is the owner's call and is still open.

## Open

- `release.yml`: add a test job before `build`; test all branches in
  `ci.yml`, not only `main` and PRs.
- Trusted publishing (bhs-59v): configure it, or delete the job and
  document local publish as the path.
- `origin/main` at `8c77784` and the two "Promote to release" commits on
  `origin/dev`: reset, rewind, or re-cut as the block. Owner's decision.
- Whether this file lives here or as `release/README.md` once a `release/`
  directory exists.
