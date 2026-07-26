# Security Policy

Maintained by one volunteer; response times are best-effort.

## Reporting Vulnerabilities

**Preferred:** GitHub Private Vulnerability Reporting — the "Report a
vulnerability" button on this repo's Security tab.

**Fallback:** age-encrypted email.

**Email:** security@pkgs.mcint.io

**SSH public key (age-compatible):**
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILLVqq1bzNWW4Z+XcAVUeoDhwb/sXw+d7O65QezsXnGh
```

Encrypt your report with:
```sh
echo "report text" | age -R <(echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILLVqq1bzNWW4Z+XcAVUeoDhwb/sXw+d7O65QezsXnGh") | mail -s "brew-hop-search security" security@pkgs.mcint.io
```

Or attach a file:
```sh
age -R <(echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILLVqq1bzNWW4Z+XcAVUeoDhwb/sXw+d7O65QezsXnGh") -o report.age report.txt
```

I aim to acknowledge reports within **14 days**; if you hear nothing
after 3 weeks, ping again. No SLA is offered. Assessment and fix are
best-effort; I follow a **90-day coordinated disclosure window** from
acknowledgment — if a fix will take longer, I'll say so and propose a
date. Keep the initial report short (a few sentences plus a PoC if
you have one); no CVSS scores needed.

## Threat Model & Risk Analysis

brew-hop-search has a **low overall risk profile** due to its narrow scope: it fetches well-known public indexes, parses structured data, and writes to a local SQLite database. There is no authentication, no credential handling, and no outbound data beyond HTTP GETs.

### Network surface

| Endpoint | Purpose | Trust |
|----------|---------|-------|
| `formulae.brew.sh/api/formula.json` | Official Homebrew formula index | First-party, HTTPS |
| `formulae.brew.sh/api/cask.json` | Official Homebrew cask index | First-party, HTTPS |
| `pypi.org/pypi/brew-hop-search/json` | Version check (read-only) | Well-known registry, HTTPS |

All URLs are hardcoded constants — no user-supplied URLs are fetched in the default code path.

### Local data sources

| Source | Access | Risk |
|--------|--------|------|
| `$(brew --cache)/api/*.json` | Read-only, brew-managed | Low — files written by brew itself |
| `$(brew --repo)/Library/Taps/**/*.rb` | Read-only, regex-parsed | **Medium** — see below |
| `brew info --json=v2 --installed` | Subprocess, stdout parsed | Low — first-party brew CLI |

### Tap .rb parsing (medium risk)

Tap formula files are Ruby source fetched from third-party git repositories. brew-hop-search parses them with simple regexes (`desc`, `homepage`, `version`, `url` fields) — it does **not** execute Ruby or eval any content. The parsed strings are stored in SQLite via parameterized queries (sqlite-utils), so SQL injection via crafted `.rb` content is not feasible.

The residual risk is:
- A malicious tap could craft `.rb` content that produces misleading search results (e.g., a `desc` claiming to be a different tool). This is cosmetic, not exploitable.
- File paths are derived from directory traversal of `Library/Taps/`, not from `.rb` file content, so path traversal is not a vector.

### SQLite database

The FTS5 database at `~/.cache/brew-hop-search/brew-hop-search.db` is user-local, written with parameterized queries via sqlite-utils, and contains only public package metadata. It has no sensitive content and can be safely deleted at any time (`brew-hop-search --refresh` rebuilds it).

### Subprocess calls

brew-hop-search invokes:
- `brew --repository`, `brew --cache` — path discovery, no user input
- `brew info --json=v2 --installed` — installed package listing
- `sys.executable -m brew_hop_search.cli` / `sys.executable -m brew_hop_search._bg_installed` — background self-invocation

No user-supplied strings are interpolated into subprocess arguments.

## Supported Versions

Security fixes are applied to the latest release only.
