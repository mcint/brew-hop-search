# Tracked Git Hooks & Check Tiers (draft)

## Purpose
Move git hooks from `.git/hooks/` into a version-controlled `hooks/` directory, and expose tiered check levels via `just` or `Makefile` so developers know exactly what checks exist and can run any tier manually.

## Status
**Draft** — not yet implemented.

## Motivation

`.git/hooks/` is not tracked by git. This means:
- New clones don't get hooks automatically
- Hook changes aren't reviewable in PRs
- No audit trail for what runs on commit/push
- Developers don't know what checks are available beyond the implicit hooks

Moving hooks to `hooks/` and setting `core.hooksPath` makes them versioned, reviewable, and consistent. Exposing tiers makes the full check menu discoverable.

## Check Tiers

Each tier includes everything from the previous tier.

| Tier | Command | When | What | Time |
|------|---------|------|------|------|
| 1. quick | `just quick` | pre-commit hook | `pytest -q` | ~3s |
| 2. check | `just check` | pre-push hook | + `ruff check` | ~5s |
| 3. full | `just full` | before opening a PR | + `ruff format --check` + type check | ~10s |
| 4. ci | `just ci` | CI pipeline | + coverage, snapshot freshness | ~30s |

Developers should know: **`just tiers`** prints this table.

## Implementation

### Justfile

```just
# Run once after cloning
setup:
    git config core.hooksPath hooks
    uv sync --dev
    @echo "✓ hooks configured, dev deps installed"

# Tier 1: fast tests (pre-commit)
quick:
    python -m pytest -q
    @echo "✓ quick passed"

# Tier 2: lint + tests (pre-push)
check:
    ruff check src/ tests/
    python -m pytest -q
    @echo "✓ check passed"

# Tier 3: everything before a PR
full:
    ruff format --check src/ tests/
    ruff check src/ tests/
    python -m pytest
    @echo "✓ full passed — ready for PR"

# Tier 4: CI-equivalent
ci: full
    python -m pytest --tb=long -vv
    @echo "✓ ci passed"

# Show available tiers
tiers:
    @echo "Check tiers (each includes the previous):"
    @echo "  just quick   — pytest                  (pre-commit, ~3s)"
    @echo "  just check   — + ruff check            (pre-push, ~5s)"
    @echo "  just full    — + ruff format + types    (before PR, ~10s)"
    @echo "  just ci      — + coverage, snapshots    (CI pipeline)"
```

### Hooks

Hooks delegate to `just`, so logic lives in one place:

```bash
# hooks/pre-commit
#!/bin/sh
set -e
just quick

# hooks/pre-push
#!/bin/sh
set -e
just check
```

### Setup

```bash
# After cloning:
just setup
```

## Prior Art

- slapchop-cli uses this pattern: `hooks/` + `core.hooksPath` + Justfile tiers
- Husky (npm) does similar for JavaScript projects
- pre-commit (Python framework) is heavier than needed for a single project
