---
question: How does Homebrew itself take configuration (HOMEBREW_* env, brew.env files, booleans, feature flags, token precedence), how do external commands (`brew <cmd>` → `brew-<cmd>`) dispatch and since when, and what does that imply for a `brew-hop` family of commands?
date: 2026-09-28
kind: full-report
tldr: >
  Brew is configured by a declarative HOMEBREW_* table (env_config.rb) that
  generates its manpage; booleans are set/unset with `false|no|off|nil|0`
  falsy; default-on switches get NO_ negations; there is no comma-list
  feature variable, one var per feature; brew.env files exist since 4.1.4.
  External commands (`brew-<cmd>` on PATH) date from 2010-06-07, not brew 6,
  and are still undeprecated in 7.0.7. Critical: `bin/brew` filters the
  environment to HOMEBREW_* before exec'ing an external command — a
  BREW_HOP_* variable does NOT reach `brew hop`; HOMEBREW_HOP_* does. Token
  precedence in brew: HOMEBREW_GITHUB_API_TOKEN > `gh auth token` >
  osxkeychain; plain GITHUB_TOKEN is stripped. Sources verified against a
  local 7.0.7 checkout plus docs.brew.sh and the brew.sh blog.
---

# Homebrew conventions: env config, external commands, version timeline

Researched by a subagent 2026-09-28 against a local Homebrew 7.0.7 checkout
(`/opt/homebrew`, git history intact) plus docs.brew.sh and brew.sh blog.
Consumers: [config-layers](../specs/drafts/config-layers.md) and
[peek](../specs/drafts/peek.md).

## 1. Configuration: `HOMEBREW_*` environment (plus `brew.env` files)

