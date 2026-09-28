---
title: peek — glance at a tap where it lives, without `brew tap`
date: 2026-09-28
kind: draft-spec
status: draft — awaiting user review before writing-plans
tldr: >
  `bhs peek user/repo` lists a tap's formulae and casks straight from
  GitHub: two scoped requests (repo metadata + one tarball), parsed with
  the existing .rb parser, printed in the house format with the
  normalized brew slug and local cross-references (tapped / installed).
  The verbosity ladder teaches: -v the URLs, -vv the tree, -vvv the
  curl|tar|jq you could run yourself. Every remote request is logged in
  the DB (30d) and the listing is cached (15m); `bhs peek` alone shows
  what you've peeked before. First verb of the Option B subcommand layer.
---

# peek — glance at a tap where it lives, without `brew tap`

`brew tap` clones a repo into `Library/Taps` and, on brew ≥ 6, asks
you to trust it. Deciding *whether* to do that is exactly when you
want to see what's in it — and today the only way is to tap it. `bhs
peek` looks first: it fetches the tap from its forge, lists what it
ships, tells you what you already have, and shows you how it looked.

## Status

**Draft** — from `feature-requests.txt` 2026-09-15 ("list formulas in
brew taps without installing … read the descriptions … from the url /
gh short description … `-v`/`-vv`/`-vvv` showing the urls, file
structure, `curl | jq` equivalent, to educate myself and other users")
and the 2026-09-28 conversation (targets, audit log, subcommand shape,
caching). Bead bhs-u7e. This is the **first verb of Option B** in
[cli-vocabulary](cli-vocabulary.md): it lands the verb dispatch, and
the existing flag surface stays untouched. The wider "inspect a thing
where it lives" family (§ Later verbs) is noted, not designed.

## Purpose

Three things, in order of how often they'll matter:

1. **Look before you tap.** What's in `steipete/tap`? Is it three
   formulae or thirty? Do the descriptions match the README's pitch?
   Is anything in there already on my machine under another name?
2. **Learn how brew's world is laid out.** A tap is a git repo with
   `Formula/*.rb` and `Casks/*.rb`. The GitHub API will hand you the
   tree and a tarball. `peek -vvv` prints the exact `curl`/`tar`/`jq`
   lines it is the equivalent of, so the tool teaches its own
   plumbing instead of hiding it.
3. **Be a good citizen, visibly.** Every remote request `peek` makes
   is scoped (two per tap), identified (our User-Agent), and recorded
   in the DB where `-C -v` can show it. "Having looked at something
   before is signal" — so what you peeked, and when, is kept.

## Design

### Invocation and the subcommand layer

```
bhs peek <target> [query] [-f|-c] [--refresh] [--offline] [-v…] [--json]
bhs peek                       # what have I peeked, and when
```

`peek` is a **verb**: the first word of argv. The CLI gains a verb
dispatch that is deliberately thin — if `argv[0]` is a known verb, a
per-verb argparse parser handles the rest; otherwise the existing flat
parser runs exactly as today. No flag is renamed, aliased or hidden
by this spec. `peek` appears in `--help` under a new `verbs:` group;
`bhs peek --help` is its own screen ([help](help.md) tiers apply).

`peek` is not draft-gated (`BREW_HOP_SEARCH_DRAFT=1` is not required):
it changes no existing behavior, and gating it would hide the one
thing this release adds. The staging note in
`sessions/2026-09-13-requests.md` § C1 applied to verbs that
*duplicate* flags; `peek` duplicates nothing.

`query` filters the listing with the same [search syntax](search-syntax.md)
as `-t`; `-f`/`-c` narrow the kind, as everywhere.

### Targets and normalization

Accepted spellings, in the order they're tried:

| spelling                                   | resolves to                         |
|--------------------------------------------|-------------------------------------|
| `user/repo`                                | github.com/user/**homebrew-**repo, then github.com/user/repo if that 404s |
| `user/homebrew-repo`                       | github.com/user/homebrew-repo       |
| `gh:user/repo`, `gh:user/homebrew-repo`    | same, explicit forge                |
| `https://github.com/user/repo[.git][/tree/BRANCH]` | that repo; `/tree/BRANCH` selects the ref |
| `git@github.com:user/repo.git`             | that repo (ssh form, read via API)  |
| any other `https://…` / `git@…` / `ssh://…` | **accepted by the grammar, refused in v1**: `peek: non-GitHub remotes not yet supported (bead)` |

Brew's own rule is that `user/repo` names the repo `homebrew-repo`;
people paste both forms, so both work. The output header always shows
the **normalized slug** — `user/repo`, the thing you'd pass to `brew
tap` and the thing the local `tap` table keys on — and, at `-v`, the
full URL and ref it resolved to. Exact-match cross-reference with
local state uses that slug, never the spelling the user typed.

### Fetching — scoped, identified, two requests

```
1. GET https://api.github.com/repos/{owner}/{repo}
      → default_branch, description, pushed_at, stargazers_count, archived
2. GET https://api.github.com/repos/{owner}/{repo}/tarball/{ref}
      → 302 to codeload.github.com → .tar.gz, read in memory
```

The tarball is the whole point: **one** request yields the file
structure *and* every `.rb`, so listing a tap costs the same two
requests whether it ships three formulae or three hundred. The
alternative (`git/trees?recursive=1` then one raw fetch per file)
is N+2 requests and is not used.

Members are filtered with the same rules `sources/taps.py` uses for
local taps: `Formula/**/*.rb`, `Casks/**/*.rb`, root `*.rb`; paths
containing `test`/`spec` skipped; kind by path; dedupe by
`(kind, name)` keeping the deepest path (the maintained copy). Each
`.rb` goes through `taps.parse_rb` — regex-level, no Ruby — so a peek
and a `-t` row for the same file agree.

Bounds, all in `defaults.py` and env-overridable:

| knob                          | default | env                             |
|-------------------------------|---------|---------------------------------|
| tarball size cap              | 20 MB   | `BREW_HOP_SEARCH_PEEK_MAX_MB`   |
| member count cap              | 2000    | `BREW_HOP_SEARCH_PEEK_MAX_FILES`|
| request timeout               | 10 s    | `BREW_HOP_SEARCH_API_TIMEOUT` (existing) |

Over a cap: stop, say so (`# [remote] tarball 34 MB > 20 MB cap —
BREW_HOP_SEARCH_PEEK_MAX_MB=40 to raise`), exit 1. A tap that big is
not a tap; it's worth a pause.

Auth: if `gh auth token` (the `gh` CLI, on PATH, already logged in)
returns a token, send it as `Authorization: Bearer`. Otherwise
anonymous — 60 requests/hour is 30 peeks, plenty. `GITHUB_TOKEN` in
the environment is honored first (12-factor, CI-friendly). No token
is ever stored by us. `-v` says which of the three applied
(`auth: gh` / `auth: env` / `auth: none`).

Transport is stdlib `urllib`, same as `sources/api.py`, with the
existing User-Agent. No new dependency.

### Output

Default (level 1), house format — the same `_section_header` / row
formatters as `-t`, so a peeked tap reads like a tapped one:

```
  # tap steipete/tap  ·  github.com/steipete/homebrew-tap  ·  pushed 3d ago  ·  not tapped
  # formulae (4)  • brew install steipete/tap/<name>
    goplaces     0.4.1  Google Places CLI                       │ https://github.com/steipete/goplaces
    peekaboo   ● 2.0.3  Screenshot tool for macOS               │ https://peekaboo.boo
    …
  # casks (1)  • brew install --cask steipete/tap/<name>
    vibetunnel   1.0.0  Terminal sharing app                    │ https://vibetunnel.sh
  # [remote] 2 requests · 41 KB · 0.6s · peeked just now  [--refresh]
