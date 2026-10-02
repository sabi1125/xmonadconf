#!/bin/sh
# toggle the floating now-playing card under the center bar

card="$HOME/.config/xmonad/scripts/bar/media-card.py"

pkill -f "python3 $card" || setsid -f python3 "$card" >/dev/null 2>&1
