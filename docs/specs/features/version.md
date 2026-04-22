# version

Show tool identity, build info, install source, and update status.

## Purpose

Quick version check (`-V`) and detailed diagnostic info (`-VV`). The output
varies by install source so local dev gets a reproducibility marker while
clean installs stay uncluttered.

## Input

- **flag**: `-V` / `--version` (stackable: `-VV`)

No query, no source flags.

## Install source

Detected at runtime:

| Source    | Detection                                                           |
|-----------|---------------------------------------------------------------------|
| `local`   | `git rev-parse --is-inside-work-tree` succeeds at the package dir   |
| `brew`    | Package path contains `/Cellar/` or `/linuxbrew/`                   |
| `pypi`    | Package path contains `site-packages` (covers `pip`/`uv tool`/venv) |
| `unknown` | None of the above                                                   |

## Output

### Short (`-V`)

Local dev (anything with a git work tree):

```
brew-hop-search 0.3.5+ee99406
```

or with uncommitted changes:

```
brew-hop-search 0.3.5+ee99406.dirty
```

Brew / PyPI install:

```
brew-hop-search 0.3.5
```

The hash on local builds is a deterministic reproducibility marker. Clean
installs omit it because the plain version already uniquely identifies
what's running.

### Detailed (`-VV`)

Always includes the commit hash on the first line, plus an `install` field
and the rest of the diagnostic card:

```
brew-hop-search 0.3.5+ee99406
  version     0.3.5
  commit      ee99406
  install     local
  user-agent  brew-hop-search/0.3.5
  pypi        https://pypi.org/project/brew-hop-search/
  github      https://github.com/mcint/brew-hop-search

recent commits
  ee99406 Terse -h: add info line for -C / -V / -VV
  ...

pypi  up to date (0.3.5)
```

Shows:
- Version, commit hash, install source, user-agent
- Project URLs (PyPI, GitHub, brew tap when available)
- Recent git commit log (10 entries, when a git dir is reachable)
- Live PyPI version check (update available / up to date)

## Identity Fields

| Field | Source |
|-------|--------|
| `version` | `__version__` in `__init__.py` |
| `commit` | `git rev-parse --short HEAD`; falls back to baked `BUILD_COMMIT` on wheels |
| `install` | `install_source()` in `__init__.py` |
| `user-agent` | `user_agent()` — env var > config > default |
| `pypi` / `github` / `tap` | Hardcoded URL constants |

## User-Agent Configuration

Priority:
1. `BREW_HOP_SEARCH_UA` environment variable
2. `user_agent` key in `~/.config/brew-hop-search/config.toml`
3. Default: `brew-hop-search/{version}`

Used in all HTTP requests (API fetch, PyPI version check).

## Data Sources

- Local: git subprocess for commit hash, dirty flag, and log
- Network: PyPI JSON API for update check (only at `-VV`)

## Cache Behavior

None. Always live data.

## Testing

Snapshot tests in `tests/snapshots/` cover help/output formats; `-V` /
`-VV` are exercised via the `_VERSION_RE` mask in `tests/test_cli.py::run`
so commit hashes and version numbers don't churn snapshots. When
user-facing output changes, update with `UPDATE_SNAPSHOTS=1 make test` and
review the diff before committing.

## Examples

```sh
brew-hop-search -V        # quick version (hash on local dev only)
brew-hop-search -VV       # full diagnostic incl. install source
```
