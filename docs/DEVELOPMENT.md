# Development

```sh
uv sync                        # dev deps; .python-version pins the dev interpreter
uv run brew-hop-search -C      # prime the cache (first run fetches ~44 MB)
make test                      # the suite; UPDATE_SNAPSHOTS=1 make test to accept output changes
```

- Code in `src/brew_hop_search/`, tests in `tests/` (snapshots under
  `tests/snapshots/`), specs in `docs/specs/`, project history and rules in
  `docs/meta/`.
- Spec first or alongside; a new feature ships with a new red-green test in
  the same commit. Conventional Commits with scope.
- Releasing, versioning, the guards and the scripts: `release/README.md`.
  Declaring a version is the owner's act (`docs/meta/RELEASING.md`).
- Working with agents here: `AGENTS.md`; issue tracking with `br`:
  `agents/beads-viewer.md`.
