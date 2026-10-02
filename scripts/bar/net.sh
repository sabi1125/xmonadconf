#!/bin/sh
# network status for the bar (iwd)

for dev in /sys/class/net/en*; do
    [ "$(cat "$dev/operstate" 2>/dev/null)" = up ] && {
        printf '<fc=#665c54>󰈀</fc> wired'
        exit 0
    }
done

wlan=$(ls /sys/class/net | grep '^wl' | head -n 1)
if [ -n "$wlan" ]; then
    ssid=$(iwctl station "$wlan" show 2>/dev/null \
            | sed -n 's/^ *Connected network *//p' | sed 's/ *$//' | cut -c1-14)
    if [ -n "$ssid" ]; then
        printf '<fc=#665c54>󰖩</fc> %s' "$ssid"
        exit 0
    fi
fi

printf '<fc=#cc241d>󰖪</fc> offline'
