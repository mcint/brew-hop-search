#!/bin/bash
# Per-project Claude Code statusline (dense trial).
# Picked up by ~/.claude/statusline-command.sh, which delegates here when
# this file exists; receives the full statusline JSON on stdin.
#
# Dense single line:  <dir> <branch><*> | <ctx>% | <model> | +A/-D | $cost

input=$(cat)

# One jq pass for all fields
IFS=$'\t' read -r cwd model used cost added removed < <(
  printf '%s' "$input" | jq -r '[
    (.workspace.current_dir // .cwd // ""),
    (.model.display_name // ""),
    (.context_window.used_percentage // "" | tostring),
    (.cost.total_cost_usd // "" | tostring),
    (.cost.total_lines_added // "" | tostring),
    (.cost.total_lines_removed // "" | tostring)
  ] | @tsv'
)

dim='\033[2m'; cyan='\033[0;36m'; red='\033[0;31m'; yellow='\033[0;33m'
green='\033[0;32m'; reset='\033[0m'
sep=" ${dim}|${reset} "

out="${cyan}$(basename "$cwd")${reset}"

# git: branch + dirty marker, compact
if branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null || git -C "$cwd" rev-parse --short HEAD 2>/dev/null); then
  dirty=""
  git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null | grep -q . && dirty="${yellow}*${reset}"
  out="$out ${red}${branch}${reset}${dirty}"
fi

# context %: green <60, yellow 60-80, red >80
if [ -n "$used" ]; then
  pct=${used%.*}
  if   [ "$pct" -gt 80 ] 2>/dev/null; then c=$red
  elif [ "$pct" -gt 60 ] 2>/dev/null; then c=$yellow
  else c=$green; fi
  out="$out$sep${c}${pct}%${reset}"
fi

[ -n "$model" ]   && out="$out$sep${dim}${model}${reset}"
[ -n "$added$removed" ] && out="$out$sep${green}+${added:-0}${reset}/${red}-${removed:-0}${reset}"
[ -n "$cost" ]    && out="$out$sep${dim}\$$(printf '%.2f' "$cost")${reset}"

printf "%b\n" "$out"
