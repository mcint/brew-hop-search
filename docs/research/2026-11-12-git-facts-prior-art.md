---
question: >
  How do other projects derive version and commit facts from git, how do
  they guard against reading the wrong repo, and what does that imply for
  brew-hop-search's six git call sites (one module, hatch import path,
  external lib, spin-off)?
date: 2026-11-12
kind: full-report
tldr: >
  Every surveyed Python tool shells out to git and lets git's own upward
  walk pick the repo; only setuptools-scm checks that the discovered
  toplevel equals the project root, and it gained GIT_CEILING_DIRECTORIES
  support in 2025 after exactly our failure (tarball inside a foreign
  repo). Go's -buildvcs=auto is the cleanest prior art for "stamp only if
  the thing being built lives in this repo". For bhs: fold the five
  package-side call sites into one stdlib module with a single run() seam,
  bound the walk with GIT_CEILING_DIRECTORIES and an equality check, load
  that file into hatch_build.py by path (hatchling does the same for the
  hook itself; cwd is not on sys.path during a PEP 517 build), take no
  external library, and do not spin off.
---

# Prior art: git facts about the running package

Scope: how projects answer "which commit am I" and "how far past the last
tag am I", at build time or at runtime, and how they avoid answering for
somebody else's repository. The bhs failure that motivates this: a brew
install sits under `/opt/homebrew/Cellar/...`, `/opt/homebrew` is
Homebrew's own checkout, and `git -C <pkg_dir>` walks up into it. 0.3.7
from the tap reported Homebrew/brew's HEAD as its own.

Terms used below. "Walk" is git's default search upward from the start
directory until it finds `.git`. "Gate" is any check a tool adds on top
of the walk. "Baked" means facts written into the artifact at build time
and read back at runtime without git.

## Python version-from-VCS tools

### setuptools-scm (and hatch-vcs on top of it)

- Reads: `git describe`-style tag distance, dirty flag, node; writes an
  optional `version_file` (`_version.py`) at build time. Runtime reads the
  generated file, not git. [1]
- When: build time. `SETUPTOOLS_SCM_PRETEND_VERSION[_FOR_<DIST>]` and
  `fallback_version` cover tarballs without metadata; without a fallback
  it errors. [1]
- Gate: `root` defaults to `.` relative to `pyproject.toml`;
  `search_parent_directories` defaults to `False`. [1] The git backend's
  `GitWorkdir.from_potential_worktree` runs `rev-parse --show-prefix` and
  returns None when the prefix is non-empty, i.e. when the project dir is
  not the toplevel; the error then hints to set
  `search_parent_directories = true`. [2] PR #1106 (merged 2025-02-21)
  made `_git_toplevel` respect `GIT_CEILING_DIRECTORIES`, motivated by a
  tarball without `.git` extracted inside an unrelated repo, where
  setuptools-scm ran `git archive` on the wrong repository. [3] That is
  our bug, in a build tool, fixed the same two ways we are weighing.
- hatch-vcs: a hatchling plugin that forwards to setuptools-scm
  (`raw-options`), adds a `version-file` build hook and a metadata hook
  that fills `{commit_hash}` into URLs. `fallback-version` or it raises.
  Build-time only; editable installs can show a stale version. [4]
- Weight: build requirement only (`setuptools-scm[simple]` plus
  `vcs-versioning`); nothing at runtime if you use the version file. [1]

### dunamai (and uv-dynamic-versioning on top of it)

- Reads: tags, distance, commit, dirty, via `git describe` and friends.
  `Version.from_git(path=None)` runs `subprocess.run(..., cwd=path)`;
  no `git -C`. [5]
- When: either. Build-time via `setup.py` or `poetry version $(dunamai
  from any)`; runtime via `get_version()`, which makes it a runtime
  dependency. [6]
- Gate: none. Detection is the exit code of `git status`; failure raises
  `RuntimeError("This does not appear to be a Git project")`. Discovery
  is left to git, so a package under a foreign repo reports the foreign
  repo. It walks parents itself only for `.git_archival.json`. [5]
- Weight: stdlib-only imports; `packaging` lazily. Still a dependency
  for four subprocess calls. [5]
- uv-dynamic-versioning: hatchling version source "powered by dunamai";
  build-time; no repo-ownership check documented. [7]

### versioningit

