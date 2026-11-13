---
title: Testing
date: 2026-11-12
kind: guide
tldr: >
  make test runs pytest over tests/. Tests never call brew, never hit the
  network, and never touch ~/.cache: the DB is redirected with
  BREW_HOP_SEARCH_DB, git and PyPI are faked at subprocess.run and urlopen.
  Random order and pytest-xdist -n auto both work, with one known order
  dependency in the build-info tests that this doc names. New feature, new
  test, red first.
---

# Testing

## Run

```sh
make test                        # uv run python -m pytest tests/ -x -q
uv run python -m pytest tests/ -vv -k fmt   # show expected output inline
UPDATE_SNAPSHOTS=1 make test     # rewrite snapshot files on purpose
```

Optional, not in the `dev` group yet:

```sh
uv run --with pytest-randomly python -m pytest tests/ -p randomly
uv run --with pytest-xdist    python -m pytest tests/ -n auto
```

## Layout

- `tests/test_*.py`: one file per surface (cli, output, outdated, config,
  timing, version, taps, cache flow, refresh dispatch, history, defaults).
- `tests/snap.py`: the `snap` fixture. `snap.assert_match(text)` compares
  against `tests/snapshots/<test_name>.txt`. A missing file is written and
  the test passes; that first run is the "red" of red-green. Set
  `UPDATE_SNAPSHOTS=1` to rewrite. Review `git diff tests/snapshots/`.
- `tests/conftest.py`: at `-vv`, prints each test's expected output after
  it runs, so the suite doubles as usage examples.
- CLI tests run `python -m brew_hop_search.cli` in a subprocess and strip
  ANSI and the version suffix before comparing.

## Isolation rules

1. **No real database.** Any test that opens the cache sets
   `BREW_HOP_SEARCH_DB` to a file under `tmp_path`, via `monkeypatch.setenv`
   in-process or `env=` for subprocess tests. `cache.effective_db_path()`
   reads the variable at call time, so this always wins.
2. **No `brew`.** Tests never spawn it. Dispatch tests replace each
   `sources.<kind>.ensure_cache` with a recorder; CLI tests seed the DB so
   the background refresh has nothing to do.
3. **No network.** `version_check.urlopen` is replaced with a fake that
   returns a canned PyPI body. The background check is also gated by a
   timestamp in the test DB.
4. **No live git facts.** `subprocess.run` is replaced where a test needs
   git absent; `_build_info` is faked through `sys.modules`.
5. **Patch through `monkeypatch` or a `with patch(...)` block.** Never
   assign to a module attribute directly. See `MONKEYPATCHING.md`.

## What resets between tests, and what does not

Resets automatically:

- Everything set through `monkeypatch` or `unittest.mock.patch`, in LIFO
  order, when the test ends.
- `tmp_path` contents (pytest keeps the last three sessions).
- `timing._records`, by an autouse fixture local to `test_timing.py`.
- `tests/snap.py`'s expect stash, drained by conftest after each test.

Does not reset:

- `display.USE_COLOR` / `USE_COLOR_STDERR` and `defaults.STALE_*` are
  computed at import. They are constants for the whole process; tests patch
  the name, never the input that fed it.
- `cache`'s pending-refresh list: `test_register_pending_refresh_visible`
  appends and leaves its entry. It diffs before/after, so it is harmless,
  but a later test that asserts the list is empty would fail.
- The package attribute `brew_hop_search._build_info`, once the real
  submodule has been imported. See the known issue below.
- Snapshot files, by design.

## Random order and parallel runs: verdict

Probed 2026-11-12 (`docs/research/2026-11-12-test-isolation-probe.md` has the numbers). 190 tests.

- Plain: 8.4 s. Two `pytest-randomly` seeds: same result as plain.
- `-n auto` (10 workers): 3.0 s, same result as plain.
- `-n auto` plus random seed 7: one additional failure.

The probe ran against the pre-#4 tests. It found one order dependency
and one constant failure, both in `tests/test_version.py`, both with the
same root cause: `from brew_hop_search import _build_info` reads the
*package attribute* before `sys.modules`, so a `sys.modules` fake is
ignored once the real submodule has been imported, and a
`builtins.__import__` hook keyed on the submodule name never fires
because a from-import passes the package name. PR #4 fixes both: every
`sys.modules` patch of `_build_info` is paired with
`monkeypatch.delattr(brew_hop_search, "_build_info", raising=False)`, and
the "no build info" case sets `sys.modules[...] = None` so the import
raises the way the import system does.

With #4 merged the suite is order- and parallel-safe, and `-n auto` can go
into `make test` (add `pytest-xdist` to the `dev` group) once a run with
`-p randomly` on the merged tree confirms it. Until that run, use `-n auto`
for local speed and keep CI serial.

## Adding a test

1. Write the test first. For output, use `snap`; the first run writes the
   file and is your red. For logic, use a plain assert that fails.
2. Isolate: `BREW_HOP_SEARCH_DB` to `tmp_path` if the cache is touched;
   fake `subprocess.run` or `urlopen` if the code path reaches them.
3. Patch only at the seams listed above. If the test needs a deeper patch,
   add a parameter to the function instead.
4. Run `make test`, then once with `-p randomly` if you touched module
   state. Commit the snapshot with the code.
