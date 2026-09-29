# Output Specification

Verbosity controls how much context surrounds search results.
The default is tuned for human reading; flags shift toward
machine-ready (quieter) or diagnostic (louder) output.

## Verbosity Levels

| Level | Flag | Alias | Description |
|-------|------|-------|-------------|
| 0 | `-q` / `--quiet` | `--verbose=0` | Machine-ready: bare results, no headers, no source tags, no separators. Suitable for `grep`, `fzf`, scripts. |
| 1 | *(default)* | `--verbose=1` | Human-optimal: section headers with counts + install hint, 2-space indent, `│` homepage separator. No source indicator column. Small hint line when no query. On a TTY, a stderr `# [cache] … [--refresh]` reminder line (age, time left, `changed`; see features/cache-flow.md § Reminder line). |
| 2 | `-v` | `--verbose=2` | Adds: source indicator column (`f`/`c`/`t`/`i`), cache age + source summary line. The reminder line is printed even off-TTY. |
| 3 | `-vv` | `--verbose=3` | Adds: per-source search stats (entry count, cache age per table). |

`-v` stacks: bare `-v` = level 2, `-vv` = level 3.
`--verbose=N` sets the level explicitly (0-3).
`-q` is shorthand for `--verbose=0`.

When both `-q` and `-v` appear, `-q` wins (level 0).

## Default Output (Level 1)

```
  # formulae (3/8307)  • brew install python@3.13
    python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
    python-build  1.4.2  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
    python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/

  # casks (2/7589)  • brew install --cask anaconda
    anaconda  2025.12  Distribution of Python and R for scientific computing  │ https://www.anaconda.com/
    pycharm  2025.1  IDE for Python  │ https://www.jetbrains.com/pycharm/
```

No source indicator prefix — the section header already identifies the source.

## Verbose Output (Level 2, `-v`)

```
  -- cache: 2h old   searching formula + cask

  # formulae (3/8307)  • brew install python@3.13
  f python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
  f python-build  1.4.2  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build

  # casks (2/7589)  • brew install --cask anaconda
  c anaconda  2025.12  Distribution of Python and R for scientific computing  │ https://www.anaconda.com/
```

Source indicator column (`f`/`c`/`t`/`i`) appears, colored on TTY.
Cache age + source summary header shown.

## Quiet Output (Level 0, `-q`)

```
python@3.13  3.13.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
python-build  1.4.2  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
anaconda  2025.12  Distribution of Python and R for scientific computing  │ https://www.anaconda.com/
```

No headers, no indent, no source tags. One result per line.

## Format Flags

Format flags bypass verbosity — they have their own layout:

| Flag | Format | Use Case |
|------|--------|----------|
| `-g` / `--grep` | Tab-separated: `slug\tversion\turl` + desc | Piping to `awk`/`cut` |
| `--json` | Raw JSON | Scripting, jq, machine consumption |
| `--csv` | CSV with header | Spreadsheets, qsv, pandas |
| `--tsv` | TSV with header | `sort`, `awk`, `cut` |
| `--table` | Aligned columns | Human reading (like `sqlite3 -column`) |
| `--sql` | SQLite INSERT statements | `sqlite3 results.db` import |

**Priority**: When multiple format flags are given, first match wins:
`json > csv > tsv > table > sql > grep > default`

All tabular formats use the same column set:
`source`, `name`, `version`, `description`, `homepage`

## Source Indicator Column

Single-char prefix identifying the data source:

| Char | Source | Color |
|------|--------|-------|
| `f` | formula | green |
| `c` | cask | yellow |
| `t` | tap | magenta |
| `i` | installed | green (formula) / yellow (cask) |
| `f` | local formula | cyan |
| `c` | local cask | cyan |

Only shown at verbosity >= 2 (`-v`).

## Section Headers

```
  # label (shown/total)  • brew install <name>
```

- `#` prefix (dimmed)
- Count: `shown/total` when results are truncated, else just `shown`
- Install hint derived from first result
- Only shown at verbosity >= 1 (default and above)

## No-Results Message

At verbosity >= 1: `  no results for 'query'`
At verbosity 0 (`-q`): no output, exit 0.
