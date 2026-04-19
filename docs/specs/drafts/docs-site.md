# Docs site (sphinx on github.io) (draft)

## Purpose
Publish versioned documentation at a stable URL (e.g.
`mcint.github.io/brew-hop-search`) so the PyPI "Documentation" sidebar
link goes somewhere *better* than the repo's `docs/` tree. Goal posts:
install/tutorial/reference navigation, per-version pages, search.

## Design

### Stack: sphinx + myst + furo

- **Sphinx** — Python-native, ships with autodoc for `help_ui` and other
  modules, integrates with pytest and with `intersphinx` so specs can
  link to upstream docs (sqlite-utils, argparse).
- **MyST parser** — keeps existing markdown in `docs/` usable as-is; no
  rewrite to reStructuredText needed.
- **Furo theme** — matches the hypothesis-docs aesthetic the user likes;
  good per-version dropdown support.

### Layout

```
docs/
├── conf.py                       # sphinx config
├── index.md                      # landing page
├── install.md                    # PyPI / homebrew / uv tool
├── tutorial.md                   # the "cookbook" draft, promoted
├── reference/
│   ├── cli.md                    # generated from help_ui HELP dict
│   ├── output-formats.md         # rendered from OUTPUT.md
│   └── cache.md
├── specs/                        # existing specs/ tree, linked in
└── changelog.md                  # curated version log
```

`conf.py` points myst at the existing `docs/specs/` tree and the top-level
`README.md` so nothing gets duplicated.

### Per-version docs

Use `sphinx-multiversion` (or `mike`) to publish
`/latest/`, `/0.3.3/`, `/0.3.4/` etc. Tag-driven: each git tag that
matches `v\d+\.\d+\.\d+` becomes a published version. `latest` tracks
`main`; `dev` tracks `dev` branch for previewing.

### Build + publish

GitHub Actions workflow on tag push:

```yaml
# .github/workflows/docs.yml
on:
  push: { tags: ['v*'] }
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }  # need full history for multiversion
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --group docs
      - run: uv run sphinx-multiversion docs _site
      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: _site
```

New dependency group:

```toml
[dependency-groups]
docs = ["sphinx", "myst-parser", "furo", "sphinx-multiversion"]
```

### PyPI sidebar update

After first publish, change `Documentation` in `[project.urls]` from
`.../tree/main/docs` to `https://mcint.github.io/brew-hop-search/`. One
release after the docs site goes live.

## Content priorities for v1

1. **Landing + install** — mirror the README's opening, install matrix,
   one quickstart example. Don't duplicate README prose; link back.
2. **Tutorial** — promote `docs/specs/drafts/cookbook.md` to a real
   page, render the examples. Ties into the doc-as-test thread: each
   code block in the tutorial should be a tagged expect-test.
3. **CLI reference** — auto-generated from the argparse parser + the
   `HELP` dict in `help_ui.py`. Single source of truth with `--help=…`.
4. **Changelog** — curated from `git log v0.3.2..v0.3.3` etc; for v1
   just embed GitHub releases via RSS, punt on hand-written until
   there's reason to.

## Tests

Per TDD norm:

- `test_docs_build` — sphinx builds without warnings. Lives in
  `tests/test_docs.py`, skipped unless `[docs]` extras are installed.
- `test_cli_reference_matches_help` — the rendered CLI reference page
  matches `brew-hop-search --help=<each-flag>` output. Snapshot-based.

## Non-goals

- **No** custom theme. Furo is right.
- **No** ReadTheDocs. github.io + Actions is enough, zero third-party
  dependencies, no account to manage.
- **No** translation infrastructure. Until someone asks.

## Rollout

1. Add `[docs]` dependency group + `docs/conf.py` skeleton. Land on
   `dev` without enabling CI.
2. Confirm local build: `uv run sphinx-build docs _site/latest`.
3. Enable GitHub Actions workflow. Publish from `dev` first for a
   shakedown.
4. After a stable build, add the tag-driven multiversion step.
5. Flip PyPI `Documentation` URL.

## Related

- `README.md` — the hypothesis-style `[project.urls]` wiring
  is already in place as of 0.3.3; this spec fills in the
  `Documentation` target.
- `claude-collab/help-ux.md` — CLI reference generation ties into the
  help dispatcher design.
