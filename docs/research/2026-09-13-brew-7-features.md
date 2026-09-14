---
question: What changed in Homebrew 6.0 → 7.0.0 that a caching/indexing tool (brew-hop-search) should know, and what new data sources does it expose?
date: 2026-09-13
kind: full-report
tldr: >
  brew 7.0.0 (released 2026-09-13) makes tap trust the default and disables
  --eval-all; adds `brew list --no-installed-on-request`, `brew doctor --json`,
  a built-in `brew vulns` fed by formulae.brew.sh/api/advisories.json (OSV
  format, 14 MB gz), and a `vulnerabilities` key on per-formula API JSON.
  `brew tap-info --installed --json=v1` carries a `trusted` field since 6.0.
  Min versions: trust/tap-info trusted = 6.0.0; list/doctor/vulns/advisories
  = 7.0.0 (some may have landed in 6.0.x point releases — unverified).
---

# Homebrew 7.0.0 research report

Sources read by the research agent: brew.sh blog index, the 7.0.0 and 6.0.0
announcement posts, the 7.0.0 migration guide, the GitHub 7.0.0 release,
docs.brew.sh/Manpage (truncated at ~39k chars; later sections came from a
summary, flagged "(manpage summary)"), docs.brew.sh/Tap-Trust,
formulae.brew.sh/docs/api/, Homebrew/brew PRs 23341 and 23555.

## 1. What changed (6.0.0 → 7.0.0)

**Tap trust (6.0.0 default; hardened in 7.0.0)**
- Non-official taps must be explicitly trusted before Ruby is evaluated.
  Commands: `brew trust [--tap|--formula|--cask|--command] target`,
  `brew untrust`, `brew trust --json=v1`. Trust store:
  `${XDG_CONFIG_HOME}/homebrew/trust.json` or `~/.homebrew/trust.json`
  (manpage summary).
- `brew tap-info` gained a `trusted` field in 6.0.0 (PR 22613).
  `brew tap-info --installed --json=v1` is named in the 7.0.0 post as now
  collecting metadata concurrently while preserving output order (PR 22975).
  `--json` accepts only `v1`.
- 7.0.0 migration guide: `HOMEBREW_EVAL_ALL` / `--eval-all` on `deps`,
  `desc`, `info`, `options`, `readall`, `search`, `uses`, `tap` are
  **disabled**. `HOMEBREW_REQUIRE_TAP_TRUST`, `HOMEBREW_NO_REQUIRE_TAP_TRUST`,
  `HOMEBREW_ALLOWED_TAPS` deprecated until 2027-12-11.
- `brew bundle cleanup` resets the trust store to the Brewfile's `trusted:`
  values; `brew bundle dump` records `trusted:` (6.0.0).

**`brew list`**
- `brew list --no-installed-on-request` identifies formulae installed as
  dependencies (7.0.0, PR 22829). Also `--installed-on-request`,
  `--poured-from-bottle`, `--built-from-source`, and `--json` (requires
  `--versions`, no named args, and `jq`).
- `brew list --installed-as-dependency` **disabled**; `brew leaves -p` remains.

**`brew info` / JSON**
- `--json` default `v1` (formula only), `v2` formula+cask; `--installed`,
  `--variations`. `brew info --fetch-manifest` disabled.
- Human output marks uninstallable packages with `⊘` vs uninstalled `✘`.

**`brew doctor`**
- 7.0.0 post: `brew doctor --json` provides structured diagnostics (PR
  22448). The verbatim manpage `doctor` section lists only `--list-checks`
  and `-D/--audit-debug` — treat `--json` as present-per-release-notes,
  UNVERIFIED in the manpage.

**Internal JSON API**
- Default since 6.0.0 (single combined download); `HOMEBREW_USE_INTERNAL_API`
  disabled in 7.0.0. 7.0.0 reuses parsed API data on warm runs while
  verifying signatures on every load (PR 23300); API carries cask language
  variants (PR 23124) and signed install steps.
- Env: `HOMEBREW_API_DOMAIN` (default `https://formulae.brew.sh/api`),
  `HOMEBREW_API_AUTO_UPDATE_SECS` (default 450), `HOMEBREW_NO_INSTALL_FROM_API`,
  `HOMEBREW_FORCE_API_AUTO_UPDATE` (manpage summary).

**Advisory database / vulnerabilities (new in 7.0.0)**
- `brew vulns` built in (was a separate tap in 6.0.0). Flags: `-d/--deps`,
  `--brewfile[=path]`, `--no-ignore-patches`, `--fix-available`,
  `--no-fix-available`, `--fix-type=released|patch|any|none|unreleased`,
  `--list-skipped`, `-s/--severity=low|medium|high|critical`,
  `-m/--max-summary`, `-j/--json`.
- Data: OSV.dev plus https://github.com/Homebrew/advisory-database (CC0,
  OSV-format `BREW-*` records). No `brew advisories` command exists.

**Bundle**: Cargo git/path sources; `source:` for uv tools; `brew deps
--brewfile`. Disabled: `brew bundle install --cleanup`, `--describe`,
`HOMEBREW_BUNDLE_JOBS`; `brew bundle --jobs` deprecated.

**Platform**: macOS ≤ 10.15 removed; Intel Tier 3, no new bottles; Linux
sandbox is Landlock.

## 2. Minimum versions

| Feature | Min brew |
|---|---|
| Tap trust, `brew trust --json=v1`, tap-info `trusted`, internal API default, bundle `trusted:` | 6.0.0 |
| `brew list --no-installed-on-request`, `brew doctor --json`, built-in `brew vulns`, `brew deps --brewfile`, formula API `vulnerabilities` key, `advisories.json` | 7.0.0 (PRs merged Jul–Aug 2026; some 6.0.x may have them — UNVERIFIED) |

## 3. formulae.brew.sh endpoints

- Documented: `/api/formula.json`, `/api/cask.json`,
  `/api/formula/${F}.json`, `/api/cask/${C}.json`,
  `/api/analytics/${CATEGORY}/${DAYS}.json`,
  `/api/analytics/${CATEGORY}/homebrew-core/${DAYS}.json`,
  `/api/analytics/cask-install/homebrew-cask/${DAYS}.json`.
- PR 23341: `api/formula/<name>.json` gains `vulnerabilities`
  `{open:[...], patched:[...], fixed_count:n}`; key **absent** when a formula
  has no records (distinguishes "clean" from "not covered"). Not in the
  internal API or `brew info` as of that PR.
- PR 23555: `https://formulae.brew.sh/api/advisories.json` (67 MB raw /
  14 MB gzip; request `--compressed`), consumed by `brew vulns`; identical to
  advisory-database `data/advisories.json`.
- `.jws.json`, "v3", tap-specific endpoints: UNVERIFIED (not in any source).

## Implications for brew-hop-search

- Any feature built on the 7.0 surface needs a brew-version gate that
  reports what was skipped (feature-requests.txt 22:22:29) → `brewver.py`.
- Tap trust is now real metadata worth indexing alongside `-t` results
  (`tap-info --installed --json=v1`: `trusted`, install path, revision).
- `advisories.json` is a natural fifth source (offline-searchable OSV
  records keyed by formula) but is 14 MB gz — cache with TTL like the index.
- `brew doctor --json` is cacheable/diffable but is a health check, not a
  search source; fits a subcommand layer better than a flag.
