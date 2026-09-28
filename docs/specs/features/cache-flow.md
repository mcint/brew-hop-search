# cache-flow

Offline-first read path: respond from cache immediately, refresh in
background, return to the shell promptly (a brief grace window catches
fast refreshes; slow ones keep running detached).

## Purpose

Make `bhs <query>`, `bhs -i`, and `bhs -O` feel instant on repeated use,
even hours or days later. The cache is the primary source of truth at
read time; the network is a *post-print* concern.

The shape: `(invoke) → (issue local + remote in parallel) → (print local
results, flush) → (brief grace poll: print ✓/✗ line if bg finishes
quickly, else "still updating in background" footer) → (exit; bg keeps
running in its own session)`.

## Input

This isn't a flag — it's the default behavior for **search**, **`-i`**,
**`-O`**. Existing flags continue to apply:

- `--refresh[=DUR]` / `--fresh[=DUR]` (alias) — force or conditional
  *foreground* refresh (legacy behavior; pre-empts cache-first)
- `--refresh=KIND[,KIND...]` — refresh a subset only; KIND ∈
  `{index, installed, outdated, taps, local, all}` (see `--refresh` below)
- `--stale DUR` — override the threshold beyond which a cache is
  considered stale enough to background-refresh, for every source the
  invocation touches
- `--stale KIND:DUR[,KIND:DUR]` — same, per source; KIND ∈
  `{index, installed, taps, local, all}` (short `x i t l`, matching
  `--refresh`). `outdated` is not a stale kind — set `index`/`installed`.
- `-l` / `--local` — *no* network, no background refresh; pure cache
- `--offline` — adverb form of the same promise for *any* source: no
  network, no `brew` subprocess, no bg refresh; missing cache is an
  error, not a fetch. Conflicts with `--refresh`.
- `-q` / `--quiet` — disables the trailing status line (results only)

### `--refresh` selector

Bare `--refresh` and `--refresh=DUR` keep their existing meaning. The
new comma-separated form picks which sources to act on:

```
--refresh                # force-refresh whichever sources this command touches
--refresh=index          # API formulae+casks only
--refresh=installed      # rerun `brew info --json=v2 --installed`
--refresh=index,installed
--refresh=all            # everything: index, installed, taps, local
--refresh=6h             # legacy: refresh if older than 6h (any KIND that's stale)
```

Parser rule: if the value matches `^[0-9]+[smhd]?(.*)?$` it's a duration;
otherwise it's a comma-separated KIND list. Mixing
(`--refresh=installed,6h`) is rejected with a clear error.

#### Short forms

For interactive use, single-letter shortcuts are accepted:

| short | canonical    |
|-------|--------------|
| `x`   | `index`      |
| `i`   | `installed`  |
| `t`   | `taps`       |
| `tap` | `taps`       |
| `l`   | `local`      |

`all` is spelled out (an `a` shortcut would collide with a future
`api` kind). Long and short forms freely mix: `--refresh=i,taps,l`
parses to `{installed, taps, local}`.

### `--refresh=KIND` as a standalone command

`bhs --refresh=KIND[,...]` with no query and no source flag is a
*"load these caches"* invocation: each requested kind is refreshed
sequentially, a one-line status (`# [cache] taps  ✓ 0.3s`) is printed
to stderr per kind, and the process exits. `-v` adds a `# [cache]
total Xs` footer.

```
bhs --refresh=all          # warm everything in one go
bhs --refresh=taps         # rescan local taps only
bhs --refresh=index,local  # API + offline cache
```

