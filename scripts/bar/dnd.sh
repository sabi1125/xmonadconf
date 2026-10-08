#!/bin/sh
# notification bell for the bar; crossed out while do-not-disturb is on,
# orange dot while dunst history holds notifications not yet marked seen (bell-seen.sh)

seen_file="${XDG_CACHE_HOME:-$HOME/.cache}/xmobar-bell-seen"
count=$(dunstctl count history 2>/dev/null || echo 0)
seen=$(cat "$seen_file" 2>/dev/null || echo 0)

# history shrank (popped or cleared): don't let old "seen" hide new ones
if [ "$count" -lt "$seen" ]; then
    echo "$count" > "$seen_file"
    seen=$count
fi

if [ "$(dunstctl is-paused 2>/dev/null)" = true ]; then
    printf '<fc=#d79921>󰂛</fc>'
elif [ "$count" -gt "$seen" ]; then
    printf '<icon=%s/xmobar/icons/bell-dot.xpm/>' "$HOME/.config/xmonad"
else
    printf '<fc=#665c54>󰂚</fc>'
fi
