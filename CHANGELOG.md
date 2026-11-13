# Changelog

Notable changes per release. The auto-generated tag message
(`git show v<version>`) has the per-commit bullets; this file is the
curated narrative, grouped and headlined.

Format roughly follows [Keep a Changelog](https://keepachangelog.com/).
Versions follow [PEP 440](https://peps.python.org/pep-0440/).

## [0.3.8]

This release starts to target `brew <subcommand>` support; the `bhs` /
`brewhs` / `brew-hop-search` surface is unchanged.

### Added

- **`brew hs`.** A `brew-hs` console script, which brew's external
  command lookup runs as `brew hs python`; the tap formula symlinks
  `brewhs` and `brew-hs` beside `brew-hop-search`. Spec: short-names.md
  § brew subcommand.

### Changed

- **The time footer tells the whole story.** `# [time] total 0.129s ·
  cache 0.037s · api(0) —`, with `· refresh bg` or `· refresh 1.9s` when a
  background refresh ran. `total` runs from the package's first import,
  not from `main()`; `cache` is the SQLite time; `api(n)` counts
  foreground HTTP requests. The v1 footer once printed `0.134s` beside a
  shell `time` of 2.7s. Spec: `docs/specs/features/timing.md`, which also
  names what the process cannot see (brew's own bootstrap under `brew hs`).
- Dev interpreter pinned to 3.12 via `.python-version`. CI tests the floor
  and the newest stable, Python 3.9 and 3.15; `make test-all` runs every
  version in between locally.

### Fixed

- **`-i` crashed on installed casks** (`TypeError: '<' not supported
  between instances of 'str' and 'list'`) when one cask had an empty
  display-name list and another did not; the tie-break sort key now
  reduces every record to one string.
- The tap is `brew tap mcint/tap` (repo `mcint/homebrew-tap`); README
  and `-VV` pointed at a tap that does not exist.
- **A brew install no longer reports Homebrew's own git tree.** `git -C`
  walked up from the Cellar into `/opt/homebrew/.git`, so 0.3.7 from the
  tap printed `0.3.7+95`, Homebrew/brew's HEAD and ten of its merge
  commits as its own. Git facts now count only when the enclosing repo
  *is* this project; otherwise the baked build info is the truth. The
  build hook applies the same rule to sdists built inside other repos.
  Spec: `docs/specs/features/version-reporting.md`.
- `-VV` no longer says "up to date" when the local build is *ahead* of
  PyPI: a dev tree, rc or between-tags build prints blue "ahead of PyPI";
  a plain X.Y.Z that PyPI has never seen prints red and exits 1.
- The commit-count version test no longer depends on whether the tree
  has been built.

## [0.3.7] — 2026-05-28

A user-facing capability release: real query syntax, offline-first
cache flow, more output formats, snappier UX after `-i`. Also lays
the design groundwork (six draft specs) for the next round of
vocabulary and format work.

### Highlights

- **Query syntax** lands. Anchors (`^foo`, `foo$`, `^exact$`), field
  scoping (`name:foo`, `desc:bar`), negation (`!foo`), quoted phrases.
  Multiple whitespace-separated terms AND-match. See `--help=query`.
- **Offline-first cache flow.** Results print from SQLite immediately;
  freshness handled in the background via a sentinel-file protocol.
  Two-second grace window then a "still updating" footer so the shell
  returns promptly even on a slow `brew info`.
- **`--refresh=KIND[,KIND...]`** selector for explicit, scoped refreshes.
  Short forms (`x i t l tap`), an `all` alias, and a standalone
  `bhs --refresh=KIND` command that warms caches without searching.
- **Per-command timing footer** — `# [time] <felt>` line on stderr at
  the end of every command. Stays out of stdout under `--json` etc.;
  `--no-timing` / `BREW_HOP_SEARCH_NO_TIMING` to suppress.
- **Richer version display.** `0.3.7-dev+31` (dev tree) /
  `0.3.7+31` (built wheel between tags) / `0.3.7` (tagged). PEP 440
  local-version label so tagged releases stay clean on PyPI.
- **`--multi` / `--long`** output format — one block per result with
  labeled fields, for narrow-terminal reading.

### Added

- Query syntax parser, predicates, and scoring (`5b573cc`, `b025163`,
  `21c3a67`).
- Cache-first stale flow with background refresh and trailing status
  (`f961e36`, `717eed3`).
- `--refresh=KIND[,KIND...]` selector form, short kinds (`x i t l tap`),
  `all` alias, and standalone-command behavior (`9d48132`, `45336e5`,
  `3035cb7`).
- `--fresh` as an alias for `--refresh` (`955690c`).
- `--multi` / `--long` per-record output (`62c5051`).
- TOML/env layer for default output format (`d606cbc`).
- 12-factor `STALE_*` env-var overrides for cache TTLs (`341a7b7`).
- `-C` cache-status `ttl` column with `-v`/`-vv` layered detail
  (`1d89eff`).
- Per-command `# [time] <felt>` timing footer (`2a4929f`).
- `INSPIRATIONS.md` doc — projects-by-concern tables of *whose taste
  shaped each surface* (`6845ffb`).
- Six draft specs in `docs/specs/drafts/`: timing, installed-indicator,
  format-color, cli-vocabulary, output-readability, index-git-history
  (`b18a8d2`, `8a8b6d0`, `8c1bb48`).
- Tag-message generator now lists commits-since-last-tag (`bcfd471`).

### Changed

- Version display: `__version__` stays raw VERSION-file content;
  `version_info()` decorates with `+N` commits-since-tag suffix —
  `0.3.7-dev+N` (dev tree) / `0.3.7+N` (built) / `0.3.7` (tagged).
  PEP 440 local-version label (`194b3ce`, `206de5a`).
- Trailing cache-update status: 300s blocking hold → 2s grace, then
  "still updating in background" footer. Shell returns promptly,
  bg subprocess keeps running with its own session (`16335fa`).
- Version comparison switched from hand-rolled tuples to
  `packaging.version.Version` (`6300729`).
- Defaults centralized in `src/brew_hop_search/defaults.py` (`fdb09c7`).
- Taps scanner: integration-tested DB round-trip, dedupe when same
  name exists at both the tap root and `Formula/` (`4952314`,
  `42d155a`).

### Fixed

- `--refresh=KIND` no-op when the corresponding source flag wasn't
  passed (`e008e07`).
- `-H` history recording the *index* version instead of the
  *installed* version (`650ecc5`).
- `-VV` PyPI check crashing on int/str tuple mix when the version
  string had a `-dev` suffix (`105a418`).
- `publish.sh` bash 3.2 unbound-array error (`339fe8c`).

### Internal / specs

- Drafted: timing (implementation landed v1), installed-indicator
  column, format-color policy, cli-vocabulary cartesian audit,
  output-readability tradeoffs, `-G` index-git-history.
- 10 follow-up beads filed for the items deferred from this release
  (smart URL caps, OSC 8 hyperlinks, `--offline` adverb, `-L` → `-l`
  rename, subcommand layer, `--stale` universalization, interactive
  viewer, scoped `-v=t` sub-args, vocabulary unification, stale-result
  diff hash).

## [0.3.6] and earlier

See `git log v0.3.5..v0.3.6` etc.
