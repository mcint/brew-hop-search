# Design System

Every command is the intersection of:

```
Feature Doc  ×  Input Guide  ×  Output Guide  ×  Envelope Guide
```

The guides are written once and apply everywhere.
A new feature only needs a Feature Doc.

## The Matrix

| Command | Query | Paging | Sources | Formats | Envelope |
|---------|-------|--------|---------|---------|----------|
| search | yes | `-n N+OFF` | `-f -c -i -t -L` | default, `-q`, `-g`, `--json`, `--csv`, `--tsv`, `--table`, `--sql` | yes |
| outdated | no | no | installed vs API | default, `--json`, diff (`--brew-verify`) | yes |
| cache-status | no | no | all | default (compact), `--json` | yes |
| history | name | no | install_log | default, `--json` | yes |
| version | no | no | git, PyPI | default only | no |

## Guides

- **Input Guide** ([INPUT.md](specs/INPUT.md)): query, sources, paging, cache control, env vars
- **Output Guide** ([OUTPUT.md](specs/OUTPUT.md)): verbosity levels, formats, section headers, source tags
- **Envelope Guide** ([ENVELOPE.md](specs/ENVELOPE.md)): JSON structure, meta fields, self-describing output

## Feature Docs

Each in [specs/features/](specs/features/):

- [search.md](specs/features/search.md) — keyword search across sources
- [outdated.md](specs/features/outdated.md) — stale package detection
- [cache-status.md](specs/features/cache-status.md) — cache inspection
- [history.md](specs/features/history.md) — version history for rollback
- [version.md](specs/features/version.md) — tool identity and update check

## Consistency Rules

1. **Verbosity is uniform**: `-q`/default/`-v`/`-vv` mean the same thing everywhere
2. **`--json` is always available** on commands that display structured data
3. **Sources are composable**: flags are additive, filters are restrictive
4. **Duration syntax is shared**: `30m`, `6h`, `1d` — same parser everywhere
5. **Section headers follow one pattern**: `# label (shown/total)  • hint`
6. **Colors map to source type**: green=formula, yellow=cask, magenta=tap, cyan=local

## Spec Lifecycle

Specs can contain **draft sections** marked with `## Draft:` or
`## Future:` headers. These document intended behavior that hasn't
been implemented yet. Drafts should live in the spec they belong to,
not in separate files — this keeps intent next to implementation.

When a draft is implemented, remove the prefix and update the spec
to describe current behavior. Commit the spec change alongside the
code change so they stay in sync.

## Design Principles

- **Offline-first**: Default search never calls `brew`. HTTP or local DB only.
- **Cache is a database**: SQLite + FTS5, queryable, inspectable with `-C`.
- **No write operations upstream**: Read-only tool. No `brew install`, no side effects.
- **Composition over features**: `-q` for fzf, `-g` for awk, `--json` for jq.
- **Progressive disclosure**: Default is clean. Details unlock with `-v`.
