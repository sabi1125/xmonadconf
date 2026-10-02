#!/bin/sh
# wallpaper.sh        -> restore the saved wallpaper
# wallpaper.sh next   -> switch to a random different one and remember it

dir="$HOME/.config/xmonad/wallpapers"
state="$dir/.current"

if [ "$1" = next ]; then
    old=$(cat "$state" 2>/dev/null)
    new=$(find "$dir" -maxdepth 1 -type f \( -name '*.png' -o -name '*.jpg' \) \
            ! -name "$old" -printf '%f\n' | shuf -n 1)
    [ -n "$new" ] && printf '%s\n' "$new" > "$state"
fi

wp=$(cat "$state" 2>/dev/null)
if [ -n "$wp" ] && [ -f "$dir/$wp" ]; then
    feh --no-fehbg --bg-fill "$dir/$wp"
else
    xsetroot -solid '#282828'
fi
