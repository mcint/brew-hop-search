<!-- from README.md.template, built with `make readme` -->
# brew-hop-search

Fast offline-first search of Homebrew formulae, casks, taps, and installed packages.

Built on SQLite + FTS5 for instant local search with smart caching.

[GitHub](https://github.com/mcint/brew-hop-search) ·
[PyPI](https://pypi.org/project/brew-hop-search/) ·
[Brew Tap](https://github.com/mcint/homebrew-brew-hop-search/blob/main/Formula/brew-hop-search.rb)

## Install

```sh
# PyPI (recommended)
uv tool install brew-hop-search     # or: pip install brew-hop-search
uvx brew-hop-search python          # one-shot without install

# Homebrew tap
brew tap mcint/brew-hop-search
brew install brew-hop-search
```

## Examples

```sh
brew-hop-search python                 # search formulae + casks
brew-hop-search -f python build        # multi-word, formulae only
brew-hop-search -i                     # list all installed
brew-hop-search -i -c                  # installed casks only
brew-hop-search -q python | fzf        # pipe to fzf
brew-hop-search --csv python | qsv sort -s name  # sort CSV
brew-hop-search --sql python | sqlite3 results.db  # import to sqlite
brew-hop-search -O                     # show outdated (local)
brew-hop-search -O --brew-verify       # diff: bhs vs brew
brew-hop-search -H python@3.13         # version history for rollback
brew-hop-search --refresh python       # force re-fetch
```

## How it works

On first run, fetches Homebrew formula and cask indexes from `formulae.brew.sh` into SQLite with FTS5. Subsequent searches are instant (local DB). Stale caches trigger background refresh.

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
  # formulae (5/8314)  • brew install python-argcomplete
    python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/
    python-build  1.4.3  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
    python-freethreading  3.14.4  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
    python-gdbm@3.11  3.11.15  Python interface to gdbm  │ https://www.python.org/
    python-gdbm@3.12  3.12.13  Python interface to gdbm  │ https://www.python.org/
  # casks (5/7627)  • brew install --cask anaconda
    anaconda  2025.12-2  Distribution of the Python and R programming languages for scientific computing  │ https://www.anaconda.com/
    armory  0.96.5  Python-Based Bitcoin Software  │ https://btcarmory.com/
    chia  2.7.0  GUI Python implementation for the Chia blockchain  │ https://www.chia.net/
    drawbot  3.132  Write Python scripts to generate two-dimensional graphics  │ https://www.drawbot.com/
    pycharm-ce  2025.2.5,252.28238.29  IDE for Python programming - Community Edition  │ https://www.jetbrains.com/pycharm/
```

With `-v` — source tags and cache info:
```
  -- cache: 2d23h old   searching formula + cask
  # formulae (5/8314)  • brew install python-argcomplete
  f python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/
  f python-build  1.4.3  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
  f python-freethreading  3.14.4  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
  f python-gdbm@3.11  3.11.15  Python interface to gdbm  │ https://www.python.org/
  f python-gdbm@3.12  3.12.13  Python interface to gdbm  │ https://www.python.org/
  # casks (5/7627)  • brew install --cask anaconda
  c anaconda  2025.12-2  Distribution of the Python and R programming languages for scientific computing  │ https://www.anaconda.com/
  c armory  0.96.5  Python-Based Bitcoin Software  │ https://btcarmory.com/
  c chia  2.7.0  GUI Python implementation for the Chia blockchain  │ https://www.chia.net/
  c drawbot  3.132  Write Python scripts to generate two-dimensional graphics  │ https://www.drawbot.com/
  c pycharm-ce  2025.2.5,252.28238.29  IDE for Python programming - Community Edition  │ https://www.jetbrains.com/pycharm/
```

Quiet mode (`-q`) for piping:
```
$ brew-hop-search -q python | fzf
python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://kislyuk.github.io/argcomplete/
python-build  1.4.3  Simple, correct PEP 517 build frontend  │ https://github.com/pypa/build
python-freethreading  3.14.4  Interpreted, interactive, object-oriented programming language  │ https://www.python.org/
anaconda  2025.12-2  Distribution of the Python and R programming languages for scientific computing  │ https://www.anaconda.com/
armory  0.96.5  Python-Based Bitcoin Software  │ https://btcarmory.com/
chia  2.7.0  GUI Python implementation for the Chia blockchain  │ https://www.chia.net/
```

## Output formats

### CSV (`--csv`)
```csv
source,name,version,description,homepage
f,python-argcomplete,3.6.3,Tab completion for Python argparse,https://kislyuk.github.io/argcomplete/
f,python-build,1.4.3,"Simple, correct PEP 517 build frontend",https://github.com/pypa/build
f,python-freethreading,3.14.4,"Interpreted, interactive, object-oriented programming language",https://www.python.org/
c,anaconda,2025.12-2,Distribution of the Python and R programming languages for scientific computing,https://www.anaconda.com/
c,armory,0.96.5,Python-Based Bitcoin Software,https://btcarmory.com/
c,chia,2.7.0,GUI Python implementation for the Chia blockchain,https://www.chia.net/
```

### Table (`--table`)
```
S  Name                  Ver                    Description                                         Homepage                              
-  --------------------  ---------------------  --------------------------------------------------  --------------------------------------
f  python-argcomplete    3.6.3                  Tab completion for Python argparse                  https://kislyuk.github.io/argcomplete/
f  python-build          1.4.3                  Simple, correct PEP 517 build frontend              https://github.com/pypa/build         
f  python-freethreading  3.14.4                 Interpreted, interactive, object-oriented program…  https://www.python.org/               
f  python-gdbm@3.11      3.11.15                Python interface to gdbm                            https://www.python.org/               
f  python-gdbm@3.12      3.12.13                Python interface to gdbm                            https://www.python.org/               
c  anaconda              2025.12-2              Distribution of the Python and R programming lang…  https://www.anaconda.com/             
c  armory                0.96.5                 Python-Based Bitcoin Software                       https://btcarmory.com/                
c  chia                  2.7.0                  GUI Python implementation for the Chia blockchain   https://www.chia.net/                 
c  drawbot               3.132                  Write Python scripts to generate two-dimensional …  https://www.drawbot.com/              
c  pycharm-ce            2025.2.5,252.28238.29  IDE for Python programming - Community Edition      https://www.jetbrains.com/pycharm/    
```

Also: `--tsv`, `--json` (full) / `--json=short` (compact rows), `--sql`, `-g` (grep).

## Cache status (`-C`)

```
  db  brew-hop-search/brew-hop-search.db  61.6 MB
  formula    8314  2d23h ago  fts  30MB json
  cask    7627  2d23h ago  fts  14MB json
  installed:f     460  2d17h ago
  installed:c      86  2d17h ago
  taps      50  3d9h ago
  local:f     161  3d9h ago
  local:c      59  3d9h ago
```

## Usage

```
usage: brew-hop-search [-fcitL] [-VCOH] [-gqT|--json[=MODE]|--csv|--tsv|--sql] [-n N[+OFF]] [--refresh[=DUR]] [query ...]

Fast offline-first Homebrew formula/cask search.

positional arguments:
  query                 search terms (AND-matched)

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
  -O, --outdated        outdated packages
  --brew-verify         use brew for -O (slower, authoritative)
  -H, --history         version history for rollback

cache:
  --refresh [DUR]       sync refresh (bare: force, =DUR: if older)
  --stale [DUR]         background refresh threshold (default: 6h)

output:
  -g, --grep            tab-separated for piping
  -q, --quiet           results only (for grep/fzf)
  --json [MODE]         JSON output; MODE=full (default) or short (compact row
                        fields)
  --csv                 CSV output
  --tsv                 tab-separated with header
  -T, --table           aligned columns (like sqlite3 -column)
  --sql                 SQLite INSERT statements
  -n N[+OFF], --limit N[+OFF]
                        max results [+offset], 0=all (default: 20)
  -v, --verbose         source tags, cache info (-vv per-source detail)
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
brew-hop-search 0.3.5+639ba7e
```

## License

[MPL-2.0](LICENSE) — file-level copyleft. Fixes to covered files come
back as MPL; new files and downstream projects can pick their own
license. See [claude-collab/licenses.md](../claude-collab/licenses.md)
for the rationale.