This is distinct from `bhs --refresh foo` (force-refresh whatever
sources `foo`'s search touches, then print results). Without a query
or source flag, `--refresh=DUR` and bare `--refresh` still fall
through to the usage hint — those forms are modifiers, not commands.

When combined with a query or source flag, `--refresh=KIND` is also
honored for kinds that the invocation wouldn't otherwise touch:
`bhs --refresh=taps foo` runs the API search for `foo` *and* refreshes
the taps cache as a side effect. (Previously, the explicit kind was
silently ignored unless the matching source flag was also set.)

**Future direction (not yet implemented):** per-kind durations in one
invocation (`--refresh=local:5m,taps:5s`) are intentionally still
rejected by the parser. Different TTLs require separate invocations
today; the syntax is a deliberate spec change that will need its own
precedence rules vs `--stale`, env vars, and config defaults.

**Future direction:** parallel refresh with return-fast semantics
(`bhs --refresh=all &` style without the `&`) — kick off every
refresh, return control immediately, print completion lines async.
Today the standalone command is sequential and blocking.

## Output

### The trailing status line

After the result body is printed and stdout is flushed, the next
behavior depends on whether a background refresh is in flight.

**No bg refresh** (cache fresh enough, `-l`, or refresh skipped): no
trailing line. Exit immediately.

**Bg refresh in flight**, TTY: we poll the bg sentinel for a short
grace window (default 2s). Fast refreshes (warm `brew info`, a
formulae.brew.sh fetch on a good network) finish inside the window;
slow ones don't, and we return to the shell anyway.

```
  python  3.13.2  Interpreted, interactive, object-oriented programming language  │ ...
  …  [more results]
  # [cache] updating index … (^C to skip)
```

The `# [cache] updating <kinds> …` line is written to stderr in dim
color. When the bg refresh completes inside the grace window, the line
is overwritten in place with one of:

- `# [cache] index ✓ matches cache  (1.2s)` — refresh ran, results
  unchanged
- `# [cache] index ↻ updated, results may differ — re-run  (1.2s)` —
  refresh ran, top-N results differ from what was just printed
- `# [cache] index ✗ refresh failed (network: …)  (8.3s)` — refresh
  errored; cached results were still served

When the grace window expires without a sentinel, the line is
overwritten with `# [cache] <kinds> still updating in background` and
the CLI exits — the bg subprocess keeps running in its own session and
the next invocation picks up the refreshed cache.

`<kinds>` is comma-joined (`index`, `installed`, `outdated`); typically
just one for search and `-i`, two for `-O` if both `index` and
`installed` are stale.

**Bg refresh in flight**, non-TTY: no status line at all. The bg
process is still launched and detached, but the terminal returns
immediately so `bhs … | grep …` doesn't block.

**Rationale for the short grace window.** Earlier this spec called for
holding the terminal open until the bg refresh finished (capped at the
bg subprocess timeout, e.g. 300s for `brew info`). In practice a cold
`brew info --json=v2 --installed` can take 30-60s on large installs,
and the held-open terminal felt like a hang — defeating the
"results-first" promise. The grace window keeps the fast-path UX
(inline ✓ when the bg finishes quickly) without the worst-case hold.

### Reminder line

Every search, `-i` and `-O` ends with one stderr comment describing the
caches it was just served from, and how to refresh them:

```
  # [cache] index 2h old, 4h left  [--refresh]
  # [cache] installed 12m old, 48m left, changed · taps <1m old, 59m left  [--refresh]
  # [cache] local 1d1h old, stale  [--refresh]
```

One clause per *source* (formula+cask collapse to `index`; `installed_*`
to `installed`; `local_*` to `local`; `tap` to `taps`): age, then time
until the TTL calls it stale (`stale` once it has), then `changed` when a
witness mtime says brew touched the source since we indexed. The
`[--refresh]` tail is the whole reason the line exists — nobody should
have to remember the flag. Sources with no cache are omitted.

Policy: default level prints it only when stderr is a TTY; `-v` and up
always; `-q` never. Format flags (`--json`, `--csv`, …) never print it;
`--json` carries the same facts as `meta.cache` (see ENVELOPE.md).

It precedes the trailing `# [cache] updating …` line when a bg refresh is
in flight: the reminder says what you got, the trailing line says what is
happening about it.

#### Duration style (experimental)

`BREW_HOP_SEARCH_DURATION=clock` swaps the word form for a signed clock,
in the reminder line and the `-C` age / fresh-for columns:

```
  # [cache] index -0:40:12 +5:19:48 · installed -0:46:10 +0:13:50 changed  [--refresh]
  # [cache] local -1d 01:00 stale  [--refresh]
```

`-` is age, `+` is time until stale; the signs carry the meaning, so
the commas go. Tiers follow what the eye needs at each range: under a
day `h:mm:ss` (exact, no unit letters to parse); one to seven days
`3d 14:05` (morning-vs-evening still matters); then `2w3d`, `3M`
(30-day months), `1y1M`. Default stays `compact` (`40m old, 5h19m
left`). A trial: if it earns its keep it graduates to config
(`[display] duration = "clock"`) and a flag; if not, it goes.

### Differs/matches detection

The "matches cache" / "may differ" determination compares the **set of
top-N (name, version) tuples** that were just printed against the same
query re-evaluated against the freshly-refreshed cache. If the tuple
list is identical (order included), report `matches`. Otherwise report
`may differ` — without re-printing, since the user can just re-run.

For `-i`, the comparison is `set(installed names + versions)` — we don't
care about ordering for the installed list.

For `-O`, the comparison is `set((name, current_version))` of the
outdated list.

### Timing

Wall-clock duration of the bg refresh is recorded and printed in the
trailing line. Additionally:

- At `-v`: also log to stderr `# [cache] timing  index=1.2s`
- At `-vv`: log per-step `# [cache] timing  fetch=0.9s parse=0.2s
  index=0.1s`
- Always: append a row to `~/.cache/brew-hop-search/refresh.log` with
  `<iso-timestamp>\t<kind>\t<duration_ms>\t<ok|fail>` for later
  analysis. Caps at 1MB (truncate-oldest on rotation).

### `^C` during the trailing line

When the user `^C`s while the trailing line is held open, the bg
process is **not** killed (it owns its own session via
`start_new_session=True` already). The CLI exits cleanly with exit
code 0. The next invocation will pick up the refreshed cache when the
bg job finishes on its own.

## Cache decision matrix

| State                        | -l / --offline | search default                        | --refresh             | --refresh=KIND        |
|------------------------------|-----|---------------------------------------|-----------------------|-----------------------|
| Fresh cache                  | use | use, no bg                            | sync refresh, then print | sync refresh selected; print |
| Stale cache (age > stale, **or witness moved**) | use | print cache, bg refresh, trailing line | sync refresh, then print | sync refresh selected; print |
| No cache                     | err | sync refresh, then print              | sync refresh, then print | sync refresh selected, then print |

Every source takes the bg row: `index` (formulae.brew.sh), `installed`
(`brew info`), `taps` (Library/Taps rescan) and `local` (brew's api/
cache). The offline three share one detached runner
(`sources/_bg.py`); `index` keeps its own because it carries a URL.

## Witness mtimes

A TTL guesses. Directory mtimes know. Each offline source names a few
*witness paths* that brew touches whenever it mutates that source:

| source    | witness paths                                              | moved by |
|-----------|------------------------------------------------------------|----------|
| installed | `<prefix>/opt`, `Cellar`, `Caskroom`                       | install, upgrade, remove (all relink under `opt/`); casks land in `Caskroom/` |
| taps      | `Library/Taps`, each `<user>/<tap>` dir, its `.git/FETCH_HEAD` | `brew tap`, `untap` (parents); `brew update` (FETCH_HEAD) |
| local     | `$(brew --cache)/api`, `api/formula`, `api/cask`           | brew writing per-formula JSON on `brew info`/`install` |
| index     | none — remote                                              | TTL only |

At index time the source samples the max mtime over its witnesses —
*before* it reads anything, so a change that lands during a slow `brew
info` shows up as moved on the next read — and stamps it into
`_meta.witness` (schema 2). Every later read stats the same paths: a
few dozen `stat` calls, no subprocess. Roots come from
`HOMEBREW_PREFIX` / `HOMEBREW_REPOSITORY` / `HOMEBREW_CACHE` when set,
else from where the `brew` binary lives — asking brew would cost more
than the check saves.

If the live max is newer than the stamp, the source is stale: it takes
the **background** row of the matrix above, never the blocking one. TTL
stays as the fallback for whatever a witness can't see (a hand-edited
`.rb` inside an existing tap moves the file, not the tap dir).

