# Input Specification

How brew-hop-search accepts queries, paging, cache control,
and source selection.

## Query

```
brew-hop-search [query ...]
```

- Space-separated terms, AND-matched (all must hit)
- Matched against name and description via FTS5 with porter stemming
- Prefix matching: `pyth` matches `python`
- No query + no source flag = show help hints
- No query + source flag (e.g. `-i`) = list all from that source

## Sources

Sources are composable and additive. Default (no flags): remote API.

| Flag | Source | Tables | Subprocess |
|------|--------|--------|------------|
| *(default)* | formulae.brew.sh | `formula`, `cask` | none |
| `-f` | filter: formulae only | (filters kind) | — |
| `-c` | filter: casks only | (filters kind) | — |
| `-i` | installed packages | `installed_formula`, `installed_cask` | `brew info --json=v2 --installed` |
| `-t` | tapped repos | `tap` | `brew --repository` + .rb scan |
| `-l` | brew's local API cache | `local_formula`, `local_cask` | `brew --cache` |

`-f` and `-c` are **filters** (restrict which kinds appear).
`-i`, `-t`, `-l` are **sources** (select where data comes from).
Combine freely: `-i -f` = installed formulae only.

## Paging

```
-n N[+OFF]
```

| Form | Meaning |
|------|---------|
| `-n 10` | 10 results, offset 0 |
| `-n 10+20` | 10 results, starting at position 20 |
| `-n +40` | default 20 results, starting at 40 |
| `-n 0` | unlimited (all results) |

Default: 20 results, offset 0.

Truncation detection: internally fetches `limit + 1` to know
whether more results exist. Section header shows `shown/total`.

## Cache Control

| Flag | Behavior |
|------|----------|
| *(default)* | Use cache if present; background refresh if older than `--stale` threshold |
| `--refresh` | Force immediate synchronous re-fetch |
| `--refresh=DUR` | Synchronous refresh only if cache older than DUR |
| `--stale DUR` | Background refresh threshold for every source touched (defaults: index 6h, installed/taps/local 1h) |
| `--stale KIND:DUR[,KIND:DUR]` | Per-source threshold; kinds `index installed taps local all`, short `x i t l` |
| `--offline` | No network, no refresh, no subprocess; every selected source must already be cached (else exit 1). Conflicts with `--refresh`. |

Background refresh spawns a detached subprocess that updates the
cache without blocking the current search.

`--offline` is an **adverb**: it composes with any source (`-i --offline`,
`-t --offline`, default api tables). `-l` is a **source** (brew's own
on-disk API cache); the two are correlated but distinct — see
`drafts/cli-vocabulary.md` § Problem 1.

### Duration Syntax

Durations accept `s`, `m`, `h`, `d` units, combinable:

```
30m    6h    1d    1h30m    3600
```

Plain integers are treated as seconds.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `BREW_HOP_SEARCH_DB` | Override database path |
| `BREW_HOP_SEARCH_UA` | Override User-Agent string |
