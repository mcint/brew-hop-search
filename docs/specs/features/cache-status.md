# cache-status

Inspect the local cache: database size, per-source age, FTS readiness.

## Purpose

Diagnostic tool for understanding cache state. Answer: "Is my
index fresh? How big is it? Is FTS working?"

## Input

- **flag**: `-C` / `--cache-status`
- **format**: `--json`

No query, no paging, no source flags.

## Output

### Default

```
  db  brew-hop-search/brew-hop-search.db  61.5 MB
  brew  7.0.1
  formula    8306  1h12m ago  ttl 6h        fts  30MB json
  cask       7596  1h12m ago  ttl 6h        fts  14MB json
  installed:f     460  1h11m ago  ttl 1h
  installed:c      84  1h11m ago  ttl 1h
  taps             49     41m ago  ttl 1h
  local:f         160  1d23h ago  ttl 1h
  local:c          59  1d23h ago  ttl 1h
```

Compact: one line per source. DB path and size on first line, then the
detected Homebrew version (`unknown` when `brew` is not on PATH).
Per-source: label, entry count (right-aligned), age, **ttl** (threshold
beyond which the source will be background-refreshed on next read), FTS
status, JSON file size.

The brew version is cached in `_meta` (kind `brew_version`, 6h TTL) so
`brew --version` isn't shelled out on every run. `-C --refresh` re-probes.
`$BREW_HOP_SEARCH_BREW_VERSION=6.1.0` overrides detection (test hook, same
layering as `STALE_*`). See `brewver.py`.

### `-v`: ttl source layer + gated features

Shows where each TTL came from (`default`, `env`), and one line per
version-gated brew feature with the minimum version when unavailable:

```
  brew  6.1.0
    ✓ tap-info-trusted
    ✗ vulns  needs 7.0.0
  formula    8306  1h12m ago  ttl 6h (default)        fts  30MB json
  installed:f  460  1h11m ago  ttl 2s (env: BREW_HOP_SEARCH_STALE_INSTALLED)
```

Features that a command skips because brew is too old are reported at
the end of that command's run (`skipped <feature>: needs brew X, have Y`),
never silently dropped.

### `-vv`: next-refresh ETA

Adds `fresh for <duration>` (or `stale` if already past):

```
  formula    8306  1h12m ago  ttl 6h (default)  fresh for 4h47m  fts  30MB json
  installed:f  460  3h ago    ttl 1h (default)  stale
```

### JSON

```json
{
  "cache_dir": "...",
  "db_path": "...",
  "db_exists": true,
  "db_size_bytes": 52658176,
  "brew": {
    "version": "7.0.1",
    "features": { "tap-info-trusted": true, "vulns": true, "doctor-json": true }
  },
  "sources": {
    "formula": { "count": 8307, "age_seconds": 7200.0, "updated_at": 1712000000, "fts": true },
    "cask": { "count": 7589, "age_seconds": 7200.0, "updated_at": 1712000000, "fts": true }
  }
}
```

## Data Sources

Reads `_meta` table for timestamps and counts.
Checks filesystem for raw JSON files and DB size.
No network access.

## Cache Behavior

Read-only inspection. Does not trigger refresh.

## Examples

```sh
brew-hop-search -C                  # human-readable status
brew-hop-search -C --json           # for monitoring scripts
brew-hop-search -C --json | jq '.sources.formula.age_seconds'
```
