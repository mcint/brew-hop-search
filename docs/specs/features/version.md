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

Between releases (dev tree):

```
brew-hop-search 0.3.6-dev
```

At a release commit or from a release install:

```
brew-hop-search 0.3.6
```

`-V` prints `__version__` verbatim, and `__version__` is the contents of
the `VERSION` file. One string, one source — no computed markers, no
string parsing.

### Detailed (`-VV`)

Same first line as `-V`; adds an `install` field and the rest of the
diagnostic card:

```
brew-hop-search 0.3.6-dev
  version     0.3.6-dev
  commit      ee99406
  install     local
  user-agent  brew-hop-search/0.3.6-dev
  pypi        https://pypi.org/project/brew-hop-search/
  github      https://github.com/mcint/brew-hop-search

recent commits
  ee99406 Terse -h: add info line for -C / -V / -VV
  ...

pypi  up to date (0.3.6)
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
brew-hop-search -V        # quick version (dev marker on dev builds)
brew-hop-search -VV       # full diagnostic incl. install source
```

---

## Release versioning scheme

How the repo tracks version between releases — not a runtime feature, but
relevant to how `__version__` and wheel metadata get their values.

### Single source of truth

`src/brew_hop_search/VERSION` is the only file storing the version.
Hatch's `[tool.hatch.version] source = "regex"` reads it at build time;
`__init__.py` reads the same file at import time. No second copy in
`pyproject.toml` to drift out of sync.

### Between releases: the `-dev` suffix

After publishing a release, `bump-version.sh --dev` writes `X.Y.(Z+1)-dev`
to VERSION and commits it. The `-dev` marker is the dev-state invariant:
it's right there in the file, survives across checkouts, and makes it
impossible to accidentally produce a build that collides with the
released version — the suffix is already baked in. No git introspection,
no computed devN, no hash appendage. What you see in VERSION is what `-V`
prints.

### Release promotion

`release.sh` auto-detects `X.Y.Z-dev` in VERSION, runs
`bump-version.sh --release` to strip the suffix, commits the promotion as
`Promote to release vX.Y.Z`, and tags. Tags always land on plain release
versions, never `-dev`.

### Resolution table

| Context                   | `VERSION` contents | `__version__` |
|---------------------------|--------------------|---------------|
| Between releases          | `0.3.7-dev`        | `0.3.7-dev`   |
| Release commit / tag      | `0.3.7`            | `0.3.7`       |
| Installed wheel (release) | `0.3.7`            | `0.3.7`       |

### Commands

```sh
make bump                # X.Y.Z → X.Y.(Z+1)  (release form)
./scripts/bump-version.sh --dev      # X.Y.Z → X.Y.(Z+1)-dev
./scripts/bump-version.sh --release  # X.Y.Z-dev → X.Y.Z (no-op otherwise)
make version             # print current VERSION
```
