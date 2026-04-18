# Development

Linear happy path from code change to published package. If any step fails, fix
the underlying issue and re-run — the guards exist so you can't silently ship
the wrong thing.

## Version invariant

**HEAD of `dev` must never share its version with a published release.** The
release flow maintains this mechanically, two ways:

- **After publish**, `publish.sh` runs `bump-version.sh --dev`, setting
  `__version__` to the next `.dev0` form (e.g. `0.3.1` → `0.3.2.dev0`). Files
  are left **uncommitted** — the dirty working tree is the "release done"
  marker, swept by your next real commit.
- **Before tagging**, `release.sh` runs `bump-version.sh --release`, which
  strips `.devN` (e.g. `0.3.2.dev0` → `0.3.2`) and commits the promotion.
  So tags always land on release-form versions, never `.dev0`.

If you pick up the project on another host with the post-publish `.dev0` never
committed, `make release` will catch it at Step 0 (PyPI preflight) and tell
you to bump — no silent republish.

## One-time setup

```sh
uv sync                       # install dev deps
uv run brew-hop-search -C     # prime the cache (first run fetches ~44 MB)
```

## The release loop

```sh
# 1. Edit code + tests.
$EDITOR src/brew_hop_search/...

# 2. Run tests. If snapshots diverge intentionally: UPDATE_SNAPSHOTS=1 make test
make test

# 3. Regenerate README from live output (only if user-facing output changed).
make readme

# 4. Commit the changes.
git commit -am "…"

# 5. Bump the version. This edits __init__.py + pyproject.toml. Commit it.
#    (If HEAD is already $X.Y.Z.dev0 from last release, skip this — the
#    release flow will auto-promote .dev0 → release at Step 0.)
make bump
git commit -am "Bump to $(make -s version)"

# 6. Run the release flow. Interactive, stops on error, asks before each
#    irreversible step. Runs: PyPI preflight → tests → build → review →
#    tag → fast-forward main → print publish commands.
make release

# 7. Copy-paste the printed publish commands. The publish script enforces
#    version-scoped upload (dist/*$VERSION*) and wheel-newer-than-tag check.
make publish-test     # to TestPyPI
make publish          # to PyPI
```

## What the guards do

| Guard | Where | What it prevents |
|-------|-------|------------------|
| `guard_pypi_unique` | `release.sh` step 0, `publish.sh` | Re-uploading an already-published version (PyPI silently 400s on re-upload; this catches it earlier) |
| `guard_dist_exists` | `publish.sh` | Publishing with nothing built |
| `guard_wheel_fresh` | `publish.sh` | Publishing a wheel that was built *before* the current version was tagged — catches "I bumped, then forgot to rebuild" |
| Clean working tree | `publish.sh` | Publishing unstaged or uncommitted work |
| `dist/*$VERSION*` glob | `publish.sh` | Accidentally re-uploading old wheels alongside the new one |

## Inspecting state

```sh
make version      # current __version__
make versions     # pypi + testpypi published versions
make tag-list     # git tags matching current version
git tag -l        # all tags
ls -la dist/      # built artifacts with mtimes
```

## If things go wrong

- **`guard_pypi_unique` fails**: the version is already on PyPI. Run `make bump`
  and try again. Never try to "republish" the same version — PyPI refuses it
  and TestPyPI's cache will bite you later.
- **`guard_wheel_fresh` fails**: the wheel in `dist/` is older than the git
  tag for this version. Run `rm -rf dist/ && make build`.
- **Tests fail on snapshots after a UI/output change**: `UPDATE_SNAPSHOTS=1
  make test`, then review `git diff tests/snapshots/` before committing.

## Script map

All scripts live in `scripts/`. Most users only need `make` targets.

| Script | Invoked by | Purpose |
|--------|------------|---------|
| `_guards.sh` | sourced | Shared preflight functions |
| `bump-version.sh` | `make bump` | Patch-bump `__init__.py` + `pyproject.toml` |
| `build-tag.sh` | `make tag` / `release.sh` | Create rc or release git tag |
| `build-readme.sh` | `make readme` | Regenerate `README.md` from template + live output |
| `release.sh` | `make release` | Interactive checkpointed release |
| `publish.sh` | `make publish[-test]` | Guarded upload to PyPI/TestPyPI |