- Reads: `git describe` (subprocess; needs git >= 1.8). Optional
  `onbuild` step rewrites `__version__` inside the built sdist/wheel and
  leaves the source tree alone; optional `write` step writes a file. [8]
- When: build time. `default-version` turns any calculation error into a
  fixed version; otherwise the build fails. [8]
- Gate: none documented. The `git` method requires the project to be
  "located inside a Git repository with one or more commits", which a
  foreign parent repo satisfies. [8]

### pdm-backend `source = "scm"`

- Reads: git or hg tags via `tag_filter` / `tag_regex`; `write_to` writes
  the bare version (or `write_template`) into the wheel. [9]
- When: build time. `PDM_BUILD_SCM_VERSION` env or `fallback_version` for
  trees without SCM. [9]
- Gate: not documented; discovery is git's. [9]

### versioneer (historic, still used)

- Reads: `git describe` via subprocess from a vendored `_version.py`;
  falls back to `$Format$` keywords expanded by `git archive`, then to
  the parent directory name (`parentdir_prefix`), then to `0+unknown`.
  Rarely fails hard. [10]
- Gate: looks for `.git` in parent directories, so a subproject "usually
  works", which is the opposite of our need. [10]
- Shape: a single vendored file plus a build-time static rewrite. This is
  the closest existing precedent for "copy one stdlib file into the tree
  and have the build step bake values".

## Git itself

- `git rev-parse --show-toplevel`: "the top-level directory of the
  working tree", error if none. `--show-superproject-working-tree`: the
  superproject root when the current repo is a submodule, else nothing.
  `--is-inside-work-tree`: `true`/`false`. In a linked worktree
  `--show-toplevel` is that worktree's root; `--git-common-dir` is the
  shared `.git`. [11]
- `GIT_CEILING_DIRECTORIES`: "a colon-separated list of absolute paths
  ... that Git should not chdir up into while looking for a repository
  directory". It does not exclude the start directory or a `GIT_DIR` set
  in the environment. An empty entry (`::`) marks later entries as not
  needing symlink resolution. `GIT_DISCOVERY_ACROSS_FILESYSTEM` is the
  other walk bound (default: stop at mount points). [12]
- Implication: setting the ceiling to the parent of the directory we
  expect to be the toplevel turns the post-hoc "is it ours" check into a
  bound git enforces before it ever touches `/opt/homebrew`. The
  `GIT_DIR` caveat matters: pre-commit hooks export `GIT_DIR` and friends,
  which is why `tests/test_foreign_git.py` scrubs them. A facade should
  scrub them in the child environment, not rely on the test fixture.

## Libraries instead of subprocess

| Library | Mechanism | Discovery | Not a repo | Weight |
|---|---|---|---|---|
| GitPython 3.2.1 | shells out to `git`; needs it on PATH; `gitdb`, `smmap` | `Repo(path, search_parent_directories=False)`; the old parent-walk default "is considered a bug" | `InvalidGitRepositoryError` | pure Python, 3 packages, still needs git [13][14] |
| pygit2 1.21.0 | libgit2 bindings | `discover_repository(path, across_fs=False, ceiling_dirs)` returns None when not found | None | 1 to 5 MB compiled wheels; Python >= 3.11 [15][16] |
| dulwich 1.2.21 | pure Python git, optional Rust speedups | `Repo.discover(start)` walks up; raises `NotGitRepository` | exception | pure Python, large surface; Python >= 3.10 [17] |

Observations. GitPython gives nothing over `subprocess` for our four
commands since it needs the same binary. pygit2 is the only one with a
first-class ceiling argument, mirroring git's env var, but at the cost of
a compiled wheel in a `uvx`-installed CLI that declares
`requires-python >= 3.9`. dulwich would let us drop the git binary
requirement, which we do not want: a user without git is the
wheel-install case, and there the baked file is the truth anyway.

## Non-Python comparables

### Go: `-buildvcs` and `debug.ReadBuildInfo`

- Reads at build: `vcs`, `vcs.revision`, `vcs.time`, `vcs.modified`
  stamped into the binary. Reads at runtime: `debug.ReadBuildInfo()`
  returns them from the binary, no VCS tool needed. [18]
- Gate: `-buildvcs=auto` (default) stamps only "if the main package, the
  main module containing it, and the current directory are all in the
  same repository". `-buildvcs=true` errors "if version control
  information is available but cannot be included due to a missing tool
  or ambiguous directory structure". [19][20]
