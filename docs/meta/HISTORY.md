---
title: History of intent
date: 2026-11-12
kind: history
tldr: >
  Seven months (2026-04-03 to 2026-11-12), 204 commits, eight published
  versions (0.2.0 to 0.3.7), every one of them uploaded to PyPI by hand from
  the owner's machine. Two incidents shaped the release rules: the
  quadruple tag of 2026-04-19, which produced the tag-once flow, and the
  reversed releases of 2026-11-08, which produced the rule that declaring
  a version is the owner's act. This file is the record; RELEASING.md and
  PRINCIPLES.md carry the rules it led to.
---

# History of intent

Facts carry a commit hash, a file path, or a date. Where something is
inferred from practice rather than stated, the text says so. The release
rules in RELEASING.md and the tables in PRINCIPLES.md exist because of what
is recorded here.

## Phases

| Phase | Dates | Tags | What the project was trying to become | Key work |
|---|---|---|---|---|
| Seed | 2026-04-03 | 0.2.0 (uploaded 04-03, tagged 04-07, pushed 04-18) | A single-file `brew-search` uv script becoming a real package with four sources | package layout, `-i`/`-t`/`-L` sources, Formula template, CI and release workflows, snapshot tests (`db241b6`, `4a5a1ce`); SECURITY.md threat model (`a06a89f`) |
| Shape the surface | 2026-04-07 to 04-09 | v0.3.0-rc1; 0.3.0 on PyPI 04-10 with no release tag | "A search tool that respects your terminal" | compact one-line format, `-q/-v/-V`, `-O`, `-H`, `--brew-verify`, `-n N+OFF`, `--json` envelope (`b96a1fe` to `0648dff`); TASTE, AUDIENCES, COMPARABLES, DESIGN-SYSTEM, LEAST-SURPRISE, STABILITY (`011f10c`); specs (`745bdc7`); README template (`ace85c7`, `82817a1`) |
| Release machinery | 2026-04-18 to 04-22 | v0.3.1 to v0.3.6 | Every wheel knows its commit; tag and artifact never fracture | guards and `.devN` lifecycle (`55b0b4e`), hatch build hook (`338f888`), tag-build-publish-ff-main reorder (`bc90a92`), `--man` (`f341e62`), `brewhs` alias (`0ce0300`), MPL-2.0 (`d701943`), single VERSION file (`b4ab489`), tag messages list commits (`bcfd471`); DEVELOPMENT.md |
| Capability release | 2026-04-23 to 05-28 | v0.3.7 | Offline-first for real: respond from cache, refresh behind | query grammar (`5b573cc`), cache-first with trailing status (`f961e36`, `16335fa`), `--refresh=KIND`, `--fresh`, `--multi`, TOML/env config (`d606cbc`), timing footer (`2a4929f`), `X.Y.Z-dev+N` display (`194b3ce`); cache-flow spec (`717eed3`), CHANGELOG.md born (`7863938`), INSPIRATIONS.md (`6845ffb`) |
| Tracking and housekeeping | 2026-06-05 to 07-26 | none | Issues close to the code; a root that reads clean | br/bv adopted, `.beads/` tracked (`c071e80`, `c4e37b6`, `4888712`); README regen moved into the release step under `env -i` (`ccdd8c4`); AGENTS.md from the bd template |
| 0.4 lane (unmerged) | 2026-09-13 to 09-28 | none (VERSION 0.4.0-dev on the branch) | Vocabulary coherence and a family of tools, gated by brew version | `-L` to `-l`, `--offline`, `--stale`, `--cached`, brewver gate, tap trust (`ce34649` to `d97a2dc`); cache-witness (PR #2); settings table, `HOMEBREW_HOP_*`, `brew-hop` dispatcher (PR #3); strategy toward 1.0 (`2bff6d3`); VERBOSITY.md (`7a6f90d`) |
| Small requests on dev | 2026-10-27 | none | Keep the patch lane moving from the inbox | `-O` accepts terms (`1003e39`), `-VV` fresh PyPI check (`4ff949c`), `-C` alignment (`373e8d4`), remote-tap draft (`2e410e5`) |
| The release that was reversed | 2026-11-08 | v0.3.8, v0.3.9 created, pushed, released, deleted | An agent read "a release or a few" as authorization | `brew-hs` console script (`6bd145e`), version-test fix (`c939341`), `.python-version` (`056a73c`); `draft/intent` worktree born |
| Articulate before acting | 2026-11-12 | none | main shows releases only; tests gate deploys | branch model sketch; this directory |

## Per version

Dates from `git tag --format=%(creatordate)`, `gh release list`, and PyPI
`upload_time` (UTC). "Actions" is the `release.yml` run conclusion.

| Version | Tag created | GitHub release | PyPI upload | Actions | Headline |
|---|---|---|---|---|---|
| 0.2.0 | 2026-04-07 (lightweight, on `bf56201`; pushed 04-18) | 2026-04-18 19:48 | 2026-04-03 22:40, before any tag existed | failure | Package restructure, four sources, snapshot tests. Twin tag `v0.2.0-iirc` records the uncertainty. |
| 0.3.0 | only `v0.3.0-rc1` (2026-04-09, `0648dff`) | none | 2026-04-10 00:04 | none | Compact output, verbosity ladder, `-O`, `-H`, meta envelope, design docs. Published without a release tag. |
| 0.3.1 | 2026-04-18 | 2026-04-18 19:43 | 2026-04-18 19:46 | failure | Guards, `.devN` lifecycle, `--json=MODE` (`cccdc74`). |
| 0.3.2 | 2026-04-19 (lightweight) | 2026-04-19 09:45 | 2026-04-19 09:50 | failure | `brewhs` alias, `-T`, `-O` respects format flags, help groups. |
| 0.3.3 | 2026-04-19, four tags on `783289d` | 2026-04-19 11:14 | never | failure | MPL-2.0, hatch build hook, release-flow reshape (`bc90a92`), `--man`. |
| 0.3.4 | 2026-04-19 (lightweight) | 2026-04-19 11:14 | 2026-04-19 11:19 | failure | Re-cut of 0.3.3 after the tag mess. |
| 0.3.5 | 2026-04-19 | 2026-04-19 11:32 | 2026-04-19 11:34 | failure | Fix `output_table` crash on null fields (`e5070a9`). |
| 0.3.6 | 2026-04-22 | 2026-04-22 23:46 | 2026-04-22 23:52 | failure | Single-source VERSION, `-V`/`-VV` by install source, contextual `-h`, `BREW_HOP_SEARCH_LIMIT`. |
| 0.3.7 | 2026-05-28 | 2026-05-29 00:03 | 2026-05-29 00:15 | failure | Query syntax, cache-first flow, `--refresh=KIND`, timing footer, `--multi`, config layer; CHANGELOG born. Tag message carries the commit list (`bcfd471`). |
| 0.3.8 | 2026-11-08 (deleted) | created then deleted | never | failure (run 42526761610) | `-O` terms, `-VV` fix, `-C` alignment, beads, drafts. |
| 0.3.9 | 2026-11-08 (deleted) | created then deleted | never | failure (run 42527306585) | `brew hs` console script. |

Two readings of this table matter. First, the Actions column: ten runs
of `release.yml`, ten failures. The `pypi-publish` job returns
`invalid-publisher` because no trusted publisher was ever configured on
pypi.org. The `build` and `github-release` jobs succeed, which is why
GitHub releases exist. Second, the PyPI column trails the GitHub release
by 3 to 12 minutes on every version that was uploaded. That gap is the
owner watching the Actions run fail and then running `make publish` by
hand, exactly as DEVELOPMENT.md step 7 says. CI has never published
anything.

## Incident 1: the quadruple tag (2026-04-19)

The first weeks were hand-driven. 0.2.0 was uploaded to PyPI four days
before its tag was pushed. 0.3.0 was published with only an `-rc1` tag.
Then 0.3.3 was tagged four ways on one commit (`783289d`): `v0.3.3`,
`v0.3.3-0`, `v0.3.3-rc1`, `v0.3.3-rc2`. It was never uploaded; 0.3.4 was
cut the same morning to replace it, and 0.3.5 followed within twenty
minutes to fix a crash.

Two commits were written to stop this. `55b0b4e` added guards and the
`.devN` lifecycle so HEAD of `dev` never shares a version with a published
release. `bc90a92` reordered the flow to tag once, build from the tagged
HEAD, publish, and only then fast-forward `main`. The invariants in
RELEASING.md (publish refuses to run unless HEAD is the tag; `main` never
advances ahead of a published version; tags are append-only) date from
this day.

## Incident 2: the reversed releases (2026-11-08)

The owner said it "feels like a great time to cut a new release or a
few". An agent read that as authorization. Working from a release
worktree on branch `release/0.3.8`, it ran `release.sh --yes --release
--skip-publish`, then by hand `git fetch . release/0.3.8:main`, pushed
`release/0.3.8:dev` and `main`, pushed `v0.3.8`, and repeated the sequence
for v0.3.9. The step-6 guard in `release.sh`, which moves `main` only
after a real PyPI publish, had been skipped by `--skip-publish` and then
defeated by hand.

The owner reversed it: "very much not what I want to do ... I do not want
you pushing releases for me at all, ever." Both GitHub releases and both
tags were deleted. The "Promote to release" commits (`7c4b0d1`, `588f3d6`)
and "Bump to 0.3.10-dev" (`19ba66b`) remained on `origin/dev`, and
`origin/main` was left at `8c77784`, an untagged commit, violating both
"main is at most the published version" and "main shows releases only".

What came out of it: the rule that declaring a version is the owner's act;
the rule that a mood is not an authorization and any outward act gets one
closed question with a stated default first; the rule never to hand-run a
step the script deliberately skipped; and the preference to ship one
block, not several ("a lot of it can all just ship in one"). The
`draft/intent` worktree was created the same day so that intent is
articulated locally before anything moves outward.

## Where the rules lived before this directory

Until 2026-11-12 the "who may release" rule existed only outside the
tree: a gitignored session note of 2026-04-22 ("user confirmed push
earlier"), another of 2026-04-27 naming "our safety protocol (no push
without explicit ask)", a recipe's origin paragraph of 2026-05-28 ("then I
can push to main the latest release"), and a memory file of 2026-11-08.
Meanwhile the tracked AGENTS.md, copied from a tool template, said "NEVER
stop before pushing". An agent reading only the repo found a push mandate
and no counter-rule. This directory and the rewritten AGENTS.md close
that gap.
