#!/bin/sh
# streams animated music bars to xmobar; flat and dim while silent

command -v cava >/dev/null || { echo ''; exec sleep infinity; }

cava -p "$HOME/.config/xmonad/config/cava.conf" 2>/dev/null | awk -F';' '
BEGIN { split("▁ ▂ ▃ ▄ ▅ ▆ ▇ █", b, " ") }
{
    s = ""; quiet = 1
    for (i = 1; i < NF; i++) { s = s b[$i + 1]; if ($i > 0) quiet = 0 }
    printf "<fc=%s>%s</fc>\n", (quiet ? "#504945" : "#8ec07c"), s
    fflush()
}'
