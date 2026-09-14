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

## QUERY SYNTAX

Each whitespace-separated token is a *term*; every term must match (AND).
A term has the shape `[field:][!][^]pattern[$]`:

* *foo* — substring match in name OR description (default)
* *^foo* — name/desc starts with `foo`
* *foo$* — name/desc ends with `foo`
* *^foo$* — exact equality
* `"foo bar"` — literal substring including whitespace (quote in shell)
* *name:foo* / *n:foo* — substring scoped to name/token
* *desc:foo* / *d:foo* / *description:foo* — substring scoped to description
* *!foo* — negate: no match may contain `foo`

Field prefix, negation, and anchors may compose: `name:^py`,
`!desc:"old api"`. Matching is case-insensitive. No regex in v1; `/foo/`
matches the literal slashes.

Quote terms that contain `^`, `$`, or `!` from the shell to avoid
expansion: `'^python$'` or `"\"machine learning\""`.

## SOURCES

Sources are composable. Default (no flags) searches the remote API index.

* `-f`, `--formulae`:
  Formulae only.

* `-c`, `--casks`:
  Casks only.

* `-i`, `--installed`:
  Installed packages (calls `brew info`).

* `-t`, `--taps`:
  Tapped repos (calls `brew --repository`, scans `.rb` files). On
  Homebrew 6.0+ each row also carries the tap's trust state from
  `brew tap-info --installed --json=v1`; `-t -v` shows `official`,
  `trusted`, or `untrusted` per result. Older brews skip that step and
  say so at `-v`.

* `-l`, `--local`:
  Brew's local API cache at `$(brew --cache)/api/` (offline, calls `brew --cache`).

* `--cached`:
  Every offline source at once — installed, taps, and the local API
  cache (`= -itl`). Never the network index. Composes with `-f`/`-c`
  and every adverb; `--cached --offline` also skips the local refresh
  scans.

Combine freely: `-i -f` searches installed formulae only, `-i -t` searches
both installed and taps.

## OUTPUT

Default output shows section headers and indented results. Verbosity
controls how much context is shown (see `docs/specs/OUTPUT.md` for full spec).

* `-q`, `--quiet`:
  Results only — no section headers, no indicators, no indent.
  Machine-ready for `grep`/`fzf`/scripts.

* `-v`, `--verbose`:
  Adds source indicator column (`f`/`c`/`t`/`i`), cache age header,
  and source summary. `-vv` adds per-source search stats.

* `-g`, `--grep`:
  Tab-separated output for piping: *slug*\\t*version*\\t*url*

* `--json`:
  Raw JSON output.

* `--csv`:
  CSV with header row. Pipes to `qsv`, spreadsheets, pandas.

* `--tsv`:
  Tab-separated with header row. Pipes to `sort`, `awk`, `cut`.

* `--table`:
  Aligned columns (like `sqlite3 -column`).

* `--sql`:
  SQLite INSERT statements. Pipe to `sqlite3 results.db`.

* `-n` *N*[`+`*OFF*]:
  Max results per section with optional offset. `-n 0` for unlimited.
  `-n +40` skips 40 with default limit 20.

## CACHE

* `--refresh`[`=`*DUR*]:
  Synchronous refresh. Bare `--refresh` forces immediate re-fetch.
  `--refresh=1h` refreshes only if cache is older than 1 hour.

* `--offline`:
  No network and no refresh of any kind: serve only what is already
  cached, for every selected source. Errors if a selected source has no
  cache yet. Conflicts with `--refresh`. Unlike `-l` (which *selects*
  brew's on-disk API cache as a source), `--offline` is an adverb that
  composes with any source.

* `--stale`[`=`*DUR*|*KIND*`:`*DUR*[`,`...]]:
  Background-refresh threshold. `--stale=1h` applies to every source the
  invocation touches; `--stale=installed:5m,taps:10m` sets one source at a
  time (kinds: `index`, `installed`, `taps`, `local`, `all`; short forms
  `x i t l`). Defaults: 6h for the API index, 1h for the rest
  (`$BREW_HOP_SEARCH_STALE_API` / `_INSTALLED` / `_TAPS` / `_LOCAL`).
  A stale source is refreshed by a detached subprocess without blocking
  the current search.

## INFO

* `-V`, `--version`:
  Show version. `-VV` also shows recent commit log and PyPI update check.

* `-C`, `--cache-status`:
  Show detailed cache status (per-source age, FTS status, DB size).

* `-O`, `--outdated`:
  Show outdated packages by comparing installed vs API index versions
  locally (instant, no brew subprocess). Shows pinned and keg-only status.

* `--brew-verify`:
  Use with `-O` to run **both** fast local comparison and
  `brew outdated --json=v2`, then show a package-matched diff.
  Prefixes: `~` version differs, `+` brew-only, `-` bhs-only.
  Version word-diff shown when target versions differ.

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
    brew-hop-search '^python'           # names starting with python
    brew-hop-search '^python@3.13$'     # exact name match
    brew-hop-search 'name:^py' d:build  # scoped name-prefix + desc term
    brew-hop-search '"machine learning"'  # literal phrase with whitespace
    brew-hop-search '^python' '!@3.9'   # prefix, excluding the 3.9 variant
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
