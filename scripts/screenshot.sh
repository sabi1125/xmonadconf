#!/bin/sh
# screenshot.sh          -> full screen
# screenshot.sh region   -> select a region
# saved to ~/Pictures/Screenshots and copied to the clipboard

dir="$HOME/Pictures/Screenshots"
mkdir -p "$dir"
file="$dir/$(date +%Y-%m-%d_%H-%M-%S).png"

case "$1" in
    region) maim -u -s -b 2 -c 0.84,0.60,0.13,1 "$file" || exit 0 ;;
    *)      maim -u "$file" ;;
esac

xclip -selection clipboard -t image/png < "$file"
dunstify -a screenshot -I "$file" "screenshot" "$(basename "$file")"
