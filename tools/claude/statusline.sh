#!/bin/bash
# Per-project Claude Code statusline (dense trial, v3).
# Picked up by ~/.claude/statusline-command.sh, which delegates here when
# this file exists; receives the full statusline JSON on stdin.
#
# Ethos + spec: ~/.claude/{motivations,specs}/statusline.md
# Segments, highest priority first (rightmost truncate first in narrow windows):
#   <~/d-l/project[/t/ail]> <branch><*> | <ctx>%(size) | <model> | +A/-D | $cost
#     [| PR#n:state] | 5h:N% 7d:N% | sw:N df:N [| ▣ready] [| #issues] [/rc]

input=$(cat)

# One jq pass for all fields. Delimit with \x1f (unit separator), NOT tab:
# tab is IFS whitespace, so read would collapse empty fields and shift values.
IFS=$'\x1f' read -r cwd proj model used ctxsize cost added removed pr_num pr_state rl5h rl7d < <(
  printf '%s' "$input" | jq -r '[
    (.workspace.current_dir // .cwd // ""),
    (.workspace.project_dir // ""),
    (.model.display_name // ""),
    (.context_window.used_percentage // "" | tostring),
    (.context_window.context_window_size // "" | tostring),
    (.cost.total_cost_usd // "" | tostring),
    (.cost.total_lines_added // "" | tostring),
    (.cost.total_lines_removed // "" | tostring),
    (.pr.number // "" | tostring),
    (.pr.review_state // ""),
    (.rate_limits.five_hour.used_percentage // "" | tostring),
    (.rate_limits.seven_day.used_percentage // "" | tostring)
  ] | join("")'
)

dim='\033[2m'; cyan='\033[0;36m'; red='\033[0;31m'; yellow='\033[0;33m'
green='\033[0;32m'; reset='\033[0m'
sep=" ${dim}|${reset} "

# color by threshold: pct_color <value> [warn=60] [crit=80] -> sets $c ('' = calm)
pct_color() {
  local v=${1%.*} warn=${2:-60} crit=${3:-80}
  c=""
  [ "$v" -ge "$warn" ] 2>/dev/null && c=$yellow
  [ "$v" -ge "$crit" ] 2>/dev/null && c=$red
}

# --- path hint: parents to initials (hyphen parts kept: dev-llm -> d-l),
#     dotdirs keep the dot, full last component ---
abbr_seg() {
  local IFS=- piece out=""
  local -a pieces
  read -ra pieces <<<"$1"
  for piece in "${pieces[@]}"; do
    case "$piece" in
    .*) out+="${piece:0:2}-" ;;
    *) out+="${piece:0:1}-" ;;
    esac
  done
  printf '%s' "${out%-}"
}
hintify() {
  local IFS=/ seg out="" n i
  local -a parts
  read -ra parts <<<"$1"
  n=${#parts[@]}
  for ((i = 0; i < n - 1; i++)); do
    seg="${parts[i]}"
    case "$seg" in
    "" | "~") out+="$seg/" ;;
    *) out+="$(abbr_seg "$seg")/" ;;
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

# --- context: used% colored + succinct window size, e.g. 42%(1M) ---
if [ -n "$used" ]; then
  pct_color "$used"
  size=""
  if [ -n "$ctxsize" ]; then
    if [ "$ctxsize" -ge 1000000 ] 2>/dev/null; then size="$((ctxsize / 1000000))M"
    elif [ "$ctxsize" -ge 1000 ] 2>/dev/null; then size="$((ctxsize / 1000))k"; fi
  fi
  out+="$sep${c:-$green}${used%.*}%${reset}${size:+${dim}(${size})${reset}}"
fi

[ -n "$model" ] && out+="$sep${dim}${model}${reset}"
[ -n "$added$removed" ] && out+="$sep${green}+${added:-0}${reset}/${red}-${removed:-0}${reset}"
[ -n "$cost" ] && out+="$sep${dim}\$$(printf '%.2f' "$cost")${reset}"

# --- PR (free: from statusline JSON, present only while a PR is open) ---
[ -n "$pr_num" ] && out+="$sep${yellow}PR#${pr_num}${reset}${pr_state:+${dim}:${pr_state}${reset}}"

# --- usage periods: always show all, grey until thresholds bite ---
usage=""
if [ -n "$rl5h" ]; then
  pct_color "$rl5h"
  usage+="${c:-$dim}5h:${rl5h%.*}%${reset}"
fi
if [ -n "$rl7d" ]; then
  pct_color "$rl7d"
  usage+="${usage:+ }${c:-$dim}7d:${rl7d%.*}%${reset}"
fi
[ -n "$usage" ] && out+="$sep$usage"

# --- machine: swap used (sysctl, hide at 0) + root disk avail (df) ---
sw=$(sysctl -n vm.swapusage 2>/dev/null | sed -nE 's/.*used = ([0-9.]+)M.*/\1/p')
sw=${sw%.*}
machine=""
if [ -n "$sw" ] && [ "$sw" -gt 0 ] 2>/dev/null; then
  if [ "$sw" -ge 1024 ]; then swh="$(awk "BEGIN{printf \"%.1fG\", $sw/1024}")"; else swh="${sw}M"; fi
  machine+="${dim}sw:${swh}${reset}"
fi
avail=$(df -h / 2>/dev/null | awk 'NR==2 {gsub(/i$/,"",$4); print $4}')
if [ -n "$avail" ]; then
  c=""
  case "$avail" in
  *G) g=${avail%G}; g=${g%.*}
     [ "$g" -lt 20 ] 2>/dev/null && c=$yellow
     [ "$g" -lt 5 ] 2>/dev/null && c=$red ;;
  *M | *K) c=$red ;;
  esac
  machine+="${machine:+ }${c:-$dim}df:${avail}${reset}"
fi
[ -n "$machine" ] && out+="$sep$machine"

# --- cached segment: br ready count (30s TTL, sync — local and fast) ---
cache_dir="${TMPDIR:-/tmp}/claude-sl-$(printf '%s' "$root" | cksum | cut -d' ' -f1)"
mkdir -p "$cache_dir"
now=$(date +%s)

fresh() { # fresh <file> <ttl_s>
  [ -f "$1" ] && [ $((now - $(stat -f %m "$1" 2>/dev/null || echo 0))) -lt "$2" ]
}

if [ -d "$root/.beads" ] && command -v br >/dev/null; then
  f="$cache_dir/br-ready"
  fresh "$f" 30 || (cd "$root" && br ready 2>/dev/null | head -1 | grep -oE '[0-9]+' | head -1) >"$f"
  ready=$(<"$f")
  [ -n "$ready" ] && out+="$sep${dim}▣${reset}${ready}"
fi

# --- gh open issues: advisory, grey; refreshed only when the repo is actually
#     fetched (FETCH_HEAD newer than cache) — no polling, no timer probes.
#     GitHub remotes only; repos that never fetch never query. ---
gitdir=$(git -C "$root" rev-parse --absolute-git-dir 2>/dev/null)
if [ -n "$gitdir" ] && command -v gh >/dev/null; then
  case "$(git -C "$root" remote get-url origin 2>/dev/null)" in
  *github.com*)
    f="$cache_dir/gh-issues" fh="$gitdir/FETCH_HEAD"
    if [ -f "$fh" ] && [ "$fh" -nt "$f" ] && mkdir "$f.lock" 2>/dev/null; then
      (
        cd "$root" && gh issue list --state open --json number --jq length >"$f.tmp" 2>/dev/null &&
          mv "$f.tmp" "$f"
        rmdir "$f.lock"
      ) &
      disown
    fi
    if [ -f "$f" ]; then
      issues=$(<"$f")
      [ -n "$issues" ] && [ "$issues" != "0" ] && out+="$sep${dim}#${issues}${reset}"
    fi
    ;;
  esac
fi

# --- /rc: a hint to me, not a status — live /rc state is not exposed to
#     statusline scripts (CC 2.1.x); shown dim, last, first to truncate ---
if [ "$(jq -r '.remoteControlAtStartup // false' ~/.claude/settings.json 2>/dev/null)" = "true" ]; then
  out+=" ${dim}/rc${reset}"
fi

printf "%b\n" "$out"