```

- Header: normalized slug, forge host + repo, `pushed <age>` from the
  repo metadata, and the cross-reference: `tapped` (slug present in
  the local `tap` table) or `not tapped`; `archived` in red when the
  repo is.
- Rows: `●` marks a name that is in `installed_formula` /
  `installed_cask` ([installed-indicator](installed-indicator.md)).
  The `brew install` hint uses the slug, so it is copy-pasteable
  whether or not the tap is tapped (`brew install user/repo/name`
  taps on demand).
- Trailer: request count, bytes, wall-clock, and the cache age of
  this listing with the `[--refresh]` reminder — the
  [cache-flow](../features/cache-flow.md) reminder line, in
  `[remote]` clothing. `-q` drops headers and the trailer, as
  everywhere.
- Empty: `# tap x/y · … · 0 formulae, 0 casks` and a `-v` hint listing
  the top-level entries seen (probably a tap in the wrong layout).

`--json` wraps `{tap: {...repo metadata...}, formulae: [...], casks:
[...]}` in the [envelope](../ENVELOPE.md), `command: "peek"`, with
`meta.remote` = the request log rows for this invocation and
`meta.cache` as for search. `-g`/`--csv`/`--tsv`/`--table` work on
the rows exactly as for `-t`.

### Verbosity ladder — the teaching axis

