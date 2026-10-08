#!/bin/sh
# input method for the bar: EN or あ (fcitx5 + hazkey, toggled with ctrl+space).
# fcitx5-remote: 2 = active (japanese), 1 = inactive (english), 0 = no text field focused
# (you'd type english there anyway); no output = fcitx5 not running.
# polls quickly but only prints when the state changes.

last=
while :; do
    case "$(fcitx5-remote 2>/dev/null)" in
        2) s='<fc=#fabd2f>あ</fc>' ;;
        0|1) s='EN' ;;
        *) s='<fc=#665c54>--</fc>' ;;
    esac
    [ "$s" != "$last" ] && echo "$s" && last=$s
    sleep 0.3
done