Unknown is not changed. A NULL stamp (pre-schema-2 DB, no discoverable
roots) or a vanished witness reads as "no change", so an upgrade never
thrashes; the first refresh after upgrading writes the stamp.

`-C` shows the witness state per source; `-C -v` names the paths. The
reminder line (next section) says `changed` when a witness moved.

`--offline` + any `--refresh` form is rejected at parse time
(`--offline and --refresh conflict. Drop one.`).

*"Sync refresh, then print"* keeps the existing first-run UX — there's
nothing to print until the cache exists.

## `-i` specifics

- `-i` always serves from cache when the cache exists, regardless of
  age, by default.
- The `brew info --json=v2 --installed` foreground call is bumped from
  60s to **300s** when run as a background refresh — slow brew
  invocations no longer block the user.
- `--refresh=installed` (or bare `--refresh` while `-i` is active) reverts
  to the synchronous behavior.
- Cache-stale threshold for `-i` is `STALE_INSTALLED` (default 1h).

## `-O` specifics

- `-O` reads the existing `formula`, `cask`, `installed_*` caches
  without forcing refresh. If both index and installed are within their
  stale windows, `-O` is fully offline.
- If either is stale, the relevant kinds are bg-refreshed after the
  outdated list prints. Trailing status reports `<kinds>` accordingly.
