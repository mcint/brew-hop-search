---
title: remote-tap — browse a tap's formulae without tapping it
date: 2026-10-27
revised: 2026-11-19 (rev 2, -tt)
kind: spec-draft
bead: bhs-vv6
tldr: >
  `bhs -tt=user/tap [query]` lists a tap's formulae and casks straight
  from GitHub (one tree-API call plus raw file fetches), parsed with the
  existing .rb regexes, cached in a `remote_tap` table under the taps TTL.
  `-t` stays local; doubling it means "look online". `=` names an exact
  tap; a bare term searches what is already known.
  Verbosity is the teaching surface: -v adds the repo blurb and counts,
  -vv shows every URL hit and the tree it saw, -vvv prints the curl | jq
  pipeline that reproduces the listing by hand.
---

# remote-tap

Browse what a tap offers, and read the descriptions, without `brew tap`
touching the machine. Input is the tap's short name or URL.

## Status

**Draft** — bead bhs-vv6. Sits beside [locations](locations.md): a
remote tap is a *source* that lives in no local *root*, which is why it
gets its own table rather than a row in `tap`.

**Rev 2 (2026-11-19).** Rev 1 spelled it `--tap=USER/REPO`. The owner
settled the spelling on 2026-11-08 and refined it on #40: `-t` stays
strictly local ("no confusion about what's local, keep the filtering
there"); `-tt` is the remote lens; and `=` binds an exact tap name,
while a bare term searches what is already known. `--tap=` is dropped.
The Option B spelling would be `bhs taps ls user/repo`.

## Purpose

Two needs from feature-requests.txt (2026-09-15):

1. **Evaluate before tapping.** "Is this tap worth adding?" today means
   `brew tap` (a git clone into `Library/Taps`) or clicking through
   GitHub. The listing should come from the URL alone.
2. **Teach the shape of a tap.** The verbose tiers should show a user
   what the tool looked at, so they could do the same with `curl` and
   `jq`. The tool is a worked example, not a black box.

## Input

```
bhs -t [query ...]                      # local taps (today, unchanged)
bhs -t=USER/REPO [query ...]            # one local tap, by exact name
bhs -tt=USER/REPO [query ...]           # one remote tap, fetched from GitHub
bhs -tt=https://github.com/USER/homebrew-REPO [query ...]
bhs -tt [query ...]                     # search remote taps already previewed (cache only)
```

The rule, in the owner's words: with `=` "that assumes that that's the
exact name"; without it, "it's a search over locally known ones".

| spelling | where it looks | network |
|---|---|---|
| `-t` | every locally tapped repo | no |
| `-t=user/repo` | that tapped repo only; error if not tapped, with a hint to try `-tt=` | no |
| `-tt` | every remote tap in the `remote_tap` cache | no |
| `-tt=user/repo` | that repo on GitHub (fetched, then cached) | yes, unless fresh |

- **Parsing.** argparse can't give a count flag a value, so a small argv
  pre-pass turns `-t=VALUE` / `-tt=VALUE` (and `--taps=VALUE`) into the
  count plus an exact-tap value before argparse runs. `=` must be
  attached; `-tt user/repo` with a space is a search term, not a tap
  name. `-t=` inside a short cluster (`-it=x`) is a usage error.
- `-tt=` is repeatable; each value is one tap. Query terms filter the
  union with the search grammar (INPUT.md § Query), name and desc.
- Short form resolves per brew's convention: `user/repo` ⇒ GitHub repo
  `user/homebrew-repo`. A full GitHub URL is accepted as-is. Other hosts
  are out of scope for v1 (reject with a clear message).
- `user/repo/name` (brew's fully qualified formula name) after `-tt=`
  previews that one formula.
- Kind filters `-f` / `-c` apply. Formats `-g`, `--json`, `--csv`,
  `--tsv`, `-T`, `--sql` apply.
- Freshness: `--refresh=taps` and `--stale DUR` honor the taps TTL
  (`BREW_HOP_SEARCH_STALE_TAPS`). `--offline` (0.4.0) reads the cache
  only, which makes `-tt=user/repo --offline` the same as a cached
  `-tt` filtered to that tap.
- Auth: if `GITHUB_TOKEN` or `GH_TOKEN` is set it is sent as a Bearer
  header; otherwise unauthenticated (60 req/h). The listing costs one
  API request plus one raw fetch per `.rb` file; raw fetches are not
  subject to the API limit.

Local and remote are never mixed silently: `-t` and `-tt` results print
in separate sections (`# taps` and `# remote taps`), both tagged `t` at
`-v`, the remote ones carrying the tap slug. Doubling a source letter to
mean "look online" is noted in cli-vocabulary as a pattern; no other
source uses it yet.

## Fetch

1. `GET https://api.github.com/repos/{user}/homebrew-{repo}` — default
   branch, description, pushed_at. (Skipped when cached and fresh.)
2. `GET https://api.github.com/repos/{user}/homebrew-{repo}/git/trees/{branch}?recursive=1`
   — one call returns every path. Keep `*.rb` under `Formula/`,
   `Casks/`, `HomebrewFormula/`, or the repo root; skip anything with
   `test` or `spec` in the path (same rule as `scan_taps`).
3. `GET https://raw.githubusercontent.com/{user}/homebrew-{repo}/{branch}/{path}`
   per kept file, bounded parallelism (8), parsed by `parse_rb` after
   it is split so the regex half takes text, not a path.
4. Dedupe `(tap, kind, name)` keeping the deepest path (`Formula/x.rb`
   over a stale root `x.rb`), mirroring the mtime rule in `scan_taps`.

Truncated trees (`truncated: true`, >100k entries) are not a realistic
tap; print a warning and proceed with what was returned.

## Storage

Table `remote_tap`, same columns as `tap` plus `branch`, `path`, and
`fetched_at`; pk `(tap, kind, name)`. `_meta` kind `remote_tap:{slug}`
so each tap ages independently. `-C` shows one `taps:r` row per cached
remote tap, aligned with the others.

Kept separate from `tap` so the local scan's dedupe and refresh never
see rows that do not exist on disk, and so `brew untap` semantics stay
simple: a remote listing is a view, not a root.

## Output

Default (level 1): the tap section exactly as `-t` renders it, with a
header `# user/repo (N formulae, M casks)`.

`-v` (level 2): adds the repo description and `pushed_at` as a relative
age under the header, the cache-age line, and the `t` indicator column.

`-vv` (level 3): adds a **trace** block after the results, one line per
request in order, with status, bytes, and wall time:

```
  # trace user/repo
    GET api.github.com/repos/user/homebrew-repo                 200  1.2KB   84ms
    GET …/git/trees/main?recursive=1                            200  9.8KB  110ms
    tree: Formula/ 14 .rb   Casks/ 2 .rb   root 0   skipped 3 (test/spec)
    GET raw.githubusercontent.com/…/Formula/foo.rb  ×16         200  41KB  312ms (8 parallel)
```

`-vvv` (level 4, **teach mode**): adds a **reproduce** block: the shell
pipeline that yields the same listing, and the JSON shape it reads.

```
  # reproduce
    curl -s https://api.github.com/repos/user/homebrew-repo/git/trees/main?recursive=1 \
      | jq -r '.tree[] | select(.type=="blob" and (.path|endswith(".rb"))) | .path'
    # .tree[] = {path, type: blob|tree, size, sha, url}
    curl -s https://raw.githubusercontent.com/user/homebrew-repo/main/Formula/foo.rb \
      | grep -E '^\s*(desc|homepage|version|url)\s'
    # yq users: yq -p json '.tree[].path' on the saved tree
```

Level 4 is new; OUTPUT.md defines 0–3. `-vvv` and `--verbose=4` map to
it. Other commands treat 4 as 3. If bhs-de8 (scoped verbosity, `-v=t`)
lands first, the trace and reproduce blocks become `-v=tt` / `-v=ttt`
and level 4 is withdrawn.

JSON (`--json`): the envelope (ENVELOPE.md) carries `command:
"tap-list"`, `tap`, `branch`, and a `requests` array mirroring the
trace lines; the reproduce text is not included (it is a rendering of
`requests`).

## Examples

```
bhs -tt=steipete/tap                   # list everything
bhs -tt=steipete/tap -c                # casks only
bhs -tt=steipete/tap goplaces -vvv     # one match, plus how to do it by hand
bhs -tt=steipete/tap/goplaces          # one formula
bhs -tt=a/one -tt=b/two cli            # two taps, one filter
bhs -tt cli                            # search taps already previewed, offline
bhs -t=homebrew/core wget              # one local tap, exact name
bhs -tt=steipete/tap --offline         # cache only, no network
```

## Tests

Red first, fixtures under `tests/fixtures/remote_tap/`: a recorded tree
JSON and four `.rb` files; `urlopen` monkeypatched to serve them by URL.

- default / `-v` / `-vv` / `-vvv` snapshots.
- argv pre-pass: `-t`, `-t=x/y`, `-tt`, `-tt=x/y`, `-tt=x/y -tt=a/b`,
  `-tt x/y` (search term, not a tap), `-it=x` (usage error),
  `--taps=x/y`; a table test over each.
- `-t=user/repo` for an untapped repo errors and suggests `-tt=`.
- short name → `homebrew-` repo; full URL accepted; non-GitHub rejected.
- second run within TTL makes zero requests; `--refresh=taps` makes
  them again.
- `test`/`spec` paths skipped; root-vs-`Formula/` duplicate keeps
  `Formula/`.
- `-C` shows the `taps:r` row aligned with the others.
- `GITHUB_TOKEN` set ⇒ Authorization header present; unset ⇒ absent.

## Open questions

- Should `-tt=user` (no repo) enumerate that user's
  `homebrew-*` repos? Cheap (one search-API call) but a different
  feature; leave for a follow-up bead.
- Whether `remote_tap` rows should feed the all-cached aggregate
  (locations.md § Aggregate). Default no: it is a view of someone
  else's repo, not something the user has.
