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

## Example output

```
  cache: 2h old   searching formula + cask

  # formulae (5/8307)  • brew install python-argcomplete
  f python-argcomplete  3.6.3  Tab completion for Python argparse       │ https://kislyuk.github.io/argcomplete/
  f python-build        1.4.2  Simple, correct PEP 517 build frontend   │ https://github.com/pypa/build
  f python-freethreading 3.14.3 Interpreted, interactive, object-oriented│ https://www.python.org/
  f python-gdbm@3.11    3.11.15 Python interface to gdbm                │ https://www.python.org/
  f python-gdbm@3.12    3.12.13 Python interface to gdbm                │ https://www.python.org/

  # casks (5/7589)  • brew install --cask anaconda
  c anaconda     2025.12  Distribution of Python and R for scientific computing │ https://www.anaconda.com/
  c drawbot      3.132    Write Python scripts to generate 2D graphics          │ https://www.drawbot.com/
  c pycharm-ce   2025.2   IDE for Python programming - Community Edition        │ https://www.jetbrains.com/pycharm/
```

Source indicators: `f`=formula `c`=cask `t`=tap `i`=installed (colored on TTY).

Quiet mode (`-q`) strips all chrome for piping:
```
$ brew-hop-search -q python | fzf
python-argcomplete  3.6.3  Tab completion for Python argparse  │ https://...
```

## Usage

```
usage: brew-hop-search [-fcitL] [-gq|--json] [-n N[+OFF]] [--refresh[=DUR]] [-VCOH] [query ...]

sources (composable, default: remote API):
  -f  formulae only         -i  installed packages
  -c  casks only            -t  tapped repos
                            -L  local API cache (offline)

output:                     cache:
  -g  tab-separated           --refresh[=DUR]  sync refresh
  -q  quiet (for grep/fzf)    --stale[=DUR]    background threshold (6h)
  --json  raw JSON
  -n N[+OFF]  limit/offset  info:
  -v  process detail          -V  version  -C  cache status
                              -O  outdated -H  history
```

### Examples

```sh
brew-hop-search python                 # search formulae + casks
brew-hop-search -f python build        # multi-word, formulae only
brew-hop-search -i                     # list all installed
brew-hop-search -i -c                  # installed casks only
brew-hop-search -i -t python           # search installed + taps
brew-hop-search -q python | fzf        # pipe to fzf
brew-hop-search -n 10+20 python        # 10 results, skip 20
brew-hop-search -O                     # show outdated (fast, local)
brew-hop-search -O --brew-verify       # outdated via brew (authoritative)
brew-hop-search -H python@3.13         # version history for rollback
brew-hop-search --refresh python       # force re-fetch
brew-hop-search --refresh=1h python    # refresh if older than 1h
```

### Direct DB access

The SQLite database is at `~/.cache/brew-hop-search/brew-hop-search.db` and is fully compatible with [sqlite-utils](https://sqlite-utils.datasette.io/):

```sh
sqlite-utils tables ~/.cache/brew-hop-search/brew-hop-search.db
sqlite-utils search ~/.cache/brew-hop-search/brew-hop-search.db formula python
```

## How it works

On first run, fetches Homebrew formula and cask indexes from `formulae.brew.sh` into SQLite with FTS5. Subsequent searches are instant (local DB). Stale caches trigger background refresh.

| Source | Flag | Data | Calls brew? |
|--------|------|------|-------------|
| Remote API | *(default)* | `formulae.brew.sh` | No |
| Installed | `-i` | `brew info --json=v2 --installed` | Yes |
| Taps | `-t` | `.rb` files in `$(brew --repo)/Library/Taps/` | Yes (`--repository`) |
| Local | `-L` | Brew's API cache at `$(brew --cache)/api/` | Yes (`--cache`) |
| Outdated | `-O` | Compares installed vs API index | No |
| Outdated | `-O --brew-verify` | `brew outdated --json=v2` | Yes |

## License

MIT
