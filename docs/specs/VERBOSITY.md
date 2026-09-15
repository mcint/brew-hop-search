---
title: Verbosity ladder — what each -v level owes the user
date: 2026-09-14
kind: spec
status: living
tldr: >
  A user should be able to resolve most confusion by adding one `v`, most
  of the rest with `vv`, and satisfy curiosity with `vvv`, on any command,
  with the same kind of thing appearing at the same level every time. This
  document enumerates, per command and per level, what is shown today and
  what should be, so the ladder stays consistent as verbs are added. It is
  a living document: edit it when a level gains or loses a line.
---

# Verbosity ladder

## The principle

`-v` is the diagnosis mechanism. Not a firehose, not a debug switch: a
**graduated invitation**. Each step answers a predictable question:

| Level | Flag | The question it answers | Character |
|---|---|---|---|
| 0 | `-q` | *(none — machine output)* | bare results, exit code carries meaning |
| 1 | default | "what did I get?" | human-optimal; one hint line max |
| 2 | `-v` | "**where** did this come from, and **how fresh** is it?" | provenance: source tags, cache age, what was skipped, what fired implicitly |
| 3 | `-vv` | "**what did the tool do** to get it?" | per-source stats, per-step timing, the commands it ran, the decisions it made |
| 4 | `-vvv` | "**show me everything**" | raw material: argv of subprocesses, env layer that won for each setting, paths, sentinel files, SQL |

Three rules keep the ladder habit-forming:

1. **Same kind of thing, same level, every verb.** Cache age is a `-v`
   fact in search, `-O`, `-t`, `-C`. A skipped brew feature is a `-v`
   fact everywhere. If a verb puts provenance at `-vv`, that's a bug
   against this spec.
2. **Each level is a superset of the one below**, and adds to stderr,
   never to stdout, so `bhs -vv python | grep` still works. Machine
   formats (`--json`, `--csv`, ...) ignore the ladder entirely.
3. **The invitation is explicit.** When the tool knows more than it
   said, it says so in five words or fewer, once: `(-v for sources)`,
   `(-vv for per-step timing)`. Never nag; never repeat per row.

The habit we want: *confused → add a v → usually resolved → add another
→ almost always resolved → `-vvv` only when curious*. That only works if
the levels are predictable, which is why this file exists.

## Where the levels are computed

`verbose = 0 if -q else 1 + count(-v)`, in `cli.py` for search/-O/-C
and threaded into `display.py`. `--verbose=N` is documented in
OUTPUT.md but not implemented (open item below).

## Per-command enumeration (today → should)

Legend: ✓ shown today · ○ proposed · ✗ shown at the wrong level today.

### search (`bhs [query]`, any source flags)

| Level | Line | Status |
|---|---|---|
| 1 | section headers with counts + install hint | ✓ |
| 1 | `no results for 'q'` | ✓ |
| 1 | `-L is now -l` rename hint (stderr) | ✓ |
| 1 | trailing refresh line when a bg refresh is in flight | ✓ |
| 2 | `-- cache: <age>  searching <sources>` header | ✓ |
| 2 | source indicator column (`f c t i`) | ✓ |
| 2 | per-row tap date + trust (`official/trusted/untrusted`) | ✓ |
| 2 | `# [brew] skipped <feature>: needs X, have Y` | ✓ |
| 2 | `# [cli] implicit verb: search` (once subcommands land) | ○ |
| 2 | `# [cache] <kind> refreshed in bg (sentinel age)` | ○ |
| 3 | `[kind] searching N entries (cache <age> old)` per source | ✓ |
| 3 | which `--stale` value applied per source and its layer (flag/env/default) | ○ |
| 3 | FTS vs LIKE fallback per source, and why | ○ |
| 4 | the FTS5 MATCH expression per source | ○ |
| 4 | bg refresh argv + sentinel path | ○ |

### outdated (`-O`)

| Level | Line | Status |
|---|---|---|
| 1 | table of outdated, one hint line | ✓ |
| 2 | source ages for index + installed | ○ (currently only in `-C`) |
| 2 | `--brew-verify` diff summary (matches / differs counts) | ✓ |
| 3 | per-package reason (pinned, version-scheme, cask auto_updates) | ✓ partly; see `drafts/outdated-detail.md` |
| 4 | the `brew outdated --json=v2` argv and duration | ○ |

### cache status (`-C`)

| Level | Line | Status |
|---|---|---|
| 1 | db path/size, brew version, per-source count/age/ttl/fts | ✓ |
| 2 | ttl layer (`default` / `env: NAME`), gated feature list | ✓ |
| 3 | `fresh for <dur>` / `stale` per source | ✓ |
| 3 | last N refresh durations from `refresh.log` per kind | ○ |
| 4 | config file path and which keys it set; sentinel files present | ○ |

### standalone refresh (`--refresh=KIND`)

| Level | Line | Status |
|---|---|---|
| 1 | `# [cache] <kind> ✓ 0.42s` per kind | ✓ |
| 2 | `# [cache] total` | ✓ |
| 3 | entries indexed per kind; bytes downloaded | ○ |
| 4 | URL, ETag/Last-Modified if conditional GET lands | ○ |

### timing footer (`# [time]`, every command)

| Level | Line | Status |
|---|---|---|
| 1 | `# [time] <felt>` | ✓ |
| 2 | `+ bg <dur>` when a background refresh completed during the hold | ✓ |
| 3 | per-phase split (parse / ensure_cache / search / render) | ○ (see `drafts/timing.md`) |

### history (`-H`), version (`-V`)

`-V` already uses count semantics (`-VV` = commits + PyPI). That is the
same ladder shape applied to a verb's own output; keep it, and make
`-V -v` equivalent to `-VV` when subcommands land so there is one habit.

## Formats and the ladder

`--json` at any `-v` is identical: verbosity is a *human* affordance.
The provenance the ladder exposes at `-v` is *already* in the envelope
(`meta.sources`, ages), so a script never needs `-v`. If a `-v` line
carries a fact the envelope lacks, add it to the envelope first.

## Relation to traces (open exploration)

The ladder is *live* diagnosis. Its complement is *after-the-fact*
diagnosis: a run leaves a trace keyed by a short id, and the user can
re-read or re-filter it later (`bhs --trace <key>`, or the `bkt`-style
"cache the run, re-filter the output" habit, or ipython's `_10`). Every
line this spec assigns to `-vv`/`-vvv` is a candidate trace record; the
ladder decides what prints *now*, the trace keeps what printed *at all*.
See the seedbed cutting `ClaudeCollab/Cuttings/run-references.md`.

## Open items

- Implement `--verbose=N` or drop it from OUTPUT.md (one of the two).
- Add the `(-v for …)` invitation line: where exactly, and the rule for
  suppressing it after the user has used `-v` once in a session (a
  small marker in the cache dir, or never suppress — decide by trying).
- Decide whether level 4 exists as `-vvv` or as `--debug`; the ladder
  argues for `-vvv` so the habit is one key.
- Every new verb PR adds its rows to this file.
