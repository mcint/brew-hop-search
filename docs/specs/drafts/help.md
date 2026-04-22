# help — future ideas (draft)

Captures unimplemented directions for the help system. The implemented
behavior lives in [`../features/help.md`](../features/help.md).

## Long-form per-flag help colocated with code

Argparse's `help=` stays the one-liner; a module-level `HELP` dict keyed by
section/flag carries the long form used by `--help=<flag>`:

```python
HELP = {
    "outdated": """\
-O / --outdated — detect packages where installed version != current.

  brew-hop-search -O                 # fast local comparison
  brew-hop-search -O -c              # casks only
  brew-hop-search -O --brew-verify   # diff vs brew's authoritative result

See also: -H (version history), --help=cache.
""",
    ...
}
```

Declarative + colocated → observable at the CLI *and* testable alongside
other snapshots.

## Doc-as-test linking spec ↔ CLI

Per-flag `HELP[...]` blocks become the substrate for generating (or
cross-checking) `docs/specs/features/*.md`: spec and CLI stay in lockstep
instead of drifting. A doc-as-test check verifies the `HELP[k]` snapshot
matches the spec section so neither can edit without the other noticing.

## Open questions

- Should contextual `-h <flag>...` include a composed example at the top
  (e.g. `brew-hop-search -O -f python`) inferred from the parsed flags?
  Risk: misleading for mutually-exclusive or nonsensical combinations.
- Grouped contextual output: if all parsed flags are in the same argparse
  group (`sources`, `output`, …), prepend the group title as a header.
- `--help=<dest>` (e.g. `--help=casks`) currently works via `_action_matches`
  checking `action.dest`. Worth documenting explicitly as an alias form?