- This is the cleanest statement of our rule: stamp when the artifact
  being built and the repo agree, otherwise stamp nothing, never stamp
  the wrong repo. Go also separates the two halves the way bhs does:
  `hatch_build.py` is the stamp step, `_build_info.py` is the embedded
  record, `ReadBuildInfo` is `build_info()`.

### Rust: `vergen`, `git-version`, cargo metadata

- `vergen-gitcl` runs the git CLI from `build.rs` and emits
  `cargo:rustc-env=VERGEN_GIT_*`, plus `rerun-if-changed` on `.git/HEAD`
  and the current ref. Sibling crates swap the backend (`vergen-git2`,
  `vergen-gix`). `VERGEN_IDEMPOTENT` forces deterministic output;
  `VERGEN_DEFAULT_ON_ERROR` emits the idempotent default when a value
  cannot be generated, with a `cargo:warning` unless `fail_on_error` is
  set. Any pre-set `VERGEN_*` env var wins, the analogue of
  `SETUPTOOLS_SCM_PRETEND_VERSION`. [21][22]
- `git-version` is a proc macro: `git_version!()` runs `git describe
  --always --dirty=-modified` from `CARGO_MANIFEST_DIR` at compile time,
  with `fallback = "..."` or a `cargo_prefix` fallback to
  `CARGO_PKG_VERSION`; otherwise compile error. Discovery is git's walk
  from the manifest dir; no toplevel check. [23][24]
- `[package.metadata]` is "completely ignored by Cargo" and reserved for
  external tools, the manifest-side analogue of `[tool.hatch.build.hooks
  .custom]`. [25]

## What this means for brew-hop-search

### One module

Yes. The five package-side call sites (`_dev_tree_git`, `commit_hash`,
`_commit_count_since_tag` in `__init__.py`; the recent-commits block in
`cli.py`; `_git` + `project_is_git_toplevel` in `hatch_build.py`) run
the same six git commands with the same timeout and the same swallow-all
error policy, and two of them implement the ownership gate twice with
different rules (markers plus `relative_to` in the package; toplevel
equality in the hook). Nothing surveyed has a gate stronger than
setuptools-scm's toplevel-equality check, and that is the one the hook
already uses. Unify on it:

    expected = pkg_dir.parents[1]          # src/brew_hop_search -> root
    env GIT_CEILING_DIRECTORIES=expected.parent
    top = git -C pkg_dir rev-parse --show-toplevel
    ours = top is not None and top == expected

The ceiling makes git stop at `expected` before it can reach
`/opt/homebrew` or `~/src`; the equality check is the belt to that
suspender and is what the tests can fake. Keep the `pyproject.toml` and
`VERSION` marker checks only if you want a third opinion; they add
nothing the equality check does not, and they fail for a renamed
checkout the same way. Under site-packages, `expected` is
`lib/python3.x`, there is no repo at or below it, and the answer is
cleanly None. The module also scrubs `GIT_DIR`, `GIT_WORK_TREE`,
`GIT_INDEX_FILE`, `GIT_PREFIX` from the child env, which is the real fix
for the pre-commit-hook problem the test fixture papers over.

One `run()` seam means `tests/test_foreign_git.py` monkeypatches one
function instead of `subprocess.run` for every module, which is the
B3 (testing conventions) payoff.

### Can `hatch_build.py` import it?

Not with a plain `import brew_hop_search`. Three facts decide it:

1. pyproject-hooks runs the backend as a subprocess with
   `cwd=source_dir` and removes its own script directory from
   `sys.path`; nothing adds the source dir. In-tree backends get a
   meta-path finder for `backend-path` entries only. [26][27] So the
   project root and `src/` are not importable during a `uv build`.
2. The build runs in an isolated environment containing only
   `build-system.requires` (hatchling). The package is not installed.
3. hatchling loads `hatch_build.py` itself with
   `importlib.util.spec_from_file_location(script_name, path)` and
   `exec_module`, without touching `sys.path`. [28]

So do what hatchling does. In the hook:

    spec = importlib.util.spec_from_file_location(
        "_bhs_git", Path(self.root) / "src/brew_hop_search/_git.py")
    git = importlib.util.module_from_spec(spec); spec.loader.exec_module(git)

