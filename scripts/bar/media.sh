#!/bin/sh
# media.sh -> now playing (click to toggle the controls popup),
#             or the date when no player is open

status=$(playerctl status 2>/dev/null)

if [ "$status" = Playing ] || [ "$status" = Paused ]; then
    text=$(playerctl metadata --format '{{artist}} - {{title}}' 2>/dev/null \
            | sed 's/^ - //; s/[<>]//g' | awk '{ print (length($0) > 30 ? substr($0, 1, 29) "…" : $0) }')
    printf '<action=`%s/.config/xmonad/scripts/bar/media-popup.sh`>%s</action>     ' "$HOME" "$text"
else
    printf '<fc=#7c6f64>󰃭 %s</fc>     ' "$(date '+%a %d %b')"
fi
