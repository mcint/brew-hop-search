# Database Schema

Schema version: **1** (brew-hop-search 0.3.0, 2026-04-09)

All tables live in a single SQLite database at
`~/.cache/brew-hop-search/brew-hop-search.db`.

## Core Tables

### `_meta` — per-source metadata

Tracks when each source was last refreshed and how many entries it had.

```sql
CREATE TABLE [_meta] (
   [kind] TEXT PRIMARY KEY,    -- source identifier (e.g. "formula", "installed_cask")
   [updated_at] FLOAT,        -- unix timestamp of last refresh
   [count] INTEGER,            -- entry count at last refresh
   [value] TEXT                -- optional scalar payload (added lazily via alter)
);
```

Known `kind` values: `formula`, `cask`, `installed_formula`, `installed_cask`,
`tap`, `local_formula`, `local_cask`, `version_check`, `brew_version`.

`brew_version` is a scalar row: `value` holds the detected `brew --version`
(e.g. `7.0.1`), `count` is 0, `updated_at` drives a 6h TTL. The `value`
column is added on first write (`alter=True`), so older databases upgrade
in place.

### `formula` — remote API formulae

```sql
CREATE TABLE [formula] (
   [name] TEXT PRIMARY KEY,
   [desc] TEXT,
   [homepage] TEXT,
   [version] TEXT,
   [raw] TEXT                  -- full JSON from formulae.brew.sh
);
```

FTS5: `formula_fts` on `(name, desc)`, porter tokenizer.

### `cask` — remote API casks

```sql
CREATE TABLE [cask] (
   [token] TEXT PRIMARY KEY,
   [name] TEXT,
   [desc] TEXT,
   [homepage] TEXT,
   [version] TEXT,
   [raw] TEXT                  -- full JSON from formulae.brew.sh
);
```

FTS5: `cask_fts` on `(token, name, desc)`, porter tokenizer.

### `installed_formula` / `installed_cask`

Same schema as `formula`/`cask`. Populated from `brew info --json=v2 --installed`.

```sql
CREATE TABLE [installed_formula] (
   [name] TEXT PRIMARY KEY,
   [desc] TEXT,
   [homepage] TEXT,
   [version] TEXT,
   [raw] TEXT                  -- full brew info JSON
);
```

FTS5: `installed_formula_fts` on `(name, desc)`, porter tokenizer.
`installed_cask` uses `token` as PK, FTS on `(token, name, desc)`.

### `tap` — tapped repos

```sql
CREATE TABLE [tap] (
   [slug] TEXT PRIMARY KEY,    -- "user/tap/kind/name"
   [name] TEXT,
   [tap] TEXT,                 -- "user/tap"
   [desc] TEXT,
   [homepage] TEXT,
   [version] TEXT,
   [added_at] FLOAT,          -- file birthtime (macOS) or mtime
   [modified_at] FLOAT,       -- file mtime
   [trusted] INTEGER,         -- 0/1 from `brew tap-info` (brew ≥ 6.0); NULL = unknown
   [official] INTEGER,        -- 0/1 Homebrew-owned tap; NULL = unknown
   [raw] TEXT                 -- scanned item incl. trusted/official (display reads raw)
);
```

FTS5: `tap_fts` on `(name, tap, desc)`, porter tokenizer.

`trusted` / `official` come from `brew tap-info --installed --json=v1`,
gated by `brewver.supports("tap-info-trusted")` (min 6.0.0). On older
brew, or when tap-info fails, both are NULL for every row — "unknown",
which display renders as nothing, distinct from 0 ("untrusted").

Note: `added_at` and `modified_at` are new in schema v1. Older databases
without these columns will still work — display code handles missing fields.

### `local_formula` / `local_cask`

Same schema as `formula`/`cask`. Populated from brew's local API cache files.

### `install_log` — version history (append-only)

```sql
CREATE TABLE [install_log] (
   [name] TEXT,
   [kind] TEXT,                -- "formula" or "cask"
   [version] TEXT,
   [brew_commit] TEXT,         -- short hash from homebrew-core
   [recorded_at] FLOAT,       -- unix timestamp when recorded
   PRIMARY KEY ([name], [kind], [version])
);
```

Append-only: entries are never deleted. New versions are inserted on
each `-i` refresh when the installed version changes.

## FTS5 Tables

Each content table has a corresponding FTS5 virtual table:

| FTS Table | Content Table | Indexed Columns | Tokenizer |
|-----------|--------------|-----------------|-----------|
| `formula_fts` | `formula` | name, desc | porter |
| `cask_fts` | `cask` | token, name, desc | porter |
| `installed_formula_fts` | `installed_formula` | name, desc | porter |
| `installed_cask_fts` | `installed_cask` | token, name, desc | porter |
| `tap_fts` | `tap` | name, tap, desc | porter |
| `local_formula_fts` | `local_formula` | name, desc | porter |
| `local_cask_fts` | `local_cask` | token, name, desc | porter |

FTS tables are rebuilt (dropped + recreated) on every source refresh.
Auto-update triggers keep FTS in sync between refreshes.

## Schema Evolution Rules

1. **Tables are dropped and recreated on refresh** — no ALTER TABLE needed
   for column changes to source tables. Just update the code and refresh.
2. **`_meta` is upserted** — new `kind` values appear automatically.
3. **`install_log` is append-only** — never drop this table. New columns
   should use ALTER TABLE ADD COLUMN with defaults.
4. **`raw` column is the safety net** — all upstream JSON is preserved.
   If we need a field we didn't extract, it's in `raw`.
5. **Missing columns are OK** — display code uses `.get()` with defaults.
   An older database missing `added_at` on `tap` will simply not show dates.

## Cache Files

In addition to the database, raw JSON files are stored:

| File | Source | Purpose |
|------|--------|---------|
| `formula.json` | formulae.brew.sh | Raw API response backup |
| `cask.json` | formulae.brew.sh | Raw API response backup |

These enable re-indexing without re-fetching. They are written atomically
(temp file + rename).

## Database Location

- Default: `~/.cache/brew-hop-search/brew-hop-search.db`
- Override: `BREW_HOP_SEARCH_DB` environment variable

The cache directory is created on first use. The entire database can be
deleted and rebuilt from scratch with `--refresh`.
