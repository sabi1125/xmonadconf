#!/bin/sh
# mark current dunst history as seen, clearing the bell's orange dot
dunstctl count history > "${XDG_CACHE_HOME:-$HOME/.cache}/xmobar-bell-seen"
