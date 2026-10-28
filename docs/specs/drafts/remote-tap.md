---
title: remote-tap — browse a tap's formulae without tapping it
date: 2026-10-27
kind: spec-draft
bead: bhs-vv6
tldr: >
  `bhs --tap=user/repo [query]` lists a tap's formulae and casks straight
  from GitHub (one tree-API call plus raw file fetches), parsed with the
  existing .rb regexes, cached in a `remote_tap` table under the taps TTL.
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
gets its own table rather than a row in `tap`. Vocabulary follows
[cli-vocabulary](cli-vocabulary.md) Option A (long flag with a value);
the Option B spelling would be `bhs taps ls user/repo`.

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
bhs --tap=USER/REPO [query ...]
bhs --tap=https://github.com/USER/homebrew-REPO [query ...]
```

- `--tap` is repeatable; each value is one tap. Query terms filter the
  union with the search grammar (INPUT.md § Query), name and desc.
- Short form resolves per brew's convention: `user/repo` ⇒ GitHub repo
  `user/homebrew-repo`. A full GitHub URL is accepted as-is. Other hosts
  are out of scope for v1 (reject with a clear message).
- Kind filters `-f` / `-c` apply. Formats `-g`, `--json`, `--csv`,
  `--tsv`, `-T`, `--sql` apply.
- Freshness: `--refresh=taps` and `--stale DUR` honor the taps TTL
  (`BREW_HOP_SEARCH_STALE_TAPS`). `-L` / offline reads the cache only.
- Auth: if `GITHUB_TOKEN` or `GH_TOKEN` is set it is sent as a Bearer
  header; otherwise unauthenticated (60 req/h). The listing costs one
  API request plus one raw fetch per `.rb` file; raw fetches are not
  subject to the API limit.

`--tap` composes with `-t`: `-t` is the locally tapped set, `--tap` is a
named remote. Both populate the same output sections, tagged `t` at
`-v`, with the remote ones carrying the tap slug as today.

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
bhs --tap=steipete/tap                 # list everything
bhs --tap=steipete/tap -c              # casks only
bhs --tap=steipete/tap goplaces -vvv   # one match, plus how to do it by hand
bhs --tap=a/one --tap=b/two cli        # two taps, one filter
bhs --tap=steipete/tap -L              # cache only, no network
```

## Tests

Red first, fixtures under `tests/fixtures/remote_tap/`: a recorded tree
JSON and four `.rb` files; `urlopen` monkeypatched to serve them by URL.

- default / `-v` / `-vv` / `-vvv` snapshots.
- short name → `homebrew-` repo; full URL accepted; non-GitHub rejected.
- second run within TTL makes zero requests; `--refresh=taps` makes
  them again.
- `test`/`spec` paths skipped; root-vs-`Formula/` duplicate keeps
  `Formula/`.
- `-C` shows the `taps:r` row aligned with the others.
- `GITHUB_TOKEN` set ⇒ Authorization header present; unset ⇒ absent.

## Open questions

- Should `--tap` also accept a bare `user` to enumerate that user's
  `homebrew-*` repos? Cheap (one search-API call) but a different
  feature; leave for a follow-up bead.
- Whether `remote_tap` rows should feed the all-cached aggregate
  (locations.md § Aggregate). Default no: it is a view of someone
  else's repo, not something the user has.
