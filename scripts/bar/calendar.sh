#!/bin/sh
# show this month's calendar as a notification, today highlighted

today=$(date +%-d)
body=$(cal --color=never | tail -n +2 | sed '/^ *$/d' \
        | sed "s/\(^\| \)\($today\)\( \|$\)/\1<span foreground='#d79921'><b>\2<\/b><\/span>\3/")

dunstify -a calendar -r 9001 -t 8000 "$(date '+%A, %d %B %Y')" "<tt>$body</tt>"
