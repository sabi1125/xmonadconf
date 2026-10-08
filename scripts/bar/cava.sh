#!/bin/sh
# streams braille music bars to xmobar (green -> yellow -> orange by height);
# a dim music note while silent

command -v cava >/dev/null || { echo ''; exec sleep infinity; }

# idle = frames of silence (24 fps) before swapping the bars for the note,
# so short gaps between songs don't flicker
cava -p "$HOME/.config/xmonad/config/cava.conf" 2>/dev/null | awk -F';' -v idle=36 '
BEGIN { split("⣀ ⣀ ⣤ ⣤ ⣶ ⣶ ⣿ ⣿", b, " "); quiet = idle }
function col(v) { return v >= 5 ? "#d65d0e" : v >= 3 ? "#d79921" : "#8ec07c" }
{
    s = ""; loud = 0
    for (i = 1; i < NF; i++) { s = s "<fc=" col($i) ">" b[$i + 1] "</fc>"; if ($i > 0) loud = 1 }
    quiet = loud ? 0 : quiet + 1
    if (quiet < idle)
        out = s
    else
        out = "<fc=#504945>     󰝚      </fc>"  # padded to the bars width so the island does not jump
    if (out != last) { print out; fflush(); last = out }
}'
