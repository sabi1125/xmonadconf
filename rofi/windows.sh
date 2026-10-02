#!/bin/sh
# rofi script mode: window switcher that takes icons from the icon theme
# (by window class) instead of the window's own embedded icon.

if [ -n "$ROFI_INFO" ]; then
  xdotool windowactivate "$ROFI_INFO" >/dev/null 2>&1 &
  exit 0
fi

printf '\0no-custom\037true\n'

for id in $(xprop -root _NET_CLIENT_LIST | grep -o '0x[0-9a-f]*'); do
  class=$(xprop -id "$id" WM_CLASS | sed -n 's/.*", "\(.*\)"$/\1/p')
  title=$(xprop -id "$id" _NET_WM_NAME | sed -n 's/^[^"]*"\(.*\)"$/\1/p')
  [ -z "$title" ] && title=$(xprop -id "$id" WM_NAME | sed -n 's/^[^"]*"\(.*\)"$/\1/p')
  icon=$(printf '%s' "$class" | tr 'A-Z' 'a-z')
  printf '%s  %s\0icon\037%s\037info\037%s\n' "$class" "$title" "$icon" "$id"
done
