# outdated

Detect packages where the installed version differs from the current index version.

## Purpose

Quick local outdated check without calling `brew outdated` (which is
slow and requires network). Optional `--brew-verify` for authoritative results.

## Input

- **flag**: `-O` / `--outdated`
- **source filter**: `-f` / `--formulae`, `-c` / `--casks` (compose; neither = both)
- **verbosity**: `-q`, `-v`, `-vv` (see OUTPUT.md levels; semantics below)
- **format**: `-g`, `--json[=MODE]`, `--csv`, `--tsv`, `-T`/`--table`, `--sql`
- **authority**: `--brew-verify` (use brew subprocess instead of local comparison)

No query, no paging.

### Source filter behavior

`-f` and `-c` filter *which kinds* the comparison emits, not the comparison
inputs themselves. The comparison still runs on both sides — only output is
scoped. Section headers and counts reflect the filter.

| Flags       | Shown                              |
|-------------|------------------------------------|
| `-O`        | outdated formulae + outdated casks |
| `-O -f`     | outdated formulae only             |
| `-O -c`     | outdated casks only                |
| `-O -f -c`  | both (equivalent to `-O`)          |

In `--brew-verify` diff mode, filtering applies to both `bhs` and `brew`
sides uniformly.

## Output

### Verbosity levels

| Level | Flag | Outdated behavior |
|-------|------|-------------------|
| 0 | `-q` | No section headers, no progress, no footer hints. One result per line, no indent, no color. Empty when nothing outdated (exit 0). |
| 1 | *(default)* | Section headers, per-item lines, footer hints. Progress status lines on stderr during comparison. |
| 2 | `-v` | Adds source summary header: `-- comparing installed:f (460) vs formula (8314) index`. Source indicator column (`f`/`c`) on each row. |
| 3 | `-vv` | Adds per-entry raw details: revision number, pin state, auto_updates flag, installed-array length when >1. |

Format flags bypass verbosity (same rule as search).

### Default (level 1)

```
  # outdated formulae (3)
    python@3.13  3.13.1 → 3.13.2
    node  21.6.0 → 21.6.1  [pinned]

  # outdated casks (1)
    firefox  121.0 → 122.0

  -- brew upgrade • brew pin <name> • -H <name> for history
```

- Section headers per included kind (respects `-f`/`-c`)
- Per-item: name, installed version → current version
- Tags: `[pinned]`, `[keg-only]` (formulae), `[auto-updates]` (casks)
- Footer hints only at level >= 1

### Quiet (`-q`)

One result per line, tab-separated, no headers:

```
python@3.13	3.13.1	3.13.2	
node	21.6.0	21.6.1	pinned
firefox	121.0	122.0	
```

Columns: `name<TAB>installed<TAB>current<TAB>tags` (tags comma-joined, empty if none).
Formulae and casks are interleaved in section order (formulae first, then casks).

### Grep (`-g` / `--grep`)

Same columns as `-q` but prefixed with the source indicator, matching the
search `-g` convention:

```
f	python@3.13	3.13.1	3.13.2	
f	node	21.6.0	21.6.1	pinned
c	firefox	121.0	122.0	
```

Columns: `source<TAB>name<TAB>installed<TAB>current<TAB>tags`

### JSON

```json
{
  "meta": { "mode": "outdated", "count": 4, ... },
  "data": {
    "outdated_formulae": [
      { "name": "python@3.13", "installed_versions": ["3.13.1"], "current_version": "3.13.2", "pinned": false }
    ],
    "outdated_casks": [
      { "name": "firefox", "installed_versions": ["121.0"], "current_version": "122.0", "auto_updates": false }
    ]
  }
}
```

`--json=short` emits compact rows with the `-g` column set per item.

### CSV / TSV

Header row + one row per result, columns match `-g`:

```csv
source,name,installed,current,tags
f,python@3.13,3.13.1,3.13.2,
f,node,21.6.0,21.6.1,pinned
c,firefox,121.0,122.0,
```

`installed` is the first installed version; see `installed_versions` in JSON
for the full list when multiple are present.

### Table (`-T` / `--table`)

Aligned columns, same column set as CSV/TSV. Like `sqlite3 -column`.

### SQL (`--sql`)

`INSERT` statements into two tables:

```sql
CREATE TABLE IF NOT EXISTS outdated_formula (name TEXT, installed TEXT, current TEXT, pinned INTEGER, keg_only INTEGER);
CREATE TABLE IF NOT EXISTS outdated_cask    (name TEXT, installed TEXT, current TEXT, auto_updates INTEGER);
INSERT INTO outdated_formula VALUES ('python@3.13', '3.13.1', '3.13.2', 0, 0);
INSERT INTO outdated_cask    VALUES ('firefox', '121.0', '122.0', 0);
```

Kind-specific tables preserve the typed flags (`pinned`, `keg_only`,
`auto_updates`) rather than flattening them into a `tags` string.

### Format priority

Same as search: `json > csv > tsv > table > sql > grep > default`.

## Comparison Logic

### Fast Mode (default)

Compares installed index (`-i` cache) against API index:

- **Formulae**: Compare `version` + `_revision` from raw JSON
- **Casks**: Compare `version` string directly
- **Excluded**: Casks with `version "latest"`
- **Invisible**: Tap-only formulae not in the main API index

### Authoritative Mode / Diff (`--brew-verify`)

When `--brew-verify` is used, **both** fast and brew are run, and the
output is a package-matched diff showing where they agree and disagree.

```
  # outdated formulae (5)  ~3 +1 -1
  ~ python@3.13  3.13.1 → 3.13.2
  ~ node  21.6.0 → 21.6.1  [pinned]
  ~ wget  1.24.4 → 1.24.5_1|1.24.5  [keg-only]
  + tap-only-pkg  1.0 → 1.1  [brew-only]
  - false-positive  2.0 → 2.1  [bhs-only]
```

**Diff prefixes**:
- `~` both agree the package is outdated (version may differ in detail)
- `+` only brew found it outdated (bhs missed — tap-only, bottle rebuild, etc.)
- `-` only bhs found it outdated (brew disagrees — likely a false positive)

**Version word-diff**: When both report a package as outdated but with
different target versions, both are shown: `bhs_ver|brew_ver`

### JSON with diff

```json
{
  "bhs": { "formulae": [...], "casks": [...] },
  "brew": { "formulae": [...], "casks": [...] }
}
```

## Data Sources

- Installed index: `installed_formula`, `installed_cask` tables
- API index: `formula`, `cask` tables (raw JSON for version comparison)
- Brew subprocess: `brew outdated --json=v2` (only with `--brew-verify`)

## Cache Behavior

Ensures both installed and API caches exist before comparing.
No dedicated cache — piggybacks on existing source caches.

## Examples

```sh
brew-hop-search -O                     # fast local outdated
brew-hop-search -O --brew-verify       # diff: fast vs brew
brew-hop-search -O --json              # for scripts
brew-hop-search -O --brew-verify --json  # both results as JSON
brew-hop-search -O --json | jq '.outdated_formulae | length'
```
