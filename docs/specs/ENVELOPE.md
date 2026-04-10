# JSON Envelope Specification

All `--json` output wraps results in a self-describing `meta` envelope.

## Envelope Structure

```json
{
  "meta": {
    "command": "search",
    "query": "python",
    "sources": ["formula", "cask"],
    "limit": 20,
    "offset": 0,
    "total": 42,
    "count": 20,
    "date": "2026-04-09T14:30:00-07:00"
  },
  "results": {
    "formula": [...],
    "cask": [...]
  }
}
```

## Meta Fields

| Field | When Present | Description |
|-------|-------------|-------------|
| `command` | always | Which mode produced this (`search`, `outdated`, `cache-status`, `history`) |
| `query` | search, history | The search query terms or package name |
| `sources` | search | Data sources searched |
| `limit` | search | Results per section (omitted when unlimited) |
| `offset` | search | Starting position (omitted when 0) |
| `total` | search | Total entries across searched sources |
| `count` | always | Results in this response |
| `mode` | outdated diff | `"diff"` when `--brew-verify` used |
| `date` | always | ISO 8601 timestamp with timezone |

Fields are **omitted** (not null) when they don't apply.

## Per-Command Examples

### Search

```json
{
  "meta": {
    "command": "search",
    "query": "python",
    "sources": ["formula", "cask"],
    "limit": 20,
    "total": 15895,
    "count": 8,
    "date": "2026-04-09T14:30:00-07:00"
  },
  "results": {
    "formula": [{ "name": "python@3.13", ... }],
    "cask": [{ "token": "anaconda", ... }]
  }
}
```

### Outdated

```json
{
  "meta": {
    "command": "outdated",
    "count": 5,
    "date": "2026-04-09T14:30:00-07:00"
  },
  "formulae": [...],
  "casks": [...]
}
```

### Outdated Diff (`--brew-verify`)

```json
{
  "meta": {
    "command": "outdated",
    "count": 5,
    "mode": "diff",
    "date": "2026-04-09T14:30:00-07:00"
  },
  "bhs": { "formulae": [...], "casks": [...] },
  "brew": { "formulae": [...], "casks": [...] }
}
```

### Cache Status

```json
{
  "meta": {
    "command": "cache-status",
    "count": 7,
    "date": "2026-04-09T14:30:00-07:00"
  },
  "cache_dir": "...",
  "db_path": "...",
  "db_exists": true,
  "db_size_bytes": 52428800,
  "sources": { ... }
}
```

### History

```json
{
  "meta": {
    "command": "history",
    "query": "python@3.13",
    "count": 3,
    "date": "2026-04-09T14:30:00-07:00"
  },
  "versions": [
    { "name": "python@3.13", "kind": "formula", "version": "3.13.2", ... }
  ]
}
```

## Design Rule

JSON output alone should reveal: what command ran, what was queried,
how many results exist vs shown, and when the data was fetched.
