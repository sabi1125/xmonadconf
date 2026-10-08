#!/usr/bin/env python3
"""keep the screen on, and show the screensaver after a while of no input.

started by xmonad (myStartup). turns off X's own blanking and DPMS (which
switched the monitor off after 10 minutes), then watches the idle time:
  idle >= IDLE_SECS  -> open saver.py in a fullscreen alacritty
  any key/mouse      -> close it again (except while saver.py shows its
                        music view: it closes itself then, see FLAG)
nothing happens while a fullscreen window (a video, F11) is focused, or while
an app holds an inhibit: this script owns org.freedesktop.ScreenSaver on the
session bus, which firefox/chromium/mpv call while a *video* plays (music
alone doesn't inhibit, so the saver's music view still shows).
"""

import ctypes
import os
import subprocess
import time
from pathlib import Path

from gi.repository import Gio, GLib

IDLE_SECS = 5 * 60
SAVER = Path(__file__).resolve().parent / "saver.py"
FLAG = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "screensaver-media"  # set by saver.py


class XScreenSaverInfo(ctypes.Structure):
    _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int), ("kind", ctypes.c_int),
                ("til_or_since", ctypes.c_ulong), ("idle", ctypes.c_ulong),
                ("event_mask", ctypes.c_ulong)]


x11 = ctypes.CDLL("libX11.so.6")
xext = ctypes.CDLL("libXext.so.6")
xss = ctypes.CDLL("libXss.so.1")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XDefaultRootWindow.restype = ctypes.c_ulong
x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
x11.XSetScreenSaver.argtypes = [ctypes.c_void_p] + [ctypes.c_int] * 4
x11.XFlush.argtypes = [ctypes.c_void_p]
xext.DPMSDisable.argtypes = [ctypes.c_void_p]
xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(XScreenSaverInfo)
xss.XScreenSaverQueryInfo.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(XScreenSaverInfo)]

dpy = x11.XOpenDisplay(None)
root = x11.XDefaultRootWindow(dpy)
info = xss.XScreenSaverAllocInfo()


def keep_screen_on():
    x11.XSetScreenSaver(dpy, 0, 0, 0, 0)  # no X blanking (timeout 0 = off)
    xext.DPMSDisable(dpy)                 # never power the monitor down
    x11.XFlush(dpy)


def idle_ms():
    xss.XScreenSaverQueryInfo(dpy, root, info)
    return info.contents.idle


def xprop(*args):
    try:
        return subprocess.run(["xprop", *args], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def fullscreen_focused():
    win = xprop("-root", "_NET_ACTIVE_WINDOW").split()[-1:]
    return bool(win) and "FULLSCREEN" in xprop("-id", win[0], "_NET_WM_STATE")


# --- org.freedesktop.ScreenSaver: apps ask us to hold off while a video plays

IFACE = Gio.DBusNodeInfo.new_for_xml("""
<node><interface name="org.freedesktop.ScreenSaver">
  <method name="Inhibit"><arg type="s" direction="in"/><arg type="s" direction="in"/>
    <arg type="u" direction="out"/></method>
  <method name="UnInhibit"><arg type="u" direction="in"/></method>
  <method name="GetActive"><arg type="b" direction="out"/></method>
  <method name="SimulateUserActivity"/>
</interface></node>""").interfaces[0]

inhibits = {}  # cookie -> (sender, app, reason)
watches = {}   # sender -> bus_watch_name id, so a crashed app can't block forever
next_cookie = 1


def sender_gone(bus, sender):
    for c in [c for c, v in inhibits.items() if v[0] == sender]:
        del inhibits[c]
    Gio.bus_unwatch_name(watches.pop(sender))


def on_call(bus, sender, path, iface, method, params, invocation):
    global next_cookie
    if method == "Inhibit":
        app, reason = params.unpack()
        if "audio" in reason.lower():  # firefox also inhibits for plain music; let the saver's music view show
            invocation.return_value(GLib.Variant("(u)", (0,)))
            return
        cookie, next_cookie = next_cookie, next_cookie + 1
        inhibits[cookie] = (sender, app, reason)
        if sender not in watches:
            watches[sender] = Gio.bus_watch_name_on_connection(
                bus, sender, Gio.BusNameWatcherFlags.NONE, None, sender_gone)
        invocation.return_value(GLib.Variant("(u)", (cookie,)))
    elif method == "UnInhibit":
        inhibits.pop(params.unpack()[0], None)
        invocation.return_value(None)
    elif method == "GetActive":
        invocation.return_value(GLib.Variant("(b)", (saver_running(),)))
    else:  # SimulateUserActivity
        invocation.return_value(None)


def on_bus(bus, name):
    for path in ("/org/freedesktop/ScreenSaver", "/ScreenSaver"):
        bus.register_object_with_closures2(path, IFACE, on_call, None, None)


Gio.bus_own_name(Gio.BusType.SESSION, "org.freedesktop.ScreenSaver",
                 Gio.BusNameOwnerFlags.REPLACE, on_bus, None, None)

# --- main loop

saver, started = None, 0.0
last_on = 0.0


def saver_running():
    return saver is not None and saver.poll() is None


def tick():
    global saver, started, last_on
    if time.monotonic() - last_on > 60:  # re-apply now and then, in case something resets it
        keep_screen_on()
        last_on = time.monotonic()

    idle = idle_ms()
    running = saver_running()
    # (input in the first few seconds is ignored: that's the saver opening)
    if running and idle < 2000 and time.monotonic() - started > 3 and not FLAG.exists():
        saver.terminate()
        saver = None
    elif not running and idle >= IDLE_SECS * 1000 and not inhibits and not fullscreen_focused():
        saver = subprocess.Popen(["alacritty", "--class", "screensaver",
                                  "-o", "window.opacity=1", "-o", "window.padding={x=0,y=0}",
                                  "-e", "python3", str(SAVER)])
        started = time.monotonic()
    return True


GLib.timeout_add_seconds(1, tick)
GLib.MainLoop().run()
