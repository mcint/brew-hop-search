# Inspirations & Influences

Projects whose design choices shaped brew-hop-search, grouped by concern.

*Not a comparison* — for "what does bhs add over X" or "what we
intentionally diverge from", see `docs/COMPARABLES.md`. This doc is
about *whose taste we learned from* and *what specific decision each
project pushed us toward*. Entries here are intentionally terse; the
rationale lives in COMPARABLES.

---

## Input Design

| Project | Link | What we took |
|---------|------|--------------|
| **argparse** | stdlib | Subparser-free flat surface, mutually exclusive groups for source flags |
| **ripgrep** | [github.com/BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) | Smart-by-default flags, `-q`/`-v`/`-vv` verbosity ladder |
| **brew** | [github.com/Homebrew/brew](https://github.com/Homebrew/brew) | `-f`/`-c`/`-i` semantics; we mirror brew's mental model, then go offline |
| **fzf** | [github.com/junegunn/fzf](https://github.com/junegunn/fzf) | Composition target — `bhs -q | fzf` shapes our quiet-mode output |
| **gh** | [github.com/cli/cli](https://github.com/cli/cli) | `--json` as a first-class flag, not an afterthought |

## Output Design

| Project | Link | What we took |
|---------|------|--------------|
| **bat** | [github.com/sharkdp/bat](https://github.com/sharkdp/bat) | Plain when piped, decorated on TTY. Auto-detection pattern |
| **jq** | [jqlang.github.io/jq](https://jqlang.github.io/jq/) | Clean JSON that's pipe-friendly without `.[]` gymnastics |
| **qsv** | [github.com/jqnatividad/qsv](https://github.com/jqnatividad/qsv) | `--csv` / `--tsv` designed for downstream CSV tooling |
| **datasette** | [datasette.io](https://datasette.io/) | The cache *is* the data — `--sql` exposes the raw FTS5 table |
| **hyperfine** | [github.com/sharkdp/hyperfine](https://github.com/sharkdp/hyperfine) | `--export-json` / `--export-markdown` for focused tools |
| **ripgrep** | [github.com/BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) | Color heuristics, ANSI codes raw rather than via `rich` |

## Cache & Storage

| Project | Link | What we took |
|---------|------|--------------|
| **sqlite-utils** | [github.com/simonw/sqlite-utils](https://github.com/simonw/sqlite-utils) | Our DB layer. `insert_all()` + FTS5 + pk-based upsert |
| **SQLite FTS5** | [sqlite.org/fts5](https://www.sqlite.org/fts5.html) | The whole search story. `MATCH`, `bm25`, prefix indexes |
| **bkt** | [github.com/dimo414/bkt](https://github.com/dimo414/bkt) | Cache-first read, refresh in background. Stale-while-revalidate |
| **homebrew-cask** | [github.com/Homebrew/homebrew-cask](https://github.com/Homebrew/homebrew-cask) | The JSON shape is our schema. We parse what brew already serves |

## Verbosity & Progressive Disclosure

| Project | Link | What we took |
|---------|------|--------------|
| **ripgrep** | [github.com/BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) | `-q` → default → `-v` → `-vv` ladder; quiet default, verbose on request |
| **curl** | [curl.se](https://curl.se/) | `-v`/`-vv`/`-vvv` as cumulative verbosity, not a fixed enum |
| **git** | [git-scm.com](https://git-scm.com/) | Status density that respects terminal width and screen budget |
| **lib-rs-search** | sibling project | Verbosity ladder kept consistent across both tools |

## Testing

| Project | Link | What we took |
|---------|------|--------------|
| **insta** | [insta.rs](https://insta.rs/) | Snapshot review workflow — first run is red, accept commits intent |
| **ppx_expect** | [github.com/janestreet/ppx_expect](https://github.com/janestreet/ppx_expect) | Expect-test ergonomics: inline expected output, diff-on-failure |
| **pytest** | [pytest.org](https://pytest.org/) | Fixture composition, conftest.py for shared setup |
| **CliRunner-style harnesses** | click / typer | Capturing argparse output for assertion |

## Distribution & Packaging

| Project | Link | What we took |
|---------|------|--------------|
| **uv** | [github.com/astral-sh/uv](https://github.com/astral-sh/uv) | `uv sync` / `uv run` reproducibility; lockfile-first dev loop |
| **hatch** | [hatch.pypa.io](https://hatch.pypa.io/) | Build backend; `hatch_build.py` hook for VERSION baking |
| **ruff** | [github.com/astral-sh/ruff](https://github.com/astral-sh/ruff) | Pre-commit posture; lint as a fast feedback loop |
| **homebrew tap pattern** | brew | Distribution shape — Formula/*.rb in this repo, installable as a tap |

## Version & Build Info

The why lives in `docs/research/2026-11-12-git-facts-prior-art.md`; the
design in `docs/specs/drafts/git-facade.md`.

| Project | Link | What we took |
|---------|------|--------------|
| **go build -buildvcs** | [pkg.go.dev/cmd/go](https://pkg.go.dev/cmd/go) | Stamp VCS facts only when the thing being built and the repo agree; otherwise stamp nothing, never the wrong repo. `debug.ReadBuildInfo` is our `_build_info.py` read back |
| **setuptools-scm** | [setuptools-scm.readthedocs.io](https://setuptools-scm.readthedocs.io/) | Toplevel must equal project root; parent-walk is opt-in. Honour `GIT_CEILING_DIRECTORIES` (their PR #1106 fixed our exact tarball-in-foreign-repo bug) |
| **git** | [git-scm.com/docs/git](https://git-scm.com/docs/git) | `GIT_CEILING_DIRECTORIES` as the walk bound; `rev-parse --show-toplevel` as the one question we ask before any other |
| **vergen** | [docs.rs/vergen-gitcl](https://docs.rs/vergen-gitcl/) | Build-script stamping via the git CLI, not a git library; idempotent defaults on error instead of a failed build |
| **versioneer** | [github.com/python-versioneer](https://github.com/python-versioneer/python-versioneer) | One vendored stdlib file shared by build step and runtime; `0+unknown` over a hard failure. What we avoid: its parent-walk default |
| **dunamai** | [github.com/mtkennerly/dunamai](https://github.com/mtkennerly/dunamai) | Stdlib-only subprocess git is enough; a ~60-line module beats a runtime dependency. What we add: the ownership gate it lacks |

## Domain (Package Search)

| Project | Link | What we took |
|---------|------|--------------|
| **brew search** | [github.com/Homebrew/brew](https://github.com/Homebrew/brew) | The baseline we're faster than. Same data, no GitHub API |
| **apt-cache search** | Debian | The Unix template — local index, instant search, no daemon |
| **nix-env -qa** | Nix | What we avoid: expression evaluation. We pre-index instead |
| **pacman -Ss** | Arch | Two-pane match output: name match vs description match |
| **dnf search** | Fedora | Section headers (`Name & Summary Matched`) we echo in `-vv` |

## Cross-Project Companions

| Project | Link | What we took |
|---------|------|--------------|
| **lib-rs-search / crs** | sibling project | Shared design system — cartesian specs, verbosity ladder, snapshot testing |
| **slapchop-cli** | sibling project | Method.md catalogue, INSPIRATIONS-vs-COMPARABLES split, dev-build flag pattern |

---

For the *why* and *what to keep distance from*, see
[COMPARABLES.md](COMPARABLES.md). For *how we organize this repo's
design docs*, see [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md).
