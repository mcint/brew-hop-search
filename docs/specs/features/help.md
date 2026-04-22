# help

Layered help: terse synopsis, full argparse help, scoped section/flag help,
contextual "you passed these flags" explanations, and a first-class man page.

## Purpose

`-h` ≠ `--help`. Users who type `-h` at an unfamiliar CLI want a short,
scannable answer; users who type `--help` want the full option table.
Both accept `=MODE` for scoped help, both reuse the argparse parser as the
source of truth, and `-h` is context-aware: if it's passed alongside other
flags, it explains those flags instead of reprinting generic examples.

## Modes

| Invocation                   | Output                                                                                  |
|------------------------------|-----------------------------------------------------------------------------------------|
| `-h`                         | Terse: usage, `--help` pointer, description, quick examples, info line, more-help block |
| `-h <flag> [<flag>...]`      | Contextual: echoes `parsed:` + one line per flag with its argparse help text            |
| `--help`                     | Full argparse help (standard `ap.print_help()`)                                         |
| `-h=MODE` / `--help=MODE`    | Scoped help (flag or section — see below)                                               |
| `--man` / `-h=man` / `--help=man` | Man page via `$PAGER`                                                              |

Resolution for `=MODE`: flag letter → flag long name → section title →
error with `did-you-mean`.

## Terse `-h`

```
  usage: brew-hop-search [-fcitL] [-VCOH] [...] [query ...]
         brew-hop-search --help      (for full help)
  Fast offline-first Homebrew formula/cask search.

  quick examples:
    brew-hop-search python               # formulae + casks (top 20)
    brew-hop-search python -n 50         # top 50; -n 0 = all, -n 20+20 = page 2
    brew-hop-search -i                   # installed packages
    brew-hop-search -O                   # outdated
    brew-hop-search -q foo | fzf        # pipe to fzf

  info:    -C cache status  ·  -V version  ·  -VV verbose & latest

  more help:
    --help=<section>      e.g. --help=sources, --help=output
    --help=<flag>          e.g. --help=-c, --help=outdated
    --man                  offline man page
```

The second line aligns `brew-hop-search --help` under the program name in
the usage line so the two forms read as siblings.

## Contextual `-h <flag>...`

Triggered when `-h` appears in argv alongside any flag-like token
(starting with `-`). The shared header is printed, then:

```
  parsed: -O -f

    -O, --outdated             outdated packages
    -f, --formulae, --formula  formulae only

  more help:
    --help=<section>      e.g. --help=sources, --help=output
    --man                  offline man page
```

Resolution:
- Exact match against any argparse action's `option_strings`
- `--long=value` → `--long`
- `-xVALUE` (e.g. `-n0`) and repeated short flags (e.g. `-VV`) → `-x` / `-V`
- Unknown tokens render as `<tok>  (unknown flag)` — no parse errors

Order matches the order tokens appeared in argv. Works with `-O -h` (flag
before `-h`) as well as `-h -O`.

## Scoped `=MODE`

Section names come from argparse group titles: `sources`, `output`,
`cache`, `info`, `positional`, `options`. Flag lookup matches any
option-string (e.g. `-c`, `--cask`) or dest (`casks`, `outdated`).

## Man page

Shipped inside the wheel at `src/brew_hop_search/data/brew-hop-search.1`
(groff) and `.1.md` (markdown fallback). `shared-data` in pyproject places
the `.1` at `{prefix}/share/man/man1/` so Homebrew picks it up via
MANPATH; `--man` handles everyone else.

Rendering order:
1. `man -l <path>` if `man` is on PATH and the `.1` exists
2. `.md` piped through `$MANPAGER` / `$PAGER` / `less -R` if TTY
3. Raw to stdout if not a TTY

## Testing

Snapshot tests in `tests/snapshots/` cover each help mode:

| Test                                | Scenario                       |
|-------------------------------------|--------------------------------|
| `test_help`                         | `--help` (full argparse)       |
| `test_help_terse`                   | bare `-h`                      |
| `test_help_scoped_section`          | `--help=sources`               |
| `test_help_scoped_flag`             | `--help=outdated`              |
| `test_help_contextual_single`       | `-h -O`                        |
| `test_help_contextual_multi`        | `-h -c -i`                     |
| `test_help_contextual_value_attached` | `-h -n0` (stripped suffix)   |
| `test_help_contextual_flag_after_others` | `-O -h`                    |
| `test_help_h_equals_mode`           | `-h=man` normalization         |
| `test_man_flag`                     | `--man` prefix                 |

Any change to help output requires regenerating with
`UPDATE_SNAPSHOTS=1 make test` and reviewing the diff in
`tests/snapshots/` before committing.

## Examples

```sh
brew-hop-search -h                 # terse
brew-hop-search -h -O -f           # contextual: explain -O and -f
brew-hop-search -O -h              # same; order-independent
brew-hop-search --help             # full options
brew-hop-search --help=sources     # section scoped
brew-hop-search --help=-c          # flag scoped
brew-hop-search --man              # man page
```
