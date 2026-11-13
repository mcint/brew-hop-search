---
title: Decisions
date: 2026-11-12
kind: decision-log
tldr: >
  ADR-lite. One short entry per decision that shaped the project: license,
  argparse, the `brewhs` and `bhs` names, the `-L` to `-l` rename and the
  capitalization rule, 0.4.0 as a minor, the `brew-hop` namespace, beads in
  git, README as a release artifact, the `.python-version` pin, and
  releases as the owner's act. Each entry gives context, decision and
  consequence with the commit or date that fixed it.
---

# Decisions

Format: context, decision, consequence. Newest last. A decision that is
revisited gets a new entry, not an edit.

## 1. MPL-2.0 (`d701943`, 2026-04-19)

Context: the package needed a license before the 0.3.3 release; the
owner wanted file-level copyleft without the viral reach of GPL.
Decision: relicense under the Mozilla Public License 2.0.
Consequence: modified files must stay MPL; the package can be vendored
into other-licensed projects. `pyproject.toml` carries the SPDX id.

## 2. argparse over click

Context: the tool began as a single-file uv script; every dependency
costs install time and surface. click, typer and rich were considered.
Decision: stdlib argparse, raw ANSI, and only `sqlite-utils` and
`packaging` as runtime dependencies.
Consequence: help modes (`-h`, `--help=MODE`, `--man`) are hand-built on
argparse; contextual help needed custom code (`f341e62`). COMPARABLES.md
§ Intentionally Distant records the position.

## 3. `brewhs` chosen, `bhs` informal (`0ce0300`, 2026-04-19)

Context: `brew-hop-search` is long to type; drafts/short-names.md weighed
`bhs` and rejected it as "too generic; high chance of PATH collision".
Decision: ship `brewhs` as the installed alias.
Consequence: `bhs` nonetheless became the tool's spoken short name in
every doc, label and bead prefix (`89d4f5f`, "Rename fast -> bhs"), and
strategy-toward-1.0 says it "survives as the short alias either way". The
Decision section of short-names.md is stale and should be updated.

## 4. `-L` to `-l` and the capitalization rule (`ce34649`, 2026-09-13)

Context: `-L` (local brew DB) was the one lowercase-shaped source with an
uppercase letter, and the flag set had no stated rule.
Decision: lowercase flags are sources and adverbs (`-f -c -i -t -l`,
`-q -v -g`); UPPERCASE flags are verbs and info (`-O -H -C -V -T`). `-L`
becomes `-l`, kept one release as a hidden alias with a stderr hint.
Consequence: every future flag has a predictable case. The rename sits on
the unmerged 0.4 lane; dev docs still show `-L`. A later release may
deprecate `-L` while adding `--offline`.

## 5. 0.4.0 as a minor, not a major (`ad892fc`, 2026-09-13)

Context: the 0.4 lane renames `-L` and adds `--offline`, `--stale`,
`--cached` and a brew-version gate. Is a rename a breaking change?
Decision: minor. "Minor, not patch: -L is renamed. Not major: nothing a
0.3.7 script relies on breaks", because the alias holds for one release.
Consequence: the rule generalises (PRINCIPLES R14): minor for widened or
renamed surface, patch for fixes, major only after two minors with zero
renames. Whether the next release is 0.3.8 or 0.4.0 is still open.

## 6. Project becomes `brew-hop` with the subcommands (`7a6f90d`, 2026-09-28)

Context: the tool is outgrowing "search"; `brew hop <verb>` is the
family, and strategy-toward-1.0 § 3 ties the rename to the dispatcher.
Decision: the project becomes `brew-hop`; the rename ships with the
subcommand layer (0.5). The feat/peek dispatcher already installs a
`brew-hop` entry point.
Consequence (2026-11-12 nuance): the `brew-hop` namespace is grown
carefully and separately from the search tool, and the name may become
`brew-hopp`, `brew-hopb` or `brew-hopt` to avoid interfering with other
tools. The next release ships `brew-hs` (`6bd145e`) so `brew hs` works,
and keeps the `bhs` / `brewhs` / `brew-hop-search` UX unchanged.

## 7. Beads tracked in git (`4888712`, 2026-06-05)

Context: `bd` was tried and found schema-broken; `br` (beads_rust) with
the `bv` TUI worked. Where should the issue store live?
Decision: `.beads/` is tracked. `br sync --flush-only` then a manual
`git add .beads/ && git commit`; `bd` is retired.
Consequence: issues travel with the code and appear on `main` at release
time. The owner later confirmed this was their own choice and that
`.beads/` on `main` is "not by itself the problem; main carrying an
untagged release is" (INTENT § Reversed).

## 8. README as a release artifact (`ccdd8c4`, 2026-07-26)

Context: README examples drifted from live output between releases.
Decision: regenerate README from `README.md.template` with live command
output at the tag step, under `env -i`, as part of `release.sh`.
Consequence: the README on `main` shows exactly what the tagged version
prints. The build must run in a clean environment so the owner's config
does not leak into examples.

## 9. `.python-version` pin vs the CI matrix (`056a73c`, 2026-11-08)

Context: the dev shell needed a predictable interpreter, but a pin can
quietly become a floor.
Decision: pin the dev interpreter with `.python-version`; let the CI
matrix (3.9/3.15) measure the real floor; the pin never narrows
`requires-python`.
Consequence: `requires-python` changes only when a dependency forces it
and the matrix shows it. Global rule: "let a matrix, not a pin, say what
works".

## 10. Releases are the owner's (2026-11-08, written down 2026-11-12)

Context: an agent cut, tagged, pushed and released v0.3.8 and v0.3.9 on
the strength of "feels like a great time to cut a new release or a few".
The owner reversed both: "I do not want you pushing releases for me at
all, ever."
Decision: declaring an official version (pushing `vX.Y.Z`, GitHub
release, PyPI upload, moving `main`) is the owner's act, after they
review the tests. Agents prepare on `dev` and stop at "ready to tag".
Agents may push `dev`, `feat/*`, `-rcN` tags and `tag-draft/vX.Y.Z`
pointers. `main` stays the default branch, protected so only the owner
pushes it. CI tests all branches; the release workflow tests before it
publishes.
Consequence: RELEASING.md, BRANCH-MODEL.md and the rewritten AGENTS.md.
The tracked AGENTS.md push mandate from the bd template is replaced.
`origin/main` at `8c77784` and the two untagged "Promote to release"
commits on `origin/dev` await the owner's reset, rewind or re-cut.
