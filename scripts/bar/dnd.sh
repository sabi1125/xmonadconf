#!/bin/sh
# notification bell for the bar; crossed out while do-not-disturb is on

if [ "$(dunstctl is-paused 2>/dev/null)" = true ]; then
    printf '<fc=#d79921>󰂛</fc>'
else
    printf '<fc=#665c54>󰂚</fc>'
fi
