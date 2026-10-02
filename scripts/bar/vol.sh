#!/bin/sh
# volume for the bar

if [ "$(pamixer --get-mute 2>/dev/null)" = true ]; then
    printf '<fc=#cc241d>󰝟</fc> <fc=#665c54>muted</fc>'
else
    printf '<fc=#665c54>󰕾</fc> %s%%' "$(pamixer --get-volume 2>/dev/null)"
fi
