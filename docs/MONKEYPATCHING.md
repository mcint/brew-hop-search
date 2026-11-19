---
title: Monkeypatching in the test suite
date: 2026-11-12
kind: convention
tldr: >
  We patch at the process edge only: environment variables, subprocess.run,
  urlopen, and sys.modules for build info. We do not patch our own internals
  below the public function a test exercises. Every patch goes through the
  pytest monkeypatch fixture or a with-block of unittest.mock.patch, so it is
  undone when the test ends. Watch import-time constants and from-imports;
  those are the two ways a patch silently misses.
---

# Monkeypatching in the test suite

A monkeypatch swaps one name for another for the length of a test. It is
the cheapest seam there is, and also the easiest to misuse. This page says
what we patch, what we do not, where it bites, and how other communities
think about the same trade.

## 1. Norms: what we patch

The suite has four kinds of seam. Each maps to a real boundary of the
program: something outside the Python process that a test must not touch.

| Seam | How | Why it is a boundary |
|---|---|---|
| Environment | `monkeypatch.setenv` / `delenv` on `BREW_HOP_SEARCH_*` | Config input; the program reads it, never writes it |
| Child processes | `monkeypatch.setattr(subprocess, "run", fake)` | `git` and `brew` are not ours and may be absent |
| Network | `monkeypatch.setattr(version_check, "urlopen", fake)` | PyPI is not ours and must not be hit from tests |
| Build artefact | `monkeypatch.setitem(sys.modules, "brew_hop_search._build_info", fake)` | The baked module exists only in a wheel |

Two further patches sit just inside the boundary and are tolerated because
they stand in for a terminal or a data source, not for logic:

- `sys.stderr.isatty` (timing footer policy) and `display.USE_COLOR_STDERR`
  (colour policy). Both are "is a human watching" facts about the process.
- `sources.<kind>.ensure_cache`, `search.search`, `sources.taps._taps_dir`.
  These replace a whole data source with a recorder so a dispatch test can
  check which sources were asked to refresh. They are one call deep from
  `cli.main` and are the public entry of each source module.

Patching the rendered version (`__version__`, `_commit_count_since_tag`,
`install_source`) in `tests/test_version.py` is the same pattern: each is
the public fact one layer below `version_info()`, and the test pins how the
string is composed from those facts.

## 2. What we do not patch

- Private helpers two or more layers below the function under test. If a
  test needs that, the function wants a parameter instead.
- Dotted paths into other packages (`sqlite_utils.Database.insert`). Use
  `BREW_HOP_SEARCH_DB` and a `tmp_path` file; SQLite is fast enough.
- Builtins. `test_commit_count_zero_when_no_git_no_build_info` patches
  `builtins.__import__` to simulate a missing `_build_info`. It is the one
  exception and is scoped to a single name check. pytest's own docs say
  builtins patching is "not recommended"; do not add a second one.
- Anything from a module-level fixture with `autouse=True` that reaches
  across files. `test_timing.py` has an autouse reset, but it is local to
  that file and resets our own recorder, not a patch.

## 3. Limits and warnings

**Undo is per test, LIFO.** `monkeypatch` records every change and undoes
them all after the requesting test or fixture finishes. `unittest.mock.patch`
as a `with` block undoes on exit. Neither survives the test, so nothing we
patch leaks into the next test by design. State we *mutate* without a patch
(a list, a file) does leak; see TESTING.md.

**Import-time constants do not see a patch.** `display.USE_COLOR` and
`USE_COLOR_STDERR` are computed once at import from `isatty()`. Setting the
env or patching `sys.stdout.isatty` afterwards changes nothing; patch the
constant itself, as `test_cache_flow.py` does. `defaults.STALE_*` are the
same shape: they read `BREW_HOP_SEARCH_STALE_*` at import. Tests therefore
call the `stale_*_seconds()` functions, not the constants.

**`from x import y` binds at import.** `version_check` does
`from urllib.request import urlopen`, so the test must patch
`version_check.urlopen`, not `urllib.request.urlopen`. The rule is to patch
where the name is looked up, not where it is defined. The reverse holds
for `subprocess`: `__init__.py` does `import subprocess` inside the function
and calls `subprocess.run`, so the module attribute is the right target.
That patch is process-wide for the test, which is why it is paired with a
function that raises immediately.

**The fromlist gotcha.** `from brew_hop_search import _build_info` does not
consult `sys.modules` first. The import system fetches the package, then
does `getattr(package, "_build_info")`, and only falls back to
`sys.modules["brew_hop_search._build_info"]` when that attribute is absent.
Once the real submodule has been imported anywhere in the process, the
package carries the attribute, and a `sys.modules` patch alone is ignored.
An earlier revision of `test_version.py` paired every `setitem` with
`monkeypatch.delattr(brew_hop_search, "_build_info", raising=False)` for
this reason. If a build-info test starts reading the real module after a
refactor, this is the first thing to check.

**Patching a shared stdlib object is global.** `sys.stderr.isatty` and
`subprocess.run` are visible to every frame, including pytest's own. Keep
such patches to tests that return quickly and never patch `open`, `print`,
or `compile`.

## 4. Indications and contraindications

Patch when the thing replaced is:

- an environment variable or config file path;
- a clock, a TTY check, or another "where am I running" fact;
- a network call, where the fake returns a canned body;
- a child process (`git`, `brew`), where the fake returns a `CompletedProcess`
  or raises `OSError`;
