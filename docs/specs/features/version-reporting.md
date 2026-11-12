---
title: Version reporting — what -V, -VV and the User-Agent say, and where the facts come from
date: 2026-11-12
kind: feature-spec
tldr: >
  The displayed version has three shapes (X.Y.Z, X.Y.Z-dev+N, X.Y.Z+N)
  built from two layers: the VERSION file and a commit count. The count
  comes from git only when the package runs from its own checkout;
  everywhere else it comes from _build_info.py baked at build time. -VV
  compares against PyPI and names four states: up to date, behind, ahead,
  and ahead-with-an-unqualified-version (which exits 1). This spec lists
  the behaviour per deployment environment, because "+95 from Homebrew's
  repo" is the kind of surprise it exists to prevent.
---

# Version reporting

People ask "which version am I running, and is it the one on PyPI?" The
answer is layered on purpose, and each layer is observable.

## Layer 1: the VERSION file

`src/brew_hop_search/VERSION` holds one line: `X.Y.Z` (a release) or
`X.Y.Z-dev` (between releases). It is the single source for hatch
(`[tool.hatch.version]`), for `__version__`, and for the release scripts.
Invariant: HEAD of `dev` never shares its version with a published release
(`DEVELOPMENT.md` § Version invariant).

## Layer 2: commits since the last tag

The count turns `0.3.8-dev` into `0.3.8-dev+27`. Two sources, one gate:

| source | used when | how |
|---|---|---|
| git | the package runs from **its own checkout** | `git describe --tags --abbrev=0`, then `git rev-list --count <tag>..HEAD`, both run with `-C <toplevel>` |
| `_build_info.py` | everywhere else | `BUILD_COMMIT_COUNT`, baked by `hatch_build.py` at build time, shipped inside the wheel and the sdist |

**The gate** (`_dev_tree_git()`): `git -C <package dir> rev-parse
--show-toplevel` walks up through parent directories, so it must be
checked, not trusted. The toplevel counts only if it holds
`pyproject.toml` and `src/brew_hop_search/VERSION` and the package
directory is underneath it. A brew install under `/opt/homebrew/Cellar`
finds Homebrew's own repo at `/opt/homebrew/.git`; an sdist extracted
inside any checkout finds that checkout. Both are rejected and fall back
to `_build_info`. The build hook applies the same rule
(`project_is_git_toplevel`): a parent directory's repo is "no git", so the
sdist-phase `_build_info.py` survives the wheel build.

Why it matters: 0.3.7 from the tap reported `0.3.7+95`, commit
`b70618fe42`, install `local`, and ten Homebrew/brew merge commits as
"recent commits". Every one of those facts belonged to `/opt/homebrew`.

## Layer 3: the three shapes

| shape | meaning | example |
|---|---|---|
| `X.Y.Z` | tagged release, or count is 0 | `0.3.7` |
| `X.Y.Z-dev+N` | a dev tree, N commits past the last tag, running from its own checkout | `0.3.8-dev+27` |
| `X.Y.Z+N` | a *built* artifact between tags (wheel or sdist); `-dev` dropped to say "built, could ship" | `0.3.8+27` |

PEP 440 reads all three (`-dev` → `.dev0`, `+N` is a local version label,
stripped by PyPI on upload). `packaging.Version` does the comparisons.

## Per environment

| environment | install source | commit | count | recent commits |
|---|---|---|---|---|
| `uv run` / editable install from the repo | `local` | live git | live git | shown (own log) |
| `uv tool install`, `pip install`, `uvx` (PyPI wheel) | `pypi` | baked | baked | not shown |
| `brew install mcint/tap/brew-hop-search` (Cellar) | `brew` | baked | baked | not shown (Homebrew's log is *not* ours) |
| sdist built inside another repo | per the above | baked from the sdist phase | baked | not shown |
| anything else (vendored copy, zipapp) | `unknown` | baked if present, else empty | baked if present, else 0 | not shown |

`install_source()` says `local` only when the gate accepts the repo;
otherwise it reads the path (`/Cellar/` or `/linuxbrew/` → `brew`,
`site-packages` → `pypi`).

## -V, -VV, -VVV

- `-V`: one line, the display version.
- `-VV`: the block (version, commit, install, user-agent, pypi, github,
  tap), recent commits when running from the own checkout, then a live
  PyPI check with a 15 s timeout and write-back of the check time.
- `-VVV`: reserved; see `docs/specs/drafts/` when the history-by-release
  view lands (the sketch is in the intent worktree).

### The four PyPI states

| local vs PyPI | prints | colour | exit |
|---|---|---|---|
| equal | `up to date (X.Y.Z)` | green | 0 |
| behind | `X.Y.Z available (current: …)` + `pip install -U` hint | yellow | 0 |
| ahead, qualified (`-dev`, `+N`, `rcN`, `aN`, `bN`, `.postN`) | `ahead of PyPI (local …, pypi …)` | blue | 0 |
| ahead, **unqualified** (plain `X.Y.Z` PyPI has never seen) | `X.Y.Z is not on PyPI (latest …): unqualified version ahead of the index` | red | **1** |

"Up to date" is reserved for equality. The unqualified-ahead state is a
release that was never declared, or a tree that forgot its `-dev`; the
release guards exist to prevent exactly that, so `-VV` balks loudly and
scripts can notice.

## User-Agent

`brew-hop-search/<display version>`, so the formulae.brew.sh logs can tell
a dev tree from a release. Overridable with `BREW_HOP_SEARCH_UA` or the
config file.

## Tests

`tests/test_version.py` (shapes, fallback, the fresh PyPI fetch),
`tests/test_version_ahead.py` (the four states), `tests/test_foreign_git.py`
(the gate, the build hook, the hidden recent-commits block).
