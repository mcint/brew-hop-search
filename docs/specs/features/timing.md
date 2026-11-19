---
title: The time footer — total · cache · api(n) · refresh
date: 2026-11-13
kind: feature-spec
tldr: >
  One stderr line at the end of every command says how long the whole run
  took (from the package's first import), how much of it was the local
  database, how many foreground HTTP requests were made and how long they
  took, and whether a background refresh was started or finished. It
  replaces the v1 footer that measured main() only and once printed 0.134s
  beside a shell `time` of 2.7s. What the process cannot see (brew's own
  bootstrap when run as `brew hs`) is named here, not hidden.
---

# The time footer

```
# [time] total 0.129s · cache 0.037s · api(0) —
# [time] total 3.321s · cache 0.512s · api(1) 2.503s · refresh bg
# [time] total 2.410s · cache 0.090s · api(0) — · refresh 1.9s
```

## Terms

| term | meaning | source |
|---|---|---|
| `total` | wall clock from the package's first import to the footer. Covers imports, argument parsing, the work, output, and the grace poll for a background refresh. Excludes interpreter boot (about 10 ms) and anything before exec. | `brew_hop_search._T0`, a `monotonic()` taken at the top of `__init__.py`; `timing.process_start()` |
| `cache` | summed time inside the local SQLite queries that produced the results | `Timer("cache")` around each `search()` call |
| `api(n)` | n = foreground HTTP requests made this run; the time is their sum. `api(0) —` when none. Background refreshes do not count here. | `timing.record_api()` in `sources.api.fetch` and `version_check.fetch_latest` |
| `refresh` | `bg` when a background refresh was started and left running; `N.Ns` when the grace poll saw it finish (the slowest kind's duration); absent when none was started | `cache.register_pending_refresh` sets `bg`; `display.trailing_refresh_status` upgrades it |

Separators are middle dots, like the rest of the `# [...]` family. Seconds
print with three decimals under ten seconds (`_fmt_secs`).

## Policy

Unchanged from v1 (`timing.should_emit`): shown on a TTY stderr by default
and always at `-v`; suppressed by `-q`, `--no-timing`,
`BREW_HOP_SEARCH_NO_TIMING`, help and version paths, and the background
refresh subprocess. Machine formats never see it (stderr), and their
envelopes do not yet carry it (see Open).

## What is not measured, said plainly

- **`brew` bootstrap.** `brew hs …` and `brew hop-search …` run Homebrew's
  Ruby before our process exists: 0.2 to 0.4 s warm, seconds cold. A shell
  `time` includes it; `total` cannot. The 2026-11-12 report (`0.134s`
  footer, `2.736 total`, 21 % CPU) was a cold brew bootstrap.
- **Interpreter boot** before the first import, about 10 ms.
- **Teardown** after the footer, milliseconds.

## Why the import instant and not process start

The true process start is not portable without a dependency; the import
timestamp is within about 10 ms of it on every platform we ship to. Honest
enough, and stated.

## Tests

`tests/test_timing_footer.py`: the three line shapes; counters feed
`summary()`; `reset()` clears everything; `process_start()` predates now;
`emit_footer` uses the recorded counters. `tests/test_timing.py` keeps the
policy table and the format helpers.

## Open

- A `timing` object in the `--json` envelope with the same keys. The
  footer is computed after output is written, so `total` would be partial
  there; decide whether partial is acceptable or the envelope gets only
  `cache` and `api`.
- Under `-v`, name the brew bootstrap when launched by brew. Detecting
  "launched by brew" reliably (not just `HOMEBREW_PREFIX` in the env) is
  the open question.
- Per-source breakdown (`installed:f 0.012s`) under `-v`, as
  `docs/specs/drafts/timing.md` sketched.