- `--brew-verify` keeps its current synchronous behavior — by user
  intent it's the slow, authoritative path.

## `-C` specifics

The cache-status display gains a "ttl" column showing the threshold at
which each source will be considered stale on the next read:

```
  formula  8306  1h12m ago  ttl 6h        fts  30MB json
  cask     7596  1h12m ago  ttl 6h        fts  14MB json
  installed:f  460  1h11m ago  ttl 1h
```

At `-v`, append the resolution layer (`default` / `env` / `config`):

```
  formula  8306  1h12m ago  ttl 6h (default)        fts  30MB json
  installed:f  460  1h11m ago  ttl 2s (env: BREW_HOP_SEARCH_STALE_INSTALLED)
```

At `-vv`, add the next-refresh ETA:

```
  formula  8306  1h12m ago  ttl 6h (default)  fresh for 4h47m  fts  30MB json
```

Witness state (§ Witness mtimes) rides the same row for the offline
sources. Default flags only a moved witness; `-v` always names the
state; `-vv` lists the witness paths once per kind (first three, then
`(+N more)`):

```
  installed:f  460  1h11m ago  ttl 1h  changed                    # default
  installed:f  460  1h11m ago  ttl 1h (default)  witness changed  # -v
  taps         912  3m ago     ttl 1h (default)  witness ok
  local:f      130  2d ago     ttl 1h (default)  witness none     # pre-schema-2 stamp
      witness: /opt/homebrew/opt, /opt/homebrew/Cellar, /opt/homebrew/Caskroom
```

`-C --json` adds `"witness": {stored, current, changed, paths}` to each
offline source; the remote index has no key.

## Examples

```sh
# Default behavior — answer from cache, refresh in background.
brew-hop-search python                      # search
brew-hop-search -i                          # installed
brew-hop-search -O                          # outdated

# Pure offline (no network, no bg refresh).
brew-hop-search -l python
brew-hop-search -i -l

# Force refresh, then print fresh results.
brew-hop-search --refresh python            # all sources this command touches
brew-hop-search --refresh=installed -i      # just `brew info` rerun
brew-hop-search --refresh=index,installed -O

# Test 1-second TTLs (12-factor):
BREW_HOP_SEARCH_STALE_API=1s brew-hop-search python

# Quiet pipeline use — no trailing status line, no bg blocking.
brew-hop-search -q python | fzf
```

## Implementation Notes

- The bg refresh is already non-blocking in `api.background_refresh`
  (`subprocess.Popen` with `start_new_session=True`). The new piece is
  the **trailing status thread** that polls a sentinel file written by
  the bg process on completion.
- Sentinel mechanism: bg process writes
  `~/.cache/brew-hop-search/.refresh-<kind>.done` (with duration + ok
  flag) at end of run. Foreground process polls for this file until
  it appears, `^C` is pressed, or the grace window expires. Default
  poll interval 100ms; default grace window 2s (see "trailing status
  line" above for the rationale).
- The "results may differ" comparison runs the same `search()` call a
  second time after refresh and diffs the (name, version) tuples. Cost
  is one extra FTS query; negligible.
- Quiet mode (`-q`) and non-TTY runs short-circuit the trailing line
  entirely but still launch the bg refresh.

## Spec status

**Specced:** offline-first read path, trailing status line semantics,
`--refresh=KIND` selector, `-C` ttl column, env-var TTL overrides
(landed separately in `defaults.py`).

**Not yet repaved:** the bg-refresh sentinel file mechanism described
above is the working plan; if implementation finds a cleaner approach
(e.g. a shared SQLite "refresh_progress" table), this spec is updated
to match before the implementation lands.