The [OUTPUT](../OUTPUT.md) levels, with `peek`'s additions. Everything
below the results goes to **stderr** so `--json | jq` stays clean.

| level | adds |
|-------|------|
| `-v`  | one line per request as it happens: `# [remote] GET api.github.com/repos/steipete/homebrew-tap  200  1.2 KB  0.21s  auth: gh`; the resolved URL + ref in the header; `t` source-indicator column on rows |
| `-vv` | the tree as seen: `# [tree] 14 entries: Formula/ (4 .rb), Casks/ (1 .rb), README.md, .github/ … skipped 2 (test/)`; per-file parse notes when a field is missing (`# [parse] Formula/foo.rb: no desc`) |
| `-vvv`| the equivalent you could paste into a shell, one block, correct quoting, no secrets: |

```
  # [equiv]
  #   curl -sS -H 'User-Agent: brew-hop-search/0.4' https://api.github.com/repos/steipete/homebrew-tap \
  #     | jq '{default_branch, description, pushed_at, archived}'
  #   curl -sSL -H 'User-Agent: brew-hop-search/0.4' https://api.github.com/repos/steipete/homebrew-tap/tarball/main \
  #     | tar tzf - | grep -E '(^|/)(Formula|Casks)/.*\.rb$'
  #   # then: tar xzf - -O '*/Formula/goplaces.rb' | grep -E '^\s*(desc|homepage|version|url) '
```

If a token was used, the `-vvv` block shows `-H "Authorization:
Bearer $GITHUB_TOKEN"` — the variable, never the value.

This ladder is the executable form of the feature request's "as part
of educating myself, and other users". It is also why the tarball
route wins over the trees API: the equivalent is three lines a person
can read.

### Persistence — the listing

A **separate** table, not rows in `tap`: local taps are searched by
`-t`, and a peek must never leak into that. Schema (SCHEMA.md gets
the entry when this ships):

```sql
CREATE TABLE [peek] (
   [slug]       TEXT,     -- normalized user/repo
   [kind]       TEXT,     -- formula | cask
   [name]       TEXT,
   [desc] TEXT, [homepage] TEXT, [version] TEXT, [url] TEXT, [path] TEXT,
   [raw]        TEXT,     -- parse_rb dict
   PRIMARY KEY (slug, kind, name)
);
-- `_meta` row per slug: kind = "peek:<slug>", updated_at = peeked_at,
-- count = rows, value = JSON repo metadata (branch, pushed_at, …)
```

TTL 15 minutes (`BREW_HOP_SEARCH_STALE_PEEK`), because the question
"what's in it" rarely changes within a sitting but the user may well
be watching a maintainer push. Within TTL: served from the table,
trailer says `peeked 4m ago`. `--refresh`: fetch regardless.
`--offline`: serve the table or fail with the usual `--offline: no
cache for peek:user/repo` — no request. Stale-and-present follows
cache-flow: serve, background-refresh, trailing line. (The `_bg`
runner gains a `peek:<slug>` kind.)

`bhs peek` with no target lists `_meta` rows with kind `peek:*`:

```
  # peeked (3)
    steipete/tap        4 formulae, 1 cask   4m ago    tapped
    gastownhall/beads   2 formulae           2d ago    tapped
    openai/tools        6 formulae           3w ago    not tapped
```

That is the "have I looked at this before" signal, and it costs
nothing. Rows older than 90 days are pruned on write
(`BREW_HOP_SEARCH_PEEK_KEEP`).

### Persistence — the audit log

```sql
CREATE TABLE [remote_log] (
   [id] INTEGER PRIMARY KEY,
   [ts] FLOAT, [verb] TEXT, [url] TEXT, [status] INTEGER,
   [bytes] INTEGER, [duration_ms] INTEGER, [auth] TEXT   -- gh | env | none
);
```

