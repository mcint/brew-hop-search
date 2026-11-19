# `.beads/` — issue tracking with br

This repository tracks issues with **br**
([beads_rust](https://github.com/Dicklesworthstone/beads_rust)), a
local-first issue tracker: SQLite for queries, `issues.jsonl` in git as the
source of truth. **bv** (beads viewer) is the TUI over the same data.
The directory is named `.beads/` because that is where br keeps its
workspace.

## Everyday commands

```sh
br ready                               # open, unblocked work
br show <id>                           # one issue
br create "Title" -t bug -p 2          # file an issue
br update <id> --status in_progress    # claim it
br close <id>                          # done
br sync --flush-only                   # write the JSONL; br never runs git
git add .beads/ && git commit          # commit it yourself
bv                                     # browse in the TUI
```

`br --help` lists the rest (`dep`, `label`, `search`, `stale`, `graph`, …).
Agent instructions are in `AGENTS.md`.

## What is tracked

| file | tracked | what |
|---|---|---|
| `issues.jsonl` | yes | every issue, one JSON object per line |
| `config.yaml`, `metadata.json` | yes | workspace settings |
| `interactions.jsonl` | yes | append-only audit log |
| `*.db`, caches, locks | no | local, rebuilt from the JSONL (see `.gitignore`) |
