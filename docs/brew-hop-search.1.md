# brew-hop-search(1) -- fast offline-first Homebrew search

## SYNOPSIS

`brew-hop-search` [`-fcitL`] [`-gq`|`--json`] [`-n` *N*[`+`*OFF*]] [`--refresh`[`=`*DUR*]] [`-VCOH`] [*query* ...]

## DESCRIPTION

Fast offline-first search of Homebrew formulae, casks, taps, and installed
packages. Built on SQLite with FTS5 full-text search for instant local queries
with smart background caching.

On first run, fetches indexes from `formulae.brew.sh` into a local SQLite
database. Subsequent searches are instant. Stale caches refresh in the
background.

Default searches never call `brew` — only HTTP or local DB reads.

## SOURCES

Sources are composable. Default (no flags) searches the remote API index.

* `-f`, `--formulae`:
  Formulae only.

* `-c`, `--casks`:
  Casks only.

* `-i`, `--installed`:
  Installed packages (calls `brew info`).

* `-t`, `--taps`:
  Tapped repos (calls `brew --repository`).

* `-L`, `--local`:
  Brew's local API cache at `$(brew --cache)/api/` (offline, calls `brew --cache`).

Combine freely: `-i -f` searches installed formulae only, `-i -t` searches
both installed and taps.

## OUTPUT

Each result line is prefixed with a source indicator: `f`=formula, `c`=cask,
`t`=tap, `i`=installed (colored on TTY).

* `-g`, `--grep`:
  Tab-separated output for piping: *slug*\\t*version*\\t*url*

* `-q`, `--quiet`:
  Results only — no section headers, no indicators. For `grep`/`fzf`.

* `--json`:
  Raw JSON output.

* `-n` *N*[`+`*OFF*]:
  Max results per section with optional offset. `-n 0` for unlimited.
  `-n +40` skips 40 with default limit 20.

* `-v`, `--verbose`:
  Show cache status and process detail. `-vv` for per-source search info.

## CACHE

* `--refresh`[`=`*DUR*]:
  Synchronous refresh. Bare `--refresh` forces immediate re-fetch.
  `--refresh=1h` refreshes only if cache is older than 1 hour.

* `--stale`[`=`*DUR*]:
  Background refresh threshold (default: 6h). Triggers a detached
  subprocess to update the cache without blocking the current search.

## INFO

* `-V`, `--version`:
  Show version. `-VV` also shows recent commit log and PyPI update check.

* `-C`, `--cache-status`:
  Show detailed cache status (per-source age, FTS status, DB size).

* `-O`, `--outdated`:
  Show outdated packages by comparing installed vs API index versions
  locally (instant, no brew subprocess). Shows pinned and keg-only status.

* `--brew-verify`:
  Use with `-O` to run `brew outdated --json=v2` instead (slower,
  authoritative). Accounts for bottle rebuilds, `pour_bottle_only_if`,
  and tap-only formulae that the fast path may miss.

* `-H`, `--history`:
  Show version history for a package from the install log. Records
  brew git commit hashes for rollback reference.

## OUTDATED ACCURACY

The fast outdated (`-O`) compares version+revision from the installed index
against the API index. Known limitations:

* Does not check bottle rebuild numbers
* Does not evaluate `pour_bottle_only_if` platform conditions
* Tap-only formulae not in the main API index are skipped
* Casks with `version "latest"` are excluded

Use `--brew-verify` to cross-check against brew's authoritative assessment.
Pinned packages are marked `[pinned]`, keg-only as `[keg-only]`.

## EXAMPLES

    brew-hop-search python              # search formulae + casks
    brew-hop-search -f python build     # multi-word, formulae only
    brew-hop-search -i                  # list all installed
    brew-hop-search -i -c               # installed casks only
    brew-hop-search -q python | fzf     # pipe to fzf
    brew-hop-search -O                  # fast outdated
    brew-hop-search -O --brew-verify    # authoritative outdated
    brew-hop-search -H python@3.13      # version history

## FILES

* `~/.cache/brew-hop-search/brew-hop-search.db`:
  SQLite database with FTS5 indexes.

* `~/.cache/brew-hop-search/*.json`:
  Raw JSON caches from `formulae.brew.sh`.

## ENVIRONMENT

* `BREW_HOP_SEARCH_DB`:
  Override database path (used for testing).

## SEE ALSO

brew(1), sqlite-utils(1)