One row per request `peek` makes, including failures (status 0 for
transport errors). Not the API index fetches — those already have
`refresh.log`; this log is for the requests a *user action* caused
against a *third party*. 30-day retention (`BREW_HOP_SEARCH_REMOTE_LOG_KEEP`),
pruned on write. Surfaced by `-C`:

```
  remote   17 requests, last 4m ago (steipete/tap)        # -C
  remote   17 requests / 30d, 0 failed, 212 KB, auth: gh  # -C -v
       last 5: … one line each …                          # -C -vv
```

and in `-C --json` as `remote: {count, failed, bytes, last, …}`.
Nothing here leaves the machine; the point is that the user can see
what the tool did on their behalf.

### Errors

| condition | message (stderr, exit 1 unless noted) |
|-----------|----------------------------------------|
| 404 both spellings | `peek: no such tap on GitHub: user/homebrew-repo (also tried user/repo)` |
| 403 rate-limited | `peek: GitHub rate limit hit, resets in 42m — \`gh auth login\` raises it to 5000/h` |
| 401 with token | `peek: GitHub rejected the token (auth: env) — check GITHUB_TOKEN` |
| no network, cache present | serve cache, trailer `peeked 3h ago · offline`, exit 0 |
| no network, no cache | `peek: cannot reach api.github.com and nothing cached for user/repo` |
| over a cap | as § Fetching |
| non-GitHub remote | `peek: non-GitHub remotes not yet supported (see bead)` |

### Later verbs (named, not designed)

The 2026-09-28 conversation sketched a family; `peek` leaves room by
making its target a **noun with an optional type prefix**, so these
can arrive without re-spelling the verb:

- `peek formula:NAME` / `peek cask:NAME` — the formula's own repo,
  README length, age, recent commit cadence: cheap quality proxies
  that are expensive to fake.
- `peek cask:NAME --versions` — older version/sha256 pairs from the
  cask's git history (pairs with [index-git-history](index-git-history.md)).
- `check` — validate `.rb` files (local or peeked) against the brew
  formula/cask DSL shape; report unknown stanzas and deprecated
  forms. Different verb: it judges, `peek` looks.
- name conflicts across `-f`/`-c`/`-t`/`-l` — a `conflicts` view,
  or a `-C -vv` section; either way not `peek`.
- non-GitHub remotes via `git clone --depth 1` into the cache dir.

None of these are in v1. They are here so the target grammar
(`[type:]name-or-slug-or-url`) and the `remote_log` table don't need
to change when they come.

## Examples

```sh
bhs peek steipete/tap                 # what's in it, am I using any of it
bhs peek gh:openai/tools -f            # formulae only
bhs peek https://github.com/borkdude/homebrew-brew/tree/main clj
bhs peek steipete/tap -vvv 2>&1 | less # learn the plumbing
bhs peek --json openai/tools | jq '.formulae[].name'
bhs peek                               # what have I peeked lately
bhs peek --offline steipete/tap        # from the table, no request
bhs -C -v                              # how many requests, to whom, when
```

## Testing

Red-green, expect/snapshot, no network in tests:

- **Grammar**: a table test over every spelling in § Targets → `(owner,
  repo_candidates, ref, forge)`; non-GitHub → refusal.
- **Fetch**: `urllib` opener monkeypatched with a fake that serves a
  canned repo JSON and a tarball built in the test from a synthetic
  tap tree (reuse `tests/test_taps.py`'s layout). Asserts: exactly two
  requests; 404-then-retry order; headers (UA, auth precedence
  env > gh > none); cap enforcement.
- **Output**: snapshots at levels 0–3 and `--json`, from the fake
  tarball; `●` and `tapped` from a seeded DB; the `-vvv` equiv block
  never contains a token value.
- **Persistence**: table round-trip, TTL served vs refetched,
  `--offline`, `bhs peek` listing order (newest first), pruning.
- **Audit**: one `remote_log` row per request incl. a failure; `-C`
  count line; 30-day prune.
- **Dispatch**: `bhs peek …` reaches the verb; `bhs python`, `bhs -i`
  unchanged (existing snapshots stay green); `bhs peek --help`
  snapshot.
