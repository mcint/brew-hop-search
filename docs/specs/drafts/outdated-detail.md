# `-O` verbosity detail: date at `-v`, commit at `-vv` (draft)

## Purpose
Make `brew-hop-search -O -v` and `-O -vv` more useful for incident
triage and accounting. Add a date column at `-v`, commit-hash detail at
`-vv`. Landing as a separate patch bump (user-visible change).

## Design

### `-O -v` — add the install date

One column, placed right after the installed-version string:

```
  # outdated formulae (3)
  f python@3.13  3.13.1 (2026-03-12) → 3.13.2
  f node         21.6.0 (2026-02-04) → 21.6.1  [pinned]
  c firefox     121.0  (2026-01-28) → 122.0
```

Source: the `time` field inside `raw.installed[0]` in
`installed_formula` / `installed_cask` (brew records epoch seconds at
install time). Format: ISO date (`YYYY-MM-DD`), no hours — install-day
precision is the useful grain.

Missing `time`: render as `----------` to keep alignment.

In diff mode (`--brew-verify`), the date comes from bhs's side; brew's
output doesn't include install date.

### `-O -vv` — add the source commit

One additional line per entry, dimmed, indented:

```
  f python@3.13  3.13.1 (2026-03-12) → 3.13.2
      tap: homebrew/core@abc123d  bottle: arm64_sequoia  revision: 0
```

Fields pulled from `raw.tap`, `raw.installed[0].used_options`,
`raw.installed[0].poured_from_bottle`, `raw.revision`. Only show fields
that are non-empty; skip the whole line if all are empty.

Rationale: for triaging "why does bhs think X is outdated" or "which
bottle am I running," commit + tap + revision are what you reach for.

### Machine formats

The `-v` date and `-vv` commit extend the column set for all tabular
outputs:

| Format | `-v` adds | `-vv` adds |
|--------|-----------|------------|
| `-g`, `--csv`, `--tsv`, `-T` | `installed_at` (ISO date) | `tap`, `revision`, `bottle_id` |
| `--json[=short]` | `installed_at` field per entry | `tap`, `revision`, `bottle_id` fields |
| `--sql` | `installed_at TEXT` column | `tap TEXT`, `revision INTEGER`, `bottle_id TEXT` |

Schema stability: these fields are additive. Consumers that drive off
the column positions should be tolerant, but the column order is now
locked.

## Tests

Per the TDD norm, each of these gets a new snapshot test before
implementation:

- `test_outdated_verbose_date` — `-O -v` output includes ISO dates
  (mask dates in `run()` similarly to version masking).
- `test_outdated_vv_commit` — `-O -vv` output includes tap + revision
  line.
- `test_outdated_csv_verbose` — CSV header contains `installed_at`.
- `test_outdated_sql_vv` — SQL schema contains `tap TEXT`.

Date masking: extend the harness to replace `\d{4}-\d{2}-\d{2}` →
`YYYY-MM-DD` so real install dates don't churn snapshots.

## Patch bump

Lands as 0.3.4 (or whichever is next after the current in-flight 0.3.3).
Mention in the release notes: `-O -v` now shows install dates; `-O -vv`
adds tap/revision/bottle detail.

## Related

- `docs/specs/features/outdated.md` — gets the final column tables
  appended when this ships.
- `claude-collab/help-ux.md` — the "versioned help, consistent across
  output modes" ethos this extends.