Conditions this imposes on `_git.py`: stdlib imports only, no relative
imports, no import of `brew_hop_search` itself. The sdist already ships
`src/`, so the wheel-from-sdist step finds the file. `self.root` is "the
root of the project tree" on `BuildHookInterface`. [29] The alternative,
`sys.path.insert(0, root/"src")` then `from brew_hop_search import _git`,
also works but executes the package `__init__` inside the build process
and leaves it in `sys.modules`; prefer the by-path load, which is also
exactly what `test_build_hook_refuses_parent_repo` already does for the
hook. No copy, no vendoring: one file, two loaders.

### External library?

No. The version-from-tags tools (setuptools-scm, hatch-vcs, versioningit,
pdm-backend, uv-dynamic-versioning) solve a different problem: they make
tags the source of truth for the version. bhs deliberately keeps a
`VERSION` file plus a `+N` distance suffix (version-string spec), and
reports facts at runtime for `-VV`, which none of them do. dunamai is the
closest fit and is stdlib-only, but it has no ownership gate at all and
would turn four subprocess calls into a runtime dependency resolved by
every `uvx` run and listed as a resource in the tap formula. GitPython
still needs the git binary; pygit2 is compiled and `>= 3.11`; dulwich is
large and removes a requirement we rely on for the install-source
heuristic. About sixty lines of stdlib, with the one gate the survey
shows nobody else has at runtime, is the right size.

### Spin-off?

Not yet. The seedbed rule asks for independent build/test, external
consumers and a distinct release cadence. Today: tests live in this
suite, the only consumer is this package and its own build hook, and
the module changes when `-V` changes. The versioneer precedent is the
honest one: a single vendored file. If a second Python project of the
owner's wants the same gate, copy `_git.py` into
`~/dev-llm/ClaudeCollab/tools/` as the seed, give it its own test file,
and only then consider `git subtree split`. Record the question in
INTENT.md "parked" rather than in a draft spec.

## Sources

[1] https://setuptools-scm.readthedocs.io/en/latest/config/
[2] https://sources.debian.org/src/setuptools-scm/9.2.2-1/src/setuptools_scm/git.py
    and testing/test_better_root_errors.py (toplevel check, hint text)
[3] https://github.com/pypa/setuptools-scm/pull/1106 (issue #1103)
[4] https://github.com/ofek/hatch-vcs
[5] https://raw.githubusercontent.com/mtkennerly/dunamai/master/dunamai/__init__.py
[6] https://github.com/mtkennerly/dunamai
[7] https://github.com/ninoseki/uv-dynamic-versioning
[8] https://versioningit.readthedocs.io/en/stable/configuration.html
[9] https://backend.pdm-project.org/metadata/
[10] https://github.com/python-versioneer/python-versioneer
[11] https://git-scm.com/docs/git-rev-parse
[12] https://git-scm.com/docs/git (Environment Variables)
[13] https://raw.githubusercontent.com/gitpython-developers/GitPython/main/git/repo/base.py
[14] https://pypi.org/project/GitPython/
[15] https://www.pygit2.org/repository.html
[16] https://pypi.org/project/pygit2/
[17] https://pypi.org/project/dulwich/
[18] https://pkg.go.dev/runtime/debug#ReadBuildInfo
[19] https://pkg.go.dev/cmd/go (Compile packages and dependencies, -buildvcs)
[20] https://go.dev/doc/go1.18 (go version)
[21] https://docs.rs/vergen-gitcl/latest/vergen_gitcl/
[22] https://docs.rs/vergen/latest/vergen/
[23] https://docs.rs/git-version/latest/git_version/
[24] https://raw.githubusercontent.com/fusion-engineering/rust-git-version/master/git-version-macro/src/lib.rs
[25] https://doc.rust-lang.org/cargo/reference/manifest.html
[26] https://raw.githubusercontent.com/pypa/pyproject-hooks/main/src/pyproject_hooks/_impl.py
[27] https://raw.githubusercontent.com/pypa/pyproject-hooks/main/src/pyproject_hooks/_in_process/_in_process.py
[28] https://raw.githubusercontent.com/pypa/hatch/master/backend/src/hatchling/plugin/utils.py
[29] https://raw.githubusercontent.com/pypa/hatch/master/backend/src/hatchling/builders/hooks/plugin/interface.py

Not fetched, stated from memory and hedged accordingly: dulwich
`Repo.discover` semantics (its API page returned 404 today); the exact
body of setuptools-scm's `from_potential_worktree` (the Debian source
page was indexed by search but did not fetch). Both are worth a
one-minute check before the INSPIRATIONS rows land.