**Not strictly env-only.** `brew` is configured by `HOMEBREW_*` variables, but since 4.1.4 (commit `375a7ee8dc`, 2023-07-28, "Allow configuring Homebrew with `.env` files"; announced in the [4.2.0 post](https://brew.sh/2023/12/18/homebrew-4.2.0/)) `bin/brew` also loads three env files, in order: `/etc/homebrew/brew.env`, `${HOMEBREW_PREFIX}/etc/homebrew/brew.env`, then `$XDG_CONFIG_HOME/homebrew/brew.env` (else `~/.homebrew/brew.env`); `HOMEBREW_SYSTEM_ENV_TAKES_PRIORITY` re-loads the system file last ([bin/brew](https://github.com/Homebrew/brew/blob/master/bin/brew), `export_homebrew_env_file`). Only lines matching `^(HOMEBREW_|SUDO_ASKPASS=|(all|no|ftp|https?)_proxy=)` are accepted, and variables `bin/brew` itself exports cannot be overridden. Documented in [`man brew` § ENVIRONMENT / docs/Manpage.md](https://docs.brew.sh/Manpage#environment): "environment variables must have a value set to be detected... run `export HOMEBREW_NO_INSECURE_REDIRECT=1` rather than just `export HOMEBREW_NO_INSECURE_REDIRECT`."

**Source of truth is a declarative table.** [`Library/Homebrew/env_config.rb`](https://github.com/Homebrew/brew/blob/master/Library/Homebrew/env_config.rb) defines `ENVS = { HOMEBREW_FOO: { description:, default:, default_text:, boolean:, disabled_by:, replacement:, odeprecated:/odisabled: } }` and metaprograms one accessor per key (`Homebrew::EnvConfig.no_auto_update?`, `.api_domain`). The manpage's ENVIRONMENT section is generated from that table ([`manpages.rb`](https://github.com/Homebrew/brew/blob/master/Library/Homebrew/manpages.rb) iterates `EnvConfig::ENVS`, skipping `hidden?`).

**Boolean parsing (two modes).** `FALSY_VALUES = %w[false no off nil 0]`. With `boolean: true`, the var is on when set to any value not in that list (case-insensitive). With `boolean: :set` (used by `HOMEBREW_NO_AUTO_UPDATE`, `HOMEBREW_DEVELOPER`, `HOMEBREW_NO_ENV_HINTS`, `HOMEBREW_NO_INSTALL_CLEANUP`, `HOMEBREW_DEBUG`), *any non-empty value* counts, even `0`. Empty string == unset. `disabled_by:` pairs a default-on switch with its negation, e.g. `HOMEBREW_REQUIRE_TAP_TRUST` (`default: true`) is disabled by `HOMEBREW_NO_REQUIRE_TAP_TRUST` (itself `odeprecated`). Lifecycle keys `odeprecated`/`odisabled`/`replacement` drive warnings and auto-copy the value to the replacement var.

**Categories (from the table):**
- *Boolean toggles:* `HOMEBREW_NO_AUTO_UPDATE`, `HOMEBREW_NO_INSTALL_CLEANUP`, `HOMEBREW_DEVELOPER`, `HOMEBREW_NO_ANALYTICS`, `HOMEBREW_DISPLAY_INSTALL_TIMES`, `HOMEBREW_VERBOSE`. Note the pervasive `NO_` negative form (`NO_COLOR`, `NO_EMOJI`, `NO_SANDBOX_LINUX`).
- *Values with defaults:* `HOMEBREW_API_DOMAIN` (default `https://formulae.brew.sh/api`), `HOMEBREW_CACHE`, `HOMEBREW_API_AUTO_UPDATE_SECS` (450), `HOMEBREW_CLEANUP_MAX_AGE_DAYS` (120), `HOMEBREW_DOWNLOAD_CONCURRENCY`. `HOMEBREW_PREFIX`/`CELLAR`/`REPOSITORY` are *derived* in `bin/brew` from the binary's location, not from the table.
- *Policy / opt-in lists:* `HOMEBREW_FORBIDDEN_FORMULAE|CASKS|TAPS|LICENSES` (space-separated; 7 vars use "space-separated"), `HOMEBREW_FORBIDDEN_OWNER[_CONTACT]`, `HOMEBREW_NO_CLEANUP_FORMULAE` (comma-separated, the outlier), `HOMEBREW_ALLOWED_TAPS`, `HOMEBREW_NO_ENV_HINTS`, `HOMEBREW_VERIFY_ATTESTATIONS`.
- *Per-subsystem namespaces:* `HOMEBREW_BUNDLE_*` (plus generated `HOMEBREW_BUNDLE_{CLEANUP,DUMP}_NO_{BREW,CASK,TAP,...}` via `BUNDLE_DISABLE_ENVS`), `HOMEBREW_CASK_OPTS` (an argv string appended to cask commands), `HOMEBREW_GITHUB_API_TOKEN`, `HOMEBREW_GITHUB_PACKAGES_{USER,TOKEN}`, `HOMEBREW_CURL_*`, `HOMEBREW_GIT_*`, `HOMEBREW_BAT_*`, `HOMEBREW_LIVECHECK_*`, `HOMEBREW_SORBET_*`.
- *Experimental:* there is no `HOMEBREW_EXPERIMENTAL_*` entry in `ENVS` and no comma-list "enable features X,Y" variable. The only such name is `HOMEBREW_EXPERIMENTAL_RUST_FRONTEND`, special-cased in `bin/brew` ("cannot be set in an env file") and absent from the manpage. Features are one-var-per-feature.

**Promotion of generic vars.** `bin/brew` copies `BROWSER`, `EDITOR`, `DISPLAY`, `NO_COLOR`, `BUNDLE_USER_CACHE` into `HOMEBREW_*` only if the `HOMEBREW_` form is unset, and unconditionally copies `PATH`, `TMPDIR`, `XDG_*`, `GOPATH`, etc. into `HOMEBREW_PATH`, `HOMEBREW_TMPDIR`... `HOMEBREW_USER_SET_VARS` records which `HOMEBREW_*` were user-set before brew exported its own.

**Reporting.** `brew config` (`system_config.rb#homebrew_env_config`) prints `HOMEBREW_PREFIX`, non-default `REPOSITORY`/`CELLAR`, then only `EnvConfig.non_default_variables`; booleans print as `set`, sensitive vars (`ENV.sensitive?`) print `set` rather than the value. `brew --env` is unrelated: it dumps the *build* environment (CC, CFLAGS...) with `--shell=` / `--plain` ([cmd/--env.rb](https://github.com/Homebrew/brew/blob/master/Library/Homebrew/cmd/--env.rb)).

**GitHub token precedence** ([`utils/github/api.rb#credentials`](https://github.com/Homebrew/brew/blob/master/Library/Homebrew/utils/github/api.rb)): (1) `HOMEBREW_GITHUB_API_TOKEN`, (2) `gh auth token --hostname github.com` (`github_cli_token`), (3) `git credential-osxkeychain get` for github.com, used only if the password matches `GITHUB_ACCESS_TOKEN_REGEX`. Brew never reads plain `GITHUB_TOKEN` itself; `bin/brew` strips `GITHUB_*TOKEN*` even in CI. Note `HOMEBREW_NO_EVAL_ENV_SCRUBBING`: secrets are scrubbed during formula evaluation except that token.

## 2. External commands

**Mechanism** ([docs/External-Commands.md](https://docs.brew.sh/External-Commands)): `brew example` resolves, in order (`brew.rb` + [`commands.rb`](https://github.com/Homebrew/brew/blob/master/Library/Homebrew/commands.rb)): internal `cmd/`/`dev-cmd/` → tap `cmd/example.rb` (`AbstractCommand` subclass, "v2") → `brew-example.rb` (legacy Ruby, `require`d in-process) → `brew-example` executable, searched on `PATH` **appended with** every `$(brew --repo)/Library/Taps/*/*/cmd` (`tap_cmd_directories`). The executable is `exec`'d with remaining argv unchanged after brew sets `HOMEBREW_CACHE` and `HOMEBREW_LIBRARY_PATH` (`brew.rb`), on top of everything `bin/brew` exported (`HOMEBREW_PREFIX`, `CELLAR`, `REPOSITORY`, `LIBRARY`...). The filename must be exactly `brew-example` (no `.sh`). Verified locally: `brew hop search foo --bar` exec'd `/tmp/.../brew-hop` with `argv: search foo --bar`.

**Critical caveat:** `bin/brew` runs `brew.sh` under a filtered environment: an allow-list (`HOME SHELL PATH TERM ... proxies`) **plus `${!HOMEBREW_@}` only** ("filter the user environment" block). Verified: `BREW_HOP_X=1` did *not* reach `brew-hop`; `HOMEBREW_HOP_X=1` did.

**Age: 2010, not brew 6.** Commit [`b016c2eae5`](https://github.com/Homebrew/brew/commit/b016c2eae516c7a631a75b41b3425c24b868b796), Adam Vandenberg, 2010-06-07, "Support external commands": "look for external commands that are +x on PATH, named as brew-<cmd> or brew-<cmd>.rb... Shell scripts are exec'd with some HOMEBREW variables set in the ENV. Ruby scripts are require'd directly." The wiki page was imported into the repo 2014-10-26 (`19d12aee45`). `brew commands` dates from 2013-09-14 (`fa0872a42c`).

**Later changes:** tap-`cmd/`-only `<name>.rb` AbstractCommand form added 2020-03-11 (`7a08691100`, "helper for official external commands"), docs rewritten 2024-04-23 ("new command abstraction", 4.2.x); 6.0.0 tap trust ([docs/Tap-Trust.md](https://docs.brew.sh/Tap-Trust)): tap-shipped commands need `brew trust --command user/repo/cmd` or whole-tap trust; PATH-based `brew-*` executables are outside that gate (only "installed on PATH or distributed in a tap"). Help: `#:` comment lines, else brew runs the executable with `--help`. `brew commands` lists an "External commands" section, but only from tap `cmd/` dirs (`external_commands` globs `tap_cmd_directories`), and `brew command hop` reported "Unknown command" for a PATH-only `brew-hop`; `brew tap-new` scaffolds no `cmd/` dir. Deprecations: none of the three forms is deprecated as of 7.0.7; `brew-*.rb` is labelled "legacy".

## 3. Version timeline (brew.sh blog)

| Ver | Date | Highlight |
|---|---|---|
| [4.0.0](https://brew.sh/2023/02/16/homebrew-4.0.0/) | 2023-02-16 | JSON API default (`HOMEBREW_NO_INSTALL_FROM_API` opt-out), auto-update 24h, EU InfluxDB analytics |
| [4.1.0](https://brew.sh/2023/07/20/homebrew-4.1.0/) | 2023-07-20 | Signed API with client verification; GA analytics removed; `HOMEBREW_NO_ENV_FILTERING` no-op |
| [4.2.0](https://brew.sh/2023/12/18/homebrew-4.2.0/) | 2023-12-18 | Ruby 3.1, Sonoma, `brew.env` config files, `brew setup-ruby` |
| [4.3.0](https://brew.sh/2024/05/14/homebrew-4.3.0/) | 2024-05-14 | SBOMs, `HOMEBREW_VERIFY_ATTESTATIONS`, autoremove default, Ruby 3.3 |
| [4.4.0](https://brew.sh/2024/10/01/homebrew-4.4.0/) | 2024-10-01 | Sequoia, cask receipts, `brew tab` |
| [4.5.0](https://brew.sh/2025/04/29/homebrew-4.5.0/) | 2025-04-29 | `bundle`/`services` built in, Ruby 3.4 + Bootsnap |
| [4.6.0](https://brew.sh/2025/08/05/homebrew-4.6.0/) | 2025-08-05 | `HOMEBREW_DOWNLOAD_CONCURRENCY` opt-in, `brew mcp-server`, macOS 26 |
| [5.0.0](https://brew.sh/2025/11/12/homebrew-5.0.0/) | 2025-11-12 | Concurrent downloads default, Linux ARM64 Tier 1, unsigned casks deprecated |
| [5.1.0](https://brew.sh/2026/03/10/homebrew-5.1.0/) | 2026-03-10 | bundle for cargo/uv/flatpak, `brew version-install`, `HOMEBREW_INSIDE_BUNDLE` |
| [6.0.0](https://brew.sh/2026/06/11/homebrew-6.0.0/) | 2026-06-11 | **Tap trust required** (`brew trust`), internal JSON API default, Linux sandbox, `brew exec` |
| [7.0.0](https://brew.sh/2026/09/13/homebrew-7.0.0/) | 2026-09-13 | Landlock sandbox, advisory DB, Intel Tier 3, `HOMEBREW_ARCH`/`NO_SANDBOX_LINUX` deprecated |

## Implications for a `brew-hop` family

- `brew hop search …` works today as a PATH `brew-hop` executable receiving `argv = [search, …]`; dispatch has been stable since 2010. Subcommand routing is yours.
- **Do not use a `BREW_HOP_*` prefix for anything that must survive `brew hop` invocation**: `bin/brew` drops every non-`HOMEBREW_*` variable. Either read `HOMEBREW_HOP_*` (passes through, mirrors upstream), or accept that `BREW_HOP_*` only works when the binary is run directly (`brew-hop`/`bhs`). Supporting both, `HOMEBREW_HOP_*` first, is the least-surprise option.
- Mirror upstream semantics: booleans are set/unset with `false|no|off|nil|0` as falsy; negative `NO_` names for default-on behaviour; one var per feature, no comma-list feature switch; lists space-separated; a declarative table generating `--help`/man text; a `config`-style dump printing only non-defaults with `set` for booleans/secrets.
- For tap distribution, ship `cmd/brew-hop` and expect users to `brew trust` (6.0+).
