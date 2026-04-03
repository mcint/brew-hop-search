# brew-search

Fast offline-first search of Homebrew formulae, casks, taps, and installed packages.

Built on SQLite + FTS5 for instant local search with smart caching.

[GitHub](https://github.com/steward/brew-search) ·
[PyPI](https://pypi.org/project/brew-search/) ·
[Brew Tap](https://github.com/steward/homebrew-brew-search/blob/main/Formula/brew-search.rb)

## Install

```sh
# PyPI (recommended)
uv tool install brew-search     # or: pip install brew-search
uvx brew-search python          # one-shot without install

# Homebrew tap
brew tap steward/brew-search
brew install brew-search
```

## Usage

```sh
brew-search <query>                  # search formulae + casks (default)
brew-search -f <query>               # formulae only
brew-search -c <query>               # casks only
brew-search -i <query>               # search installed packages
brew-search -t <query>               # also search tapped repos
brew-search -L <query>               # search brew's local API cache (offline)
brew-search -C                       # show cache status
brew-search --refresh <query>        # force re-fetch before searching
```

### Cache control (bkt-style TTLs)

```sh
brew-search --stale 1h <query>       # background refresh if cache > 1h old
brew-search --fresh 24h <query>      # force sync refresh if cache > 24h old
```

### Output formats

```sh
brew-search --json <query>           # JSON output
brew-search -g <query>               # greppable: slug\tversion\turl
brew-search -C --json                # machine-readable cache status
```

### Direct DB access

The SQLite database is at `~/.cache/brew-search/brew-search.db` and is fully compatible with [sqlite-utils](https://sqlite-utils.datasette.io/):

```sh
sqlite-utils tables ~/.cache/brew-search/brew-search.db
sqlite-utils search ~/.cache/brew-search/brew-search.db formula python
sqlite-utils query ~/.cache/brew-search/brew-search.db "SELECT name, desc FROM installed_formula"
```

## How it works

On first run, `brew-search` fetches the Homebrew formula and cask indexes from `formulae.brew.sh`, stores them in a local SQLite database with FTS5 full-text search, and keeps the raw JSON alongside for easy re-creation.

Subsequent searches are instant (local FTS5 queries). Stale caches trigger a background refresh so the next search is both fast and fresh.

| Source | Flag | Data |
|--------|------|------|
| Remote API | *(default)* | `formulae.brew.sh` formula + cask indexes |
| Installed | `-i` | `brew info --json=v2 --installed` |
| Taps | `-t` | `.rb` files in `$(brew --repo)/Library/Taps/` |
| Local | `-L` | Brew's own API cache at `$(brew --cache)/api/` |

## License

MIT
