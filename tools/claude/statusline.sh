#!/bin/bash
# Per-project Claude Code statusline (dense trial, v2).
# Picked up by ~/.claude/statusline-command.sh, which delegates here when
# this file exists; receives the full statusline JSON on stdin.
#
# Segments, highest priority first (rightmost truncate first in narrow windows):
#   <~/d/project[/t/ail]> <branch><*> | <ctx>% | <model> | +A/-D | $cost
#     [| PR#n:state] [| 5h:NN%] [| ▣ready] [| #issues] [rc]
#
# Costs per render: 1 jq pass + git status (local). br ready count cached 30s;
# gh open-issue count cached 15 min, refreshed in background, served stale.

input=$(cat)

# One jq pass for all fields. Delimit with \x1f (unit separator), NOT tab:
# tab is IFS whitespace, so read would collapse empty fields and shift values.
IFS=$'\x1f' read -r cwd proj model used cost added removed pr_num pr_state rl5h < <(
  printf '%s' "$input" | jq -r '[
    (.workspace.current_dir // .cwd // ""),
    (.workspace.project_dir // ""),
    (.model.display_name // ""),
    (.context_window.used_percentage // "" | tostring),
    (.cost.total_cost_usd // "" | tostring),
    (.cost.total_lines_added // "" | tostring),
    (.cost.total_lines_removed // "" | tostring),
    (.pr.number // "" | tostring),
    (.pr.review_state // ""),
    (.rate_limits.five_hour.used_percentage // "" | tostring)
  ] | join("\u001f")'
)

dim='\033[2m'; cyan='\033[0;36m'; red='\033[0;31m'; yellow='\033[0;33m'
green='\033[0;32m'; reset='\033[0m'
sep=" ${dim}|${reset} "

# --- path hint: abbreviate parents to first char (dotdirs to 2), full last ---
hintify() {
  local IFS=/ seg out="" n i
  local -a parts
  read -ra parts <<<"$1"
  n=${#parts[@]}
  for ((i = 0; i < n - 1; i++)); do
    seg="${parts[i]}"
    case "$seg" in
    "" | "~") out+="$seg/" ;;
    .*) out+="${seg:0:2}/" ;;
    *) out+="${seg:0:1}/" ;;
    esac
  done
  printf '%s' "$out${parts[n - 1]}"
}

root="${proj:-$cwd}"
path_part="${cyan}$(hintify "${root/#$HOME/\~}")${reset}"
if [ -n "$proj" ] && [ "$cwd" != "$proj" ] && [[ "$cwd" == "$proj"/* ]]; then
  path_part+="${dim}/$(hintify "${cwd#"$proj"/}")${reset}"
fi
out="$path_part"

# --- git: branch + dirty marker ---
if branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null || git -C "$cwd" rev-parse --short HEAD 2>/dev/null); then
  dirty=""
  git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null | grep -q . && dirty="${yellow}*${reset}"
  out+=" ${red}${branch}${reset}${dirty}"
fi

# --- context %: green <60, yellow 60-80, red >80 ---
if [ -n "$used" ]; then
  pct=${used%.*}
  if [ "$pct" -gt 80 ] 2>/dev/null; then c=$red
  elif [ "$pct" -gt 60 ] 2>/dev/null; then c=$yellow
  else c=$green; fi
  out+="$sep${c}${pct}%${reset}"
fi

[ -n "$model" ] && out+="$sep${dim}${model}${reset}"
[ -n "$added$removed" ] && out+="$sep${green}+${added:-0}${reset}/${red}-${removed:-0}${reset}"
[ -n "$cost" ] && out+="$sep${dim}\$$(printf '%.2f' "$cost")${reset}"

# --- PR (free: from statusline JSON, present only while a PR is open) ---
[ -n "$pr_num" ] && out+="$sep${yellow}PR#${pr_num}${reset}${pr_state:+${dim}:${pr_state}${reset}}"

# --- 5h rate limit: only when it's becoming relevant (>=60%) ---
if [ -n "$rl5h" ]; then
  rl=${rl5h%.*}
  if [ "$rl" -ge 80 ] 2>/dev/null; then out+="$sep${red}5h:${rl}%${reset}"
  elif [ "$rl" -ge 60 ] 2>/dev/null; then out+="$sep${yellow}5h:${rl}%${reset}"; fi
fi

# --- cached segments: br ready count (30s), gh open issues (15min, bg refresh) ---
cache_dir="${TMPDIR:-/tmp}/claude-sl-$(printf '%s' "$root" | cksum | cut -d' ' -f1)"
mkdir -p "$cache_dir"
now=$(date +%s)

fresh() { # fresh <file> <ttl_s>
  [ -f "$1" ] && [ $((now - $(stat -f %m "$1" 2>/dev/null || echo 0))) -lt "$2" ]
}

# br: fast + local -> sync refresh on expiry
if [ -d "$root/.beads" ] && command -v br >/dev/null; then
  f="$cache_dir/br-ready"
  fresh "$f" 30 || (cd "$root" && br ready 2>/dev/null | head -1 | grep -oE '[0-9]+' | head -1) >"$f"
  ready=$(<"$f")
  [ -n "$ready" ] && out+="$sep${dim}▣${reset}${ready}"
fi

# gh: network -> serve stale, refresh in background (mkdir as lock)
if git -C "$root" remote get-url origin >/dev/null 2>&1 && command -v gh >/dev/null; then
  f="$cache_dir/gh-issues"
  if ! fresh "$f" 900 && mkdir "$f.lock" 2>/dev/null; then
    (
      cd "$root" && gh issue list --state open --json number --jq length >"$f.tmp" 2>/dev/null &&
        mv "$f.tmp" "$f"
      rmdir "$f.lock"
    ) &
    disown
  fi
  if [ -f "$f" ]; then
    issues=$(<"$f")
    [ -n "$issues" ] && [ "$issues" != "0" ] && out+="$sep${dim}#${reset}${issues}"
  fi
fi

# --- rc tag: static "configured on" from settings (live /rc state is not
#     exposed to statusline scripts as of CC 2.1.x) — lowest priority, last ---
if [ "$(jq -r '.remoteControlAtStartup // false' ~/.claude/settings.json 2>/dev/null)" = "true" ]; then
  out+=" ${dim}rc${reset}"
fi

printf "%b\n" "$out"
