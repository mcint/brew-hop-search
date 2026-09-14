# search

Search Homebrew formulae, casks, taps, and installed packages by keyword.

## Purpose

Find packages by name or description. Default mode — what runs when
you type `brew-hop-search python`.

## Input

- **query**: Space-separated terms (AND-matched, all must hit). See
  [Query Syntax](#query-syntax) for anchors, field scoping, phrases.
- **sources**: `-f`, `-c`, `-i`, `-t`, `-l` (composable)
- **paging**: `-n N[+OFF]` (default: 20)
- **cache control**: `--refresh[=DUR]` (alias: `--fresh`), `--stale DUR`
- **format**: `-q`, `-g`, `--json`, `--csv`, `--tsv`, `--table`, `--sql`, `--multi` (alias `--long`), `-v`, `-vv`

## Query Syntax

Each whitespace-separated token is a **term**; every term must match (AND).
A term has the shape `[field:][!][^]pattern[$]`:

| Form            | Meaning                                                   |
|-----------------|-----------------------------------------------------------|
| `foo`           | substring match in name OR description (default scope)    |
| `^foo`          | name/desc starts with `foo`                               |
| `foo$`          | name/desc ends with `foo`                                 |
| `^foo$`         | exact equality                                            |
| `"foo bar"`     | literal substring including whitespace (quoted)           |
| `name:foo`      | substring in name only (alias: `n:`)                      |
| `desc:foo`      | substring in description only (aliases: `d:`, `description:`) |
| `!foo`          | negate: no match may contain `foo`                        |
| `name:^py`      | prefix, scoped to name                                    |
| `!desc:"old "`  | negate a scoped phrase                                    |

Combining rules:

- `^` / `$` bind to the pattern; place them inside quotes is fine
  (`"^foo"` = anchor, same as `^foo`).
- Field prefix, negation, and anchors compose in any visual order but parse
  as `field:` → `!` → `^pattern$` (canonical).
- Matching is case-insensitive.
- Multiple terms AND together; there is no OR operator in v1.
- No regex support in v1; `/…/` is treated as a literal substring. (Tracked
  as a future extension — see draft in `docs/specs/drafts/search-syntax.md`.)
- To search for a literal `^`, `$`, or leading `!`, quote the term and the
  anchors become part of the pattern only when *not* at start/end: `'py^3'`.

Field scoping for non-formula sources:

| Source         | `name:` matches against     | `desc:` matches against |
|----------------|-----------------------------|-------------------------|
| formula        | `name`                      | `desc`                  |
| cask           | `token` OR `name` (array)   | `desc`                  |
| tap            | `tap` OR `name`             | `desc`                  |
| installed_*    | same as their non-installed counterparts |           |

## Output

### Default (verbosity 1)

```
  # formulae (3/8307)  • brew install python@3.13
    python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
    python-build  1.4.2  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
```

- Section header per source kind
- 4-space indent, no source tag
- Name (bold, colored by source), version (dim), description, homepage (dim, after `│`)

### Verbose (verbosity 2, `-v`)

```
  -- cache: 2h old   searching formula + cask
  # formulae (3/8307)  • brew install python@3.13
  f python@3.13  3.13.2  ...
```

- Cache age + source summary header
- Source indicator column: `f`/`c`/`t`/`i`

### Quiet (verbosity 0, `-q`)

```
python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
```

- No headers, no indent, no source tags

### Grep (`-g`)

```
python@3.13	3.13.2	https://www.python.org/
  Interpreted, interactive, object-oriented programming language
```

- Tab-separated: slug, version, URL
- Description on next line, indented

### JSON (`--json`)

Raw JSON array (single source) or object keyed by source kind.
See [ENVELOPE.md](../ENVELOPE.md) for structure.

### CSV (`--csv`)

```csv
source,name,version,description,homepage
f,python@3.13,3.13.2,"Interpreted, interactive, object-oriented programming language",https://www.python.org/
```

Standard CSV with header row. Pipes to `qsv`, spreadsheets, pandas.

### TSV (`--tsv`)

```
source	name	version	description	homepage
f	python@3.13	3.13.2	Interpreted, interactive...	https://www.python.org/
```

Tab-separated with header row. Pipes to `awk`, `cut`, `sort`.

### Table (`--table`)

```
S  Name         Ver     Description                     Homepage
-  -----------  ------  ------------------------------  -------------------------
f  python@3.13  3.13.2  Interpreted, interactive, ob…   https://www.python.org/
```

Aligned columns like `sqlite3 -column`. Description capped at 50 chars, homepage at 40.

### SQL (`--sql`)

```sql
CREATE TABLE IF NOT EXISTS results (...);
INSERT INTO results VALUES ('f', 'python@3.13', '3.13.2', '...', '...');
```

SQLite INSERT statements. Pipe to `sqlite3` to build a queryable local table.

### Multi-line (`--multi` / `--long`)

```
formula  python@3.13
  version  3.13.2
  desc     Interpreted, interactive, object-oriented programming language
  url      https://www.python.org/

formula  node
  version  21.6.1
  ...
```

One stanza per result, labeled fields, blank line between. Reads
naturally for one-or-two-result lookups; pipes through `grep -A` cleanly.

## Data Sources

| Source | Table | Primary Key | FTS Columns |
|--------|-------|-------------|-------------|
| Remote API | `formula` | `name` | `name`, `desc` |
| Remote API | `cask` | `token` | `token`, `name`, `desc` |
| Installed | `installed_formula` | `name` | `name`, `desc` |
| Installed | `installed_cask` | `token` | `token`, `name`, `desc` |
| Taps | `tap` | `slug` | `name`, `tap`, `desc` | + `added_at`, `modified_at` |
| Local | `local_formula` | `name` | `name`, `desc` |
| Local | `local_cask` | `token` | `token`, `name`, `desc` |

## Search Algorithm

1. **Parse**: Query string → list of `Term(field, negate, anchor_start,
   anchor_end, literal)`. Shlex-style quoting preserves whitespace.
2. **FTS pass**: Build FTS5 query from the *unanchored*, *non-negated*,
   *non-phrase* tokens as `"term"* AND …`; fetch up to 200 candidates.
   Anchored/phrase/negated/field-scoped terms do not narrow the pre-filter —
   they run in the post-filter.
3. **Fallback**: If no FTS table, full table scan.
4. **Post-filter**: Each candidate must satisfy every term's predicate
   (field, anchor mode, literal, negation). Negated terms disqualify;
   non-negated terms that don't match disqualify.
5. **Scoring**: Per-term additive, on the matched side of the pair:
   - Exact equality (effective `^foo$`): +100
   - Prefix (`^foo`): +60
   - Suffix (`foo$`): +40
   - Substring in name: +30
   - Substring in description: +10
   - Negated terms contribute 0 (already gated by step 4)
6. **Sort**: Score descending, then name ascending.
7. **Slice**: Apply offset and limit.

## Output Format Default

The default output format (when no CLI format flag is passed) follows
the precedence:

    config.toml  →  $BREW_HOP_SEARCH_FORMAT  →  CLI flag

Each layer overrides the previous. If none is set, the human-readable
TTY default is used.

```toml
# ~/.config/brew-hop-search/config.toml
[output]
default = "multi"   # any of: default, multi/long, json, json:short,
                    #         csv, tsv, table, sql, grep, quiet
```

```sh
BREW_HOP_SEARCH_FORMAT=json bhs python    # session override
bhs --csv python                          # one-shot override
```

Override the config path with `$BREW_HOP_SEARCH_CONFIG` (mainly for
tests).

## Cache Behavior

- **Default TTL**: Background refresh if older than 6h (`--stale`)
- **Force**: `--refresh` fetches synchronously
- **Conditional**: `--refresh=1h` fetches only if older than 1h
- **Background**: Spawns detached subprocess, non-blocking

## Examples

```sh
brew-hop-search python              # formulae + casks
brew-hop-search -f python build     # multi-word, formulae only
brew-hop-search -i                  # list all installed
brew-hop-search -i -c               # installed casks only
brew-hop-search -q python | fzf     # pipe to fzf
brew-hop-search -n 5+20 python      # 5 results starting at position 20
brew-hop-search --json python | jq  # structured output
brew-hop-search --csv python | qsv sort -s name  # sort by name
brew-hop-search --tsv python | sort -t$'\t' -k3  # sort by version
brew-hop-search --table python      # aligned columns
brew-hop-search --sql python | sqlite3 results.db  # import to sqlite
brew-hop-search '^python'           # names starting with python
brew-hop-search '^python$'          # exact name python
brew-hop-search 'name:^py' desc:build  # scoped: name prefix + desc term
brew-hop-search '"machine learning"'   # literal phrase with whitespace
brew-hop-search '^py' '!@3.9'       # starts with py, exclude 3.9 variant
```
