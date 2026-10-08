# ~/.config/xmonad/config/zsh/gruvbox.zsh-theme
# minimal gruvbox prompt for oh-my-zsh, matching the xmonad rice:
#
#   ~/.config/xmonad on main ●  took 4s
#   ›                                          ✘ 1
#
# linked into ~/.oh-my-zsh/custom/themes/; enable with ZSH_THEME="gruvbox"

# palette (same values as xmobar, rofi, alacritty, firefox)
typeset -gA GB=(
  fg     '#ebdbb2'
  fg4    '#a89984'
  gray   '#7c6f64'
  dim    '#665c54'
  yellow '#d79921'
  red    '#cc241d'
  aqua   '#8ec07c'
  blue   '#83a598'
)

setopt prompt_subst
zmodload zsh/datetime
autoload -Uz add-zsh-hook

# git: "on main ●" (dot = uncommitted changes)
ZSH_THEME_GIT_PROMPT_PREFIX=" %F{$GB[dim]}on%f %F{$GB[aqua]}"
ZSH_THEME_GIT_PROMPT_SUFFIX="%f"
ZSH_THEME_GIT_PROMPT_DIRTY=" %F{$GB[yellow]}●"
ZSH_THEME_GIT_PROMPT_CLEAN=""

# python venv: oh-my-zsh's own (venv) prefix is turned off, we draw it ourselves
export VIRTUAL_ENV_DISABLE_PROMPT=1
_gb_venv() {
  [[ -n $VIRTUAL_ENV ]] && print -n " %F{$GB[blue]}(${VIRTUAL_ENV:t})%f"
}

# user@host, only over ssh
_gb_host() {
  [[ -n $SSH_CONNECTION ]] && print -n "%F{$GB[fg4]}%n@%m%f %F{$GB[dim]}·%f "
}

# "took 12s" for commands that ran 3s or longer
_gb_took=""
_gb_preexec() { _gb_start=$EPOCHREALTIME }
_gb_precmd() {
  _gb_took=""
  if [[ -n $_gb_start ]]; then
    local -i secs=$(( EPOCHREALTIME - _gb_start ))
    unset _gb_start
    if (( secs >= 3 )); then
      local t=""
      (( secs >= 3600 )) && t+="$(( secs / 3600 ))h "
      (( secs >= 60 ))   && t+="$(( secs % 3600 / 60 ))m "
      t+="$(( secs % 60 ))s"
      _gb_took="  %F{$GB[dim]}took $t%f"
    fi
  fi
  # a blank line between commands (not before the very first prompt)
  (( ${+_gb_drawn} )) && print ""
  _gb_drawn=1
}
add-zsh-hook preexec _gb_preexec
add-zsh-hook precmd  _gb_precmd

# line 1: [user@host ·] dir [on branch ●] [(venv)] [✦jobs] [took Ns]
# line 2: › (yellow, red after a failed command)
PROMPT='$(_gb_host)%F{$GB[fg]}%B%(4~|…/%3~|%~)%b%f$(git_prompt_info)$(_gb_venv)%(1j. %F{$GB[dim]}✦%j%f.)${_gb_took}
%(?.%F{$GB[yellow]}.%F{$GB[red]})›%f '

# right side: exit code of a failed command, dim
RPROMPT='%(?..%F{$GB[dim]}✘ %?%f)'

# continuation lines (open quotes, loops, ...)
PROMPT2='%F{$GB[dim]}·%f '
