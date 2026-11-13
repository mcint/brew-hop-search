# Short Names & Aliases (draft → shipping in 0.3.2)

## Purpose
Install the tool under a short alias (`brewhs`) in addition to the canonical
`brew-hop-search`, without renaming the package, breaking existing installs, or
forcing users onto the new name.

## Status
**Shipping** — `brewhs` added to `[project.scripts]` in 0.3.2. `bhs` was
considered and rejected (see Decision below). `brew-hs` added in 0.3.9 so
that `brew hs` works as a brew subcommand (see § brew subcommand).

## Motivation

`brew-hop-search` is 15 characters + a hyphen the shell can't tab-complete past
until you've typed enough to disambiguate. Muscle-memory users already alias it.
A built-in short name:

- Removes the "first thing I do is alias it" tax.
- Makes copy-pasted cookbook recipes shorter and more readable.
- Signals the project takes ergonomics seriously (least-surprise value).

## Decision: `brewhs`, not `bhs`

Names considered:

| Name      | Pronunciation      | Verdict |
|-----------|--------------------|---------|
| `bhs`     | "bee aitch ess"    | **Rejected.** Too generic; high chance of PATH collision with another tool; conveys nothing about what it does. |
| `brewhs`  | "bruce" / "brews"  | **Chosen.** Keeps "brew" prefix (discoverable + thematic), adds "hs" for hop-search. Rhymes with "bruce" — mascot-ready. |
| `brewsh`  | "brewsh" / "brush" | Runner-up. Close to `brew sh` visually, risks "typo of `brew`" confusion. |

## Non-goals

- **No** renaming the PyPI package. It stays `brew-hop-search`.
- **No** renaming the canonical binary. `brew-hop-search` is always installed,
  never deprecated, always valid in docs and scripts.
- **No** hard dependency on `brewhs` existing — docs, CI, and the man page all
  keep using `brew-hop-search`. `brewhs` is a convenience alias.

## Design

### PyPI (`pyproject.toml`)

A second entry under `[project.scripts]` costs nothing — it becomes an extra
console entry point pointing at the same function:

```toml
[project.scripts]
brew-hop-search = "brew_hop_search.cli:main"
brewhs          = "brew_hop_search.cli:main"
```

`uv tool install brew-hop-search` (or `pip install`) then drops both on PATH.
No runtime cost, no packaging complexity.

### brew subcommand: `brew hs` (0.3.9)

`brew <name>` runs any executable called `brew-<name>` found on PATH (brew's
external-command mechanism), so `brew hop-search` has worked since the first
release for free. The hyphen matters: `brewhs` is a standalone alias and does
**not** make `brew hs` work. A third entry point does:

```toml
brew-hs = "brew_hop_search.cli:main"
```

Request (feature-requests.txt 2026-11-08): "besides brew-hop-search available
through brew subcommands, brew-hs should make hs subcommand available".

Known gap: `bin/brew` passes only `HOMEBREW_*` variables to external
commands, so `BREW_HOP_SEARCH_*` settings do not reach `brew hs` until the
`HOMEBREW_HOP_*` twins from config-layers (feat/peek) land. Config file
settings are unaffected.

### Homebrew formula

Symlinks in `install`:

```ruby
def install
  virtualenv_install_with_resources
  bin.install_symlink "brew-hop-search" => "brewhs"
  bin.install_symlink "brew-hop-search" => "brew-hs"
end
```

Not yet wired (tap formula still pins an older tarball URL + placeholder
sha256). Follow-on work when the formula is next refreshed.

### argv[0] awareness (future)

The CLI currently hard-codes `prog="brew-hop-search"` in the argparse parser.
Switching to `prog=Path(sys.argv[0]).name` would make `brewhs --help` render
`brewhs` in usage lines. One-line change; deferred until someone actually runs
`brewhs --help` and notices.

## Marketing / branding notes (non-normative)

These are **vibes-only** notes to keep dev mental coherence, not product
commitments. File under "things we agree on if we ever write a landing page".

- `brewhs` ≈ "bruce" is the **mascot name**. Finding Nemo's Bruce the shark:
  *"FOSS are friends, not food."* The joke:
  - Homebrew is the ocean. Formulae and casks are fish.
  - `brewhs` is the friendly shark who helps you find them without eating them
    (no network calls by default, no mutations to your brew state).
  - Tagline candidate: *"brewhs — FOSS are friends, not food."*
- Don't put this in the README yet. Put it in a `docs/BRAND.md` if/when there's
  a reason to. Premature branding is cringe; having the idea written down so it
  doesn't dissolve is not.

## Risks / open questions

- **PATH collision**: `brewhs` is unusual enough to be likely-free on most
  systems. If a user reports a collision, they can `rm $(which brewhs)` or
  uninstall whichever other tool shipped it.
- **Homebrew policy**: if upstreaming to homebrew-core is ever a goal, the
  symlink may need to be dropped. Personal tap: no issue.
- **Shell completion**: completions generated for `brew-hop-search` won't
  trigger on `brewhs` unless duplicated. Low priority; document as a known gap
  when completion ships.
- **Man page**: `man brewhs` will not work until either a `.so brew-hop-search.1`
  include is shipped or the formula symlinks the man page.

## Rollout

1. ✅ Add `brewhs` entry to `[project.scripts]` (ships in 0.3.2).
2. Watch for collision reports.
3. Formula symlink on next tap refresh.
4. README gets a one-line "also installs as `brewhs`" note under Install. No
   rewrite of existing examples — `brew-hop-search` stays canonical.
