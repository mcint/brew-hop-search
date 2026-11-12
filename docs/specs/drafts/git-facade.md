---
title: git facade: one place for git facts about this package
date: 2026-11-12
kind: spec-draft
tldr: >
  A stdlib-only module, src/brew_hop_search/_git.py, becomes the only
  code that runs git about *this* package. Every reader goes through
  toplevel(), which answers None unless the repo found is the project's
  own checkout. hatch_build.py loads the same file by path. history.py
  stays out: it asks the Homebrew tap repo, a different question.
---

# Git facade

## Purpose

Six places run `git` today. Five ask about this package (commit, tag
distance, recent log, build stamping) and two of them re-implement the
"is this repo ours" gate with different rules. The sixth, `history.py`,
asks Homebrew's repo for its HEAD and is not about us. Fold the five into
one module so the gate exists once, is tested once, and is faked at one
seam. Background and prior art:
`docs/research/2026-11-12-git-facts-prior-art.md`.

## Design

### Module

`src/brew_hop_search/_git.py`. Imports: `os`, `subprocess`, `pathlib`.
No import of `brew_hop_search`, no relative imports (see Build hook).

    def run(args, cwd, *, timeout=5) -> str | None
        # the only subprocess call in the module; "" or None on any
        # failure; child env has GIT_DIR, GIT_WORK_TREE, GIT_INDEX_FILE,
        # GIT_PREFIX removed; GIT_CEILING_DIRECTORIES set by callers.

    def toplevel(start: Path, expected: Path) -> Path | None
        # rev-parse --show-toplevel from `start`, with
        # GIT_CEILING_DIRECTORIES=expected.parent so git never walks past
        # `expected`. Returns `expected` when git agrees it is the
        # toplevel; None otherwise (no repo, foreign repo, no git).

    def short_head(top) -> str
    def count_since_tag(top) -> int        # 0 on any failure
    def recent(top, n=10) -> list[str]     # `log --oneline -n`
    def describe(top) -> dict              # for the build hook:
        # commit_full, branch, tag (exact), last_tag, dirty

Every function except `run` and `toplevel` takes the `top` that
`toplevel()` returned and does nothing clever with it. Callers decide
`expected`:

- package at runtime: `expected = Path(__file__).resolve().parents[1]`
  (`src/brew_hop_search` -> repo root). Under site-packages or a Cellar
  this is `lib/python3.x`, which is never a toplevel, so None.
- build hook: `expected = Path(self.root)`.

The gate rule is therefore one sentence: *git facts are used only when
the toplevel git reports equals the directory this project expects to be
its root*. The ceiling makes the walk stop there; the equality check is
what tests can fake. The `pyproject.toml` / `VERSION` marker checks in
today's `_dev_tree_git()` are dropped; they only restate the same fact.

### Package wrapper

`__init__.py` keeps its public names and shrinks:

    def _dev_tree_git() -> Path | None:
        return _git.toplevel(PKG_DIR, PKG_DIR.parents[1])

`commit_hash()`, `_commit_count_since_tag()`, `install_source()` call
`_git.short_head(top)` / `_git.count_since_tag(top)` and fall back to
`_build_info` exactly as now. `cli._show_version` replaces its inline
`subprocess.run` with `_git.recent(top)`.

### Build hook

hatchling loads `hatch_build.py` by file path and does not put the
project root or `src/` on `sys.path`; the backend subprocess has
`cwd=root` but `cwd` is not on `sys.path` either. So the hook loads the
facade the same way hatchling loaded the hook:

    spec = importlib.util.spec_from_file_location(
        "_bhs_git", Path(self.root) / "src" / "brew_hop_search" / "_git.py")
    git = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(git)
    top = git.toplevel(Path(self.root), Path(self.root))

`_git()` and `project_is_git_toplevel()` in the hook are deleted. The
sdist already ships `src/`, so the wheel-from-sdist step finds the file;
in that step there is no repo at `root`, `toplevel()` is None, and the
existing "keep the sdist-phase `_build_info.py`" branch runs unchanged.

### Out of scope

- `history.py::_brew_commit()` asks `brew --repository`'s git for its
  HEAD. Different repo, different purpose, and the ownership gate would
  be wrong there. It may reuse `_git.run()` for the env scrub and
  timeout, nothing more.
- No external dependency. No spin-off until a second consumer exists.

## Tests

Red first. `tests/test_git_facade.py` (new) and
`tests/test_foreign_git.py` (trimmed):

- `toplevel()` on this checkout returns the repo root; with `start`
  inside a `tmp_path` repo whose parent is also a repo and
  `expected=inner`, returns `inner`; with `expected=inner` but no
  `.git` in `inner`, returns None even though the outer repo exists
  (the ceiling test). Real git, `tmp_path`, no mocks.
- `run()` strips `GIT_DIR` and friends from the child env (set them in
  `monkeypatch`, assert the child does not see them via
  `git rev-parse --git-dir`).
- The existing foreign-git tests keep their assertions but fake
  `brew_hop_search._git.run` only, never `subprocess.run`. The autouse
  `_no_git_env` fixture goes away once `run()` scrubs the env itself.
- `test_build_hook_refuses_parent_repo` stays, now exercising the hook's
  by-path load of `_git.py`.

## Migration

One commit per row, each green on `make test`:

1. `feat(git): add _git facade with run/toplevel/short_head/...` plus
   `tests/test_git_facade.py`.
2. `refactor(version): route __init__ git calls through _git`.
3. `refactor(cli): -VV recent commits via _git.recent`.
4. `refactor(build): hatch_build loads _git by path; drop local _git()`.
5. `test(foreign-git): fake _git.run only; remove GIT_* fixture`.
6. `docs(specs): fold this draft into version-reporting.md § Layer 2`
   and add the INSPIRATIONS rows.

## Examples

Dev tree (`uv run brew-hop-search -VV`): `toplevel()` returns the
checkout; version shows `0.3.10-dev+7`, commit, and ten recent commits.

Brew install under `/opt/homebrew/Cellar/brew-hop-search/0.3.9/libexec/
lib/python3.13/site-packages/brew_hop_search`: `expected` is
`lib/python3.13`, ceiling is `libexec/lib`, git finds nothing, `toplevel()`
is None; `-VV` shows the baked commit and no recent-commits block.

sdist extracted inside `~/src` (itself a repo) and built there:
`toplevel(root, root)` is None because git stops at `~/src/bhs-0.3.9`'s
parent; the hook keeps the `_build_info.py` written in the sdist phase.
