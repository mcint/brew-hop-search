<!-- from README.md.template, built with `make readme` -->
# brew-hop-search

Fast offline-first search of Homebrew formulae, casks, taps, and installed packages.

Built on SQLite + FTS5 for instant local search with smart caching.

[GitHub](https://github.com/mcint/brew-hop-search) ·
[PyPI](https://pypi.org/project/brew-hop-search/) ·
[Brew Tap](https://github.com/mcint/homebrew-tap/blob/main/Formula/brew-hop-search.rb)

## Try it

```sh
uvx brew-hop-search python          # nothing to install: runs once from PyPI
```

## Install

```sh
# PyPI (recommended)
uv tool install brew-hop-search     # or: pip install brew-hop-search

# Homebrew tap
brew tap mcint/tap
brew install brew-hop-search
```

Works with Homebrew on macOS and on Linux (Linuxbrew).

## Names

Either install puts the same tool on PATH under three names, and brew
picks up the third as a subcommand:

```sh
brew-hop-search python      # full name
brewhs python               # short alias
brew-hs python              # brew's naming for external commands …
brew hs python              # … so brew runs it as `brew hs`
```

The examples below use the full name; any of these works the same.

## Examples

```sh
brew-hop-search python                 # search formulae + casks (top 20)
brew-hop-search -f python build        # multi-word, formulae only
brew-hop-search '^python' '!@3.9'      # anchored + negated terms (see --help=query)
brew-hop-search 'name:^py' d:build     # scoped: name-prefix + desc term
brew-hop-search -c -i                  # casks, installed only
brew-hop-search -i -n0                 # all installed (-n|--limit: N, 0=all, N+offset for paging)
# BREW_HOP_SEARCH_LIMIT=50 in your shell rc overrides the default 20
brew-hop-search -q python | fzf        # pipe to fzf
brew-hop-search --csv python | qsv sort -s name  # sort CSV
brew-hop-search --sql python | sqlite3 results.db  # import to sqlite
brew-hop-search -O                     # show outdated (local)
brew-hop-search -O --brew-verify       # diff: bhs vs brew
brew-hop-search -H python@3.13         # version history for rollback
brew-hop-search python --refresh       # force re-fetch (--refresh last: it takes a value)
```

## How it works

On first run, fetches Homebrew formula and cask indexes from `formulae.brew.sh` into SQLite with FTS5. Subsequent searches are instant (local DB). Caches older than 6 hours trigger a background refresh on the next run; override with `--stale=DUR` or force immediate with `--refresh`.

| Source | Flag | Data | Calls brew? |
|--------|------|------|-------------|
| Remote API | *(default)* | `formulae.brew.sh` | No |
| Installed | `-i` | `brew info --json=v2 --installed` | Yes |
| Taps | `-t` | `.rb` files in `$(brew --repo)/Library/Taps/` | Yes |
| Local | `-L` | Brew's API cache at `$(brew --cache)/api/` | Yes |
| Outdated | `-O` | Compares installed vs API index | No |
| Outdated | `-O --brew-verify` | Diff bhs vs `brew outdated` | Yes |

## Example output

Default search — clean, human-optimal:
```
  # formulae (5/8733)  • brew install python-argcomplete
    python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/
    python-build  1.6.1  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
    python-freethreading  3.15.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
    python-gdbm@3.11  3.11.18  Python interface to gdbm  │ https://www.python.org/
    python-gdbm@3.12  3.12.16  Python interface to gdbm  │ https://www.python.org/
  # casks (5/7837)  • brew install --cask anaconda
    anaconda  2026.07-1  Distribution of the Python and R programming languages for scientific computing  │ https://www.anaconda.com/
    armory  0.96.5  Python-Based Bitcoin Software  │ https://btcarmory.com/
    chia  2.7.5  GUI Python implementation for the Chia blockchain  │ https://www.chia.net/
    drawbot  3.132  Write Python scripts to generate two-dimensional graphics  │ https://www.drawbot.com/
    pycharm-ce  2025.2.5,252.28238.29  IDE for Python programming - Community Edition  │ https://www.jetbrains.com/pycharm/
```

With `-v` — source tags and cache info:
```
  -- cache: just fetched   searching formula + cask
  # formulae (5/8733)  • brew install python-argcomplete
  f python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/
  f python-build  1.6.1  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
  f python-freethreading  3.15.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
  f python-gdbm@3.11  3.11.18  Python interface to gdbm  │ https://www.python.org/
  f python-gdbm@3.12  3.12.16  Python interface to gdbm  │ https://www.python.org/
  # casks (5/7837)  • brew install --cask anaconda
  c anaconda  2026.07-1  Distribution of the Python and R programming languages for scientific computing  │ https://www.anaconda.com/
  c armory  0.96.5  Python-Based Bitcoin Software  │ https://btcarmory.com/
  c chia  2.7.5  GUI Python implementation for the Chia blockchain  │ https://www.chia.net/
  c drawbot  3.132  Write Python scripts to generate two-dimensional graphics  │ https://www.drawbot.com/
  c pycharm-ce  2025.2.5,252.28238.29  IDE for Python programming - Community Edition  │ https://www.jetbrains.com/pycharm/
  # [time] total 0.045s · cache 0.004s · api(0) —
```

Quiet mode (`-q`) for piping:
```
$ brew-hop-search -q python | fzf
python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/
python-build  1.6.1  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
python-freethreading  3.15.2  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
anaconda  2026.07-1  Distribution of the Python and R programming languages for scientific computing  │ https://www.anaconda.com/
armory  0.96.5  Python-Based Bitcoin Software  │ https://btcarmory.com/
chia  2.7.5  GUI Python implementation for the Chia blockchain  │ https://www.chia.net/
```

## Output formats

### CSV (`--csv`)
```csv
source,name,version,description,homepage
f,python-argcomplete,3.6.3,Tab completion for Python argparse,https://kislyuk.github.io/argcomplete/
f,python-build,1.6.1,"Simple, correct PEP 517 build frontend",https://github.com/pypa/build
f,python-freethreading,3.15.2,"Interpreted, interactive, object-oriented programming language",https://www.python.org/
c,anaconda,2026.07-1,Distribution of the Python and R programming languages for scientific computing,https://www.anaconda.com/
c,armory,0.96.5,Python-Based Bitcoin Software,https://btcarmory.com/
c,chia,2.7.5,GUI Python implementation for the Chia blockchain,https://www.chia.net/
```

### Table (`--table`)
```
S  Name                  Ver                    Description                                         Homepage                              
-  --------------------  ---------------------  --------------------------------------------------  --------------------------------------
f  python-argcomplete    3.6.3                  Tab completion for Python argparse                  https://kislyuk.github.io/argcomplete/
f  python-build          1.6.1                  Simple, correct PEP 517 build frontend              https://github.com/pypa/build         
f  python-freethreading  3.15.2                 Interpreted, interactive, object-oriented program…  https://www.python.org/               
f  python-gdbm@3.11      3.11.18                Python interface to gdbm                            https://www.python.org/               
f  python-gdbm@3.12      3.12.16                Python interface to gdbm                            https://www.python.org/               
c  anaconda              2026.07-1              Distribution of the Python and R programming lang…  https://www.anaconda.com/             
c  armory                0.96.5                 Python-Based Bitcoin Software                       https://btcarmory.com/                
c  chia                  2.7.5                  GUI Python implementation for the Chia blockchain   https://www.chia.net/                 
c  drawbot               3.132                  Write Python scripts to generate two-dimensional …  https://www.drawbot.com/              
c  pycharm-ce            2025.2.5,252.28238.29  IDE for Python programming - Community Edition      https://www.jetbrains.com/pycharm/    
```

Also: `--tsv`, `--json` (full) / `--json=short` (compact rows), `--sql`, `-g` (grep).

## Cache status (`-C`)

```
  db  brew-hop-search/brew-hop-search.db  76.4 MB
  formula      8733    <1m ago  ttl 6h  fts  32MB json
  cask         7837    <1m ago  ttl 6h  fts  20MB json
  installed:f   551  3h38m ago  ttl 1h
  installed:c   100  3h38m ago  ttl 1h
  taps         8648  9h21m ago  ttl 1h
  local:f        41  6d11h ago  ttl 1h
  local:c        11  6d11h ago  ttl 1h
```

## Usage

```
usage: brew-hop-search [-fcitL] [-VCOH] [-gqT|--json[=MODE]|--csv|--tsv|--sql] [-n N[+OFF]] [--refresh[=DUR]] [query ...]

Fast offline-first Homebrew formula/cask search.

positional arguments:
  query                 search terms (AND-matched). Supports ^prefix, suffix$,
                        ^exact$, "quoted phrase", name:/desc: scope, !negate.
                        See --help=query or man page for the full grammar.

sources (composable, default: remote API):
  -f, --formulae, --formula
                        formulae only
  -c, --casks, --cask   casks only
  -i, --installed       installed packages
  -t, --taps            tapped repos
  -L, --local           local API cache (offline)

info:
  -h [MODE]             terse help (or MODE: man, <section>, <flag>)
  --help [MODE]         full help (or MODE: man, <section>, <flag>)
  --man                 offline man page (same as --help=man)
  -V, --version         version (-VV: commits + PyPI)
  -C, --cache-status    cache status
  -O, --outdated        outdated packages (terms filter by name)
  --brew-verify         use brew for -O (slower, authoritative)
  -H, --history         version history for rollback

cache:
  --refresh, --fresh [DUR|KIND[,KIND...]]
                        sync refresh: bare=force, =DUR=if older,
                        =KIND[,KIND...] (kinds:
                        index,installed,outdated,taps,local,all). --fresh is
                        an alias
  --stale [DUR]         background refresh threshold (default: 6h,
                        $BREW_HOP_SEARCH_STALE_API to override)

output:
  -g, --grep            tab-separated for piping
  -q, --quiet           results only (for grep/fzf)
  --json [MODE]         JSON output; MODE=full (default) or short (compact row
                        fields)
  --csv                 CSV output
  --tsv                 tab-separated with header
  -T, --table           aligned columns (like sqlite3 -column)
  --sql                 SQLite INSERT statements
  --multi, --long       multi-line per-result with labeled fields
  -n, --limit N[+OFF]   max results [+offset], 0=all (default: 20, or
                        $BREW_HOP_SEARCH_LIMIT)
  -v, --verbose         source tags, cache info (-vv per-source detail)
  --no-timing           suppress the `# [time]` footer
                        ($BREW_HOP_SEARCH_NO_TIMING also works)
```

### Direct DB access

The SQLite database is at `~/.cache/brew-hop-search/brew-hop-search.db`:

```sh
sqlite-utils tables ~/.cache/brew-hop-search/brew-hop-search.db
sqlite-utils search ~/.cache/brew-hop-search/brew-hop-search.db formula python
```

## Docs

- [Design System](docs/DESIGN-SYSTEM.md) — cartesian spec architecture
- [Specs](docs/specs/) — INPUT, OUTPUT, ENVELOPE, SCHEMA, per-feature
- [Comparables](docs/COMPARABLES.md) — Python project references
- [Least Surprise](docs/LEAST-SURPRISE.md) — operational principles
- [Man page](docs/brew-hop-search.1.md) — full reference

## Version

```
brew-hop-search 0.3.8-dev+23
```

## License

[MPL-2.0](LICENSE) — file-level copyleft. Fixes to covered files come
back as MPL; new files and downstream projects can pick their own
license.