- a module that only exists in a built artefact (`_build_info`).

Do not patch when:

- the target is your own helper and the test is about logic above it; pass
  the value in, or test the helper directly;
- the path has more than one dot past the module (`a.b.c.d`); that is the
  test knowing the implementation's shape;
- you would need three fakes to make one call succeed (Hynek's "drowning
  in boilerplate" test); write a thin adapter and fake that;
- the real thing is cheap and deterministic (SQLite in `tmp_path`, a dict);
- the patch has to be `autouse` across files to keep the suite green; that
  is shared state wearing a costume.

## 5. Diversity of thought

Positions differ on *how much* to double, but agree on *where*: at a
boundary you understand, with a fake that behaves like the real thing.

**Python.**
- pytest's monkeypatch page: undo happens after the requesting test; prefer
  patching the reference your code uses; for code you control, "a safer
  long-term pattern is to make dependencies explicit".
  https://docs.pytest.org/en/stable/how-to/monkeypatch.html
- `unittest.mock`: "patch where an object is looked up, which is not
  necessarily the same place as where it is defined"; `autospec=True` makes
  a mock fail "in the same way as your production code" on a bad call.
  https://docs.python.org/3/library/unittest.mock.html
- pytest-mock's `mocker` is the same `mock.patch` as a fixture, with call
  assertions and spies; use it when you need to assert *how* a seam was
  called, `monkeypatch` when you only need to swap a value.
  https://pypi.org/project/pytest-mock/
- Hynek Schlawack, "Don't Mock What You Don't Own in 5 Minutes": mock your
  own adapter, not the third-party client; he uses `pretend` stubs and
  verified fakes rather than classic mocks. "In the end, it's less of a
  rule and more of a heuristic."
  https://hynek.me/articles/what-to-mock-in-5-mins/
- Ned Batchelder, "Why your mock breaks later": a `builtins.open` patch
  broke coverage.py under Python 3.14. "Mock where the object is used, not
  where it's defined." Also "Stop mocking, start testing" (2012): if you
  need a mock, have exactly one well-tested one.
  https://nedbatchelder.com/blog/202511/why_your_mock_breaks_later.html
  https://nedbatchelder.com/blog/201206/tldw_stop_mocking_start_testing
- Hypothesis has no mocking stance as such; its stateful testing runs the
  real implementation against a plain model and compares. MacIver: property
  testing "is intrinsically black box". Treat that as the far end of the
  "use the real thing" spectrum.
  https://hypothesis.readthedocs.io/en/latest/stateful.html

**Not Python.**
- Freeman and Pryce, *Growing Object-Oriented Software* ch. 8, "Only Mock
  Types That You Own". Gojko Adzic's refinement: "only mock types that you
  understand". Pryce: the exception is "constructing a non-trivial adapter
  around that type".
  https://groups.google.com/g/growing-object-oriented-software/c/NvmAOBVlC4A
- Martin Fowler, "Mocks Aren't Stubs": dummy / fake / stub / spy / mock;
  state verification vs behaviour verification; mockist tests couple to
  implementation and "interfere with refactoring".
  https://martinfowler.com/articles/mocksArentStubs.html
- Sandi Metz, "The Magic Tricks of Testing": assert results of incoming
  queries, side effects of incoming commands; mock outgoing commands; do not
  test outgoing queries at all.
  https://speakerdeck.com/skmetz/magic-tricks-of-testing-railsconf
- Go: small interfaces, hand-written fakes, and a conformance test for the
  fake. `testing/fstest.MapFS` is "a simple in-memory file system for use in
  tests"; `fstest.TestFS` checks any `fs.FS` behaves correctly. No patching
  exists in the language, so the seam must be a parameter.
  https://pkg.go.dev/testing/fstest
- Rust: traits plus injection, either generic or `dyn`. Hand-written fakes
  for simple traits; `mockall` generates expectation mocks when call order
  matters. Forum advice for HTTP: point the client at a local server rather
  than mock the client.
  https://blog.logrocket.com/mocking-rust-mockall-alternatives
  https://users.rust-lang.org/t/what-is-the-ideomatic-way-to-abstract-dependencies-for-unit-testing-dependency-injection/135081
- Ruby RSpec verifying doubles (`instance_double`): "a stricter alternative
  to normal doubles" that checks the stubbed method exists and the arity
  matches, so the double cannot drift from the class. Python's `autospec`
  is the same idea.
  https://rspec.info/features/3-12/rspec-mocks/verifying-doubles/
- Enterprise Craftsmanship, on GOOS: mocks are justified only where the
  system talks to the outside; "the communication pattern only becomes part
  of API when it crosses the boundary of the system".
  https://enterprisecraftsmanship.com/posts/growing-object-oriented-software-guided-by-tests-without-mocks/

Where this suite sits: closest to Fowler's classicist and the Go view. Real
SQLite, real argparse, real rendering; fakes only for env, process, network
and build artefact. The dispatch recorders in `test_refresh_dispatch.py`
are the one behaviour-verification spot, and they sit on the seam that
Metz would call an outgoing command.

## 6. Naming

`MONKEYPATCHING.md` says what the page is about. If the owner wants the
title to carry the stance rather than the mechanism, two candidates:

- `SEAMS.md`: what the program's test seams are, and that a seam is a
  boundary, not an attribute path.
- `TEST-DOUBLES.md`: covers fakes and recorders as well as patches, which
  is what the suite actually uses.
