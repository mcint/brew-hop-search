---
title: Test-suite probe, order and parallel safety
date: 2026-11-12
kind: probe
tldr: >
  190 tests. Plain run 8.4 s, 1 failure; two random seeds, same 1 failure;
  xdist -n auto 3.0 s, same 1 failure; xdist plus random seed 7, 2 failures.
  The extra failure is a real order dependency between the two build-info
  tests in tests/test_version.py, caused by the from-import package
  attribute shortcut. The constant failure is a WIP test bug, not order.
  Everything else is order- and parallel-safe.
---

# Test-suite probe, 2026-11-12

Worktree probed, read-only:
`/Users/steward/dev-llm/brew-hop-search/.claude/worktrees/release`
(branch `fix/version-reporting`, checkout commit `47a4b17`, with an
uncommitted edit to `tests/test_version.py` dated 12:51 today). The
worktree was being edited by another session during this probe; at one
point `tests/test_foreign_git.py` and `tests/test_version_ahead.py` were
present and then gone. The md5 list below pins what was actually run.
Python 3.12.14 via `uv run`.

Raw log: `raw-runs.txt` beside this file. Driver: `probe.sh`.

## Runs

| # | Invocation | Result | Wall |
|---|---|---|---|
| 1 | `pytest tests/ -q` | 189 passed, 1 failed | 9.1 s (8.42 s in pytest) |
| 2 | `-p randomly --randomly-seed=1` | 189 passed, 1 failed | 9.4 s |
| 3 | `-p randomly --randomly-seed=20261112` | 189 passed, 1 failed | 8.5 s |
| 4 | `-n auto` (pytest-xdist, 10 workers) | 189 passed, 1 failed | 3.8 s (3.01 s) |
| 5 | `-n auto -p randomly --randomly-seed=7` | 188 passed, 2 failed | 3.1 s |

All runs used `-p no:cacheprovider` so nothing was written under the repo.
Snapshot files were not rewritten: every file under `tests/snapshots/` kept
its checkout mtime (`Nov 8 13:39:39`), and `tests/*.py` md5s were identical
before and after.

## Failure A: constant, in every run

`tests/test_version.py::test_commit_count_zero_when_no_git_no_build_info`
`assert 27 == 0`

Not an order problem. The test patches `builtins.__import__` to raise
`ImportError` when `name == "brew_hop_search._build_info"`. The code under
test does `from brew_hop_search import _build_info`, which calls
`__import__("brew_hop_search", ..., fromlist=("_build_info",))`. The name
the hook sees is the package, not the submodule, so the hook never fires
and the real module loads from disk. That file exists in a dev tree:
`uv run` triggers the hatch build hook, which writes
`src/brew_hop_search/_build_info.py` (gitignored) with
`BUILD_COMMIT_COUNT = 27` for this checkout. The test is the uncommitted
WIP edit; the earlier committed revision used
`monkeypatch.setitem(sys.modules, ..., None)` plus
`monkeypatch.delattr(brew_hop_search, "_build_info", raising=False)`.

## Failure B: order dependent, surfaced by run 5

`tests/test_version.py::test_commit_count_falls_back_to_build_info`
`assert 27 == 42`, on worker `gw8`, the same worker that ran failure A.

Confirmed by hand with fixed ordering (`-p no:randomly`, test ids on the
command line):

| Order | Result |
|---|---|
| fallback, then zero | fallback passes, zero fails (A) |
| zero, then fallback | both fail |

Mechanism: `from brew_hop_search import _build_info` first tries
`getattr(brew_hop_search, "_build_info")` and only falls back to
`sys.modules` when the attribute is missing. The first import of the real
submodule anywhere in the process sets that package attribute. After that,
a `monkeypatch.setitem(sys.modules, "brew_hop_search._build_info", fake)`
is ignored. The fallback test only wins when it is the first thing in its
process to import `_build_info`. In the plain run it is; under xdist plus
shuffling it was not. Any test that calls `build_info()` or `commit_hash()`
with git disabled would poison it the same way.

Fix is the one the earlier revision had: pair every `sys.modules` patch of
`_build_info` with `monkeypatch.delattr(brew_hop_search, "_build_info",
raising=False)`. Both undo automatically.

## Everything else

188 tests passed in all five orderings and across 10 workers. No shared
`tmp_path`, no snapshot writes, no DB collisions. Each DB-touching test
sets `BREW_HOP_SEARCH_DB` to a file under its own `tmp_path`. Subprocess
tests in `test_cli.py` pass `env=` with the same override, except the
`--help` and `-h` snapshot tests, which do not open the DB.

## Monkeypatch inventory (tests/*.py, state as probed)

| Target kind | Count | Where |
|---|---|---|
| env var (`setenv`/`delenv`, `BREW_HOP_SEARCH_*`) | 33 | timing 11, refresh_dispatch 8, config 7, defaults 4, history 1, taps 1, version 1 |
| own module attribute | 15 | refresh_dispatch 8 (`sources.*.ensure_cache`, `search.search`), taps 4 (`_taps_dir`), cache_flow 2 (`USE_COLOR_STDERR`), version 1 (`version_check.urlopen`, the only network seam) |
| `unittest.mock.patch` on own package names | 15 | version (`__version__`, `_commit_count_since_tag`, `install_source`) |
| stdlib object attribute (`sys.stderr.isatty`) | 11 | timing |
| `subprocess.run` (stdlib module attribute) | 2 | version |
| `sys.modules` item (`setitem`/`delitem`) | 2 | version (`_build_info`) |
| `builtins.__import__` | 1 | version |

Counts are grep hits on `monkeypatch.` and `patch(` lines, not tests. The
backlog's numbers for `test_foreign_git` (15) and `test_version_ahead` (8)
are for files not present in the checkout at probe time.

## Shared state found in `src/`

- `timing._records`: module list, cleared by an autouse fixture local to
  `test_timing.py`. Nothing else appends to it during tests.
- `display.USE_COLOR`, `USE_COLOR_STDERR`: import-time `isatty()` results.
  Patched directly where a test needs colour on or off.
- `defaults.STALE_*`: import-time reads of env. Tests call the functions.
- `cache.DB_PATH` is a constant but every caller goes through
  `effective_db_path()`, which reads `BREW_HOP_SEARCH_DB` at call time.
- `cache` pending-refresh list: `test_register_pending_refresh_visible`
  appends and does not remove; it snapshots the list before and diffs, so
  it is order-safe, but the entry survives the test.
- `brew_hop_search._build_info` package attribute: the leak described in
  Failure B.
- `tests/snap.py` `_current_expects`: module list drained by conftest after
  every test; per-process under xdist.
