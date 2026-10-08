#!/usr/bin/env python3
# mellow: a caelestia-style shell for xmonad on X11.
#
#   frame      a thin border around the screen that grows out of the left bar,
#              with rounded inner corners. it reserves its space with struts,
#              so xmonad's avoidStruts keeps windows inside it.
#   left bar   arch button, workspaces, clock, status icons.
#   top        hover the middle of the top edge: dashboard / media / performance.
#   right      hover the right edge: volume slider. stay there: notifications
#              and session buttons.
#
# every surface is its own small window painted in the frame colour, so the
# pieces read as one shape. panels draw their own concave "flares" where they
# meet the frame; picom only rounds corners outwards (see picom.conf rules).
#
#   kill -USR1 <pid>   toggle the dashboard      (M-a in xmonad.hs)
#   kill -USR2 <pid>   toggle the sidebar        (M-S-a)

import calendar
import datetime
import getpass
import hashlib
import json
import math
import os
import re
import shlex
import signal
import socket
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import warnings

import cairo
import gi

warnings.filterwarnings("ignore", category=DeprecationWarning)  # set_wmclass: picom rules match on it

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GdkX11, GLib, Gtk, Pango  # noqa: E402,F401
from Xlib import X, Xatom  # noqa: E402

try:  # the terminal tab needs vte3 (pacman -S vte3)
    gi.require_version("Vte", "2.91")
    from gi.repository import Vte  # noqa: E402
except (ValueError, ImportError):
    Vte = None
from Xlib import display as xdisplay  # noqa: E402

# ----------------------------------------------------------------------------
# look

BAR = 40        # left bar width
EDGE = 8        # frame thickness on the other three sides
FLARE = 16      # radius of the concave curves where pieces meet the frame
ROUND = 18      # radius of the outer corners of panels
ALPHA = 0.7    # opacity of the frame and panels; picom blurs what shows through
CARD_ALPHA = 0.55  # cards inside the panels, on top of that
PAGE_H = 316    # height of the pages in the top panel (below the tabs)

FONT = "JetBrainsMono Nerd Font Propo"  # Propo: icons keep their real shape

# gruvbox colours on darker backgrounds, to match the rest of the rice
FRAME = "#111618"
CARD = "#171c1f"
CARD_HI = "#1e2326"
FG = "#ebdbb2"
DIM = "#a89984"
FAINT = "#665c54"
ACCENT = "#b8bb26"
RED = "#cc241d"

WORKSPACES = ["1", "2", "3", "4", "5"]  # xmonad.hs myWorkspaces
WEATHER_URL = "https://wttr.in/?format=j1"  # location from your IP
CELSIUS = True

CACHE = os.path.expanduser("~/.cache/mellow")

CSS = f"""
* {{ font-family: "{FONT}"; color: {FG}; }}
window {{ background: transparent; font-size: 12px; }}
label {{ font-size: inherit; }}

button {{
  background: none; border: none; box-shadow: none; text-shadow: none;
  padding: 0; margin: 0; min-height: 0; min-width: 0; border-radius: 10px;
  transition: all 150ms ease;
}}
button:hover {{ background: alpha({FG}, 0.08); }}
button:active {{ background: alpha({FG}, 0.16); }}

.icon {{ font-size: 16px; }}
.big {{ font-size: 22px; }}
.huge {{ font-size: 32px; font-weight: bold; }}
.dim, .dim * {{ color: {DIM}; }}
.faint {{ color: {FAINT}; }}
.bold {{ font-weight: bold; }}
.accent {{ color: {ACCENT}; }}
.small {{ font-size: 10px; }}

/* left bar */
.logo {{ font-size: 18px; color: {FG}; min-height: 32px; min-width: 32px; }}
.ws {{
  min-width: 10px; min-height: 10px; border-radius: 99px; margin: 3px 0;
  background: {FAINT}; transition: all 200ms ease;
}}
.ws.occupied {{ background: {DIM}; }}
.ws.active {{ background: {ACCENT}; min-height: 28px; }}
.ws:hover {{ background: {FG}; }}
.clock {{ font-weight: bold; font-size: 13px; }}
.barbtn {{ min-height: 30px; min-width: 30px; }}
.dot {{ color: {ACCENT}; font-size: 8px; }}
.ime {{ font-weight: bold; font-size: 11px; color: {DIM}; }}
.ime.ja {{ color: #fabd2f; font-size: 15px; }}

/* panels */
.card {{ background: alpha({CARD}, {CARD_ALPHA}); border-radius: 14px; padding: 10px; }}
.tab {{ padding: 5px 12px; border-radius: 10px; }}
.tab label {{ color: {DIM}; }}
.tab.active label {{ color: {FG}; }}
.tab.active {{ box-shadow: inset 0 -2px {ACCENT}; border-radius: 10px 10px 2px 2px; }}

.cal-head {{ font-weight: bold; }}
.cal-dow {{ color: {DIM}; font-size: 11px; }}
.cal-day {{ min-width: 28px; min-height: 21px; font-size: 11px; }}
.cal-dow {{ font-size: 10px; }}
.cal-nav {{ min-width: 22px; min-height: 20px; }}
.cal-other {{ color: {FAINT}; }}
.cal-today {{ background: {FG}; color: {FRAME}; border-radius: 99px; font-weight: bold; }}

.play {{ background: {FG}; border-radius: 99px; min-width: 52px; min-height: 30px; }}
.play label {{ color: {FRAME}; }}
.play:hover {{ background: {ACCENT}; }}
.ctl {{ min-width: 30px; min-height: 30px; border-radius: 99px; }}

progressbar trough {{ min-height: 4px; border-radius: 99px; background: {CARD_HI}; }}
progressbar progress {{ min-height: 4px; border-radius: 99px; background: {ACCENT}; }}

scale {{ padding: 0; }}
scale trough {{ min-width: 14px; border-radius: 99px; background: {CARD_HI}; }}
scale highlight {{ border-radius: 99px; background: {ACCENT}; }}
scale slider {{ min-width: 0; min-height: 0; background: none; border: none; box-shadow: none; margin: 0; }}

/* performance page */
.pcard {{ background: alpha({CARD}, {CARD_ALPHA}); border-radius: 14px; padding: 10px 12px; }}
.ptitle {{ font-size: 14px; font-weight: bold; }}
.pbig {{ font-size: 17px; font-weight: bold; }}
.term {{ background: alpha({CARD}, {CARD_ALPHA}); border-radius: 14px; padding: 10px; }}

/* media page */
.title {{ font-size: 17px; font-weight: bold; }}
.sq {{ min-width: 36px; min-height: 36px; border-radius: 10px; background: {CARD_HI}; }}
.sq:hover {{ background: alpha({FG}, 0.18); }}
.bigplay {{ min-width: 78px; min-height: 40px; border-radius: 12px; background: {FG}; }}
.bigplay label {{ color: {FRAME}; font-size: 18px; }}
.bigplay:hover {{ background: {ACCENT}; }}
.pill {{ background: {CARD_HI}; border-radius: 10px; padding: 6px 12px; }}
.lyric {{ color: {FAINT}; font-size: 13px; }}
.lyric.now {{ color: {FG}; font-weight: bold; font-size: 14px; }}
.lyric.near {{ color: {DIM}; }}

.notif {{ background: alpha({CARD}, {CARD_ALPHA}); border-radius: 14px; padding: 10px 12px; margin-bottom: 8px; }}
.notif-icon {{ background: {CARD_HI}; border-radius: 99px; min-width: 34px; min-height: 34px; color: {ACCENT}; }}
.session {{ min-width: 46px; min-height: 46px; border-radius: 14px; font-size: 20px; }}
.session label, .logo label {{ font-size: inherit; }}
.session.armed {{ background: {RED}; }}
scrolledwindow, viewport {{ background: transparent; border: none; }}
"""


def rgba(color, alpha=1.0):
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


# ----------------------------------------------------------------------------
# small helpers

def run(cmd, timeout=2):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def spawn(cmd):
    subprocess.Popen(cmd, shell=True, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pointer():
    _, x, y = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()
    return x, y


def in_rect(x, y, rect):
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh


def label(text="", *classes, xalign=None, ellipsize=False, width=None):
    lb = Gtk.Label(label=text)
    for c in classes:
        lb.get_style_context().add_class(c)
    if xalign is not None:
        lb.set_xalign(xalign)
    if ellipsize:
        lb.set_ellipsize(Pango.EllipsizeMode.END)
    if width:
        lb.set_max_width_chars(width)
    return lb


def button(child, on_click, *classes, tooltip=None):
    b = Gtk.Button()
    b.add(label(child, "icon") if isinstance(child, str) else child)
    b.set_relief(Gtk.ReliefStyle.NONE)
    b.set_can_focus(False)
    for c in classes:
        b.get_style_context().add_class(c)
    if tooltip:
        b.set_tooltip_text(tooltip)
    b.connect("clicked", lambda *_: on_click())
    return b


def box(vertical=False, spacing=0, *children, cls=None):
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,
                spacing=spacing)
    for ch in children:
        b.pack_start(ch, False, False, 0)
    if cls:
        b.get_style_context().add_class(cls)
    return b


def safely(fn):
    """run fn for a signal handler and keep the handler alive whatever happens:
    a handler that raises is dropped by glib, and the next signal would kill us"""
    try:
        fn()
    except Exception:
        import traceback
        traceback.print_exc()
    return True


def every(seconds, fn):
    fn()
    GLib.timeout_add(int(seconds * 1000), lambda: fn() or True)


# ----------------------------------------------------------------------------
# painting: panels hang off an edge of the frame

def edge_matrix(edge, pos):
    """local coords (u along the edge, v away from it) -> window coords"""
    return {
        "top": cairo.Matrix(1, 0, 0, 1, 0, pos),
        "bottom": cairo.Matrix(1, 0, 0, -1, 0, pos),
        "left": cairo.Matrix(0, 1, 1, 0, pos, 0),
        "right": cairo.Matrix(0, 1, -1, 0, pos, 0),
    }[edge]


def hanging_panel(cr, edge, pos, u, length, depth):
    """a panel attached to an edge: concave flares where it leaves the edge,
    rounded corners on the far side"""
    R, r = FLARE, ROUND
    cr.save()
    cr.transform(edge_matrix(edge, pos))
    cr.move_to(u - R, 0)
    cr.line_to(u + length + R, 0)
    cr.arc_negative(u + length + R, R, R, -math.pi / 2, -math.pi)
    cr.line_to(u + length, depth - r)
    cr.arc(u + length - r, depth - r, r, 0, math.pi / 2)
    cr.line_to(u + r, depth)
    cr.arc(u + r, depth - r, r, math.pi / 2, math.pi)
    cr.line_to(u, R)
    cr.arc_negative(u - R, R, R, 0, -math.pi / 2)
    cr.close_path()
    cr.restore()
    cr.fill()


def flare(cr, x, y, cx, cy):
    """fill the FLARE x FLARE square at (x, y), minus the circle around (cx, cy)"""
    cr.save()
    cr.rectangle(x, y, FLARE, FLARE)
    cr.clip()
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    cr.rectangle(x, y, FLARE, FLARE)
    cr.arc(cx, cy, FLARE, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


# ----------------------------------------------------------------------------
# windows

_xdisplay = None


def set_strut(win, left=0, right=0, top=0, bottom=0):
    global _xdisplay
    _xdisplay = _xdisplay or xdisplay.Display()
    d = _xdisplay
    sw, sh = d.screen().width_in_pixels, d.screen().height_in_pixels
    partial = [left, right, top, bottom,
               0, sh - 1 if left else 0, 0, sh - 1 if right else 0,
               0, sw - 1 if top else 0, 0, sw - 1 if bottom else 0]
    w = d.create_resource_object("window", win.get_window().get_xid())
    w.change_property(d.intern_atom("_NET_WM_STRUT_PARTIAL"), Xatom.CARDINAL, 32, partial)
    w.change_property(d.intern_atom("_NET_WM_STRUT"), Xatom.CARDINAL, 32, partial[:4])
    d.flush()


class Surface(Gtk.Window):
    """a borderless see-through window that paints itself"""

    def __init__(self, wmclass, rect, popup=False, clickable=True):
        super().__init__(type=Gtk.WindowType.POPUP if popup else Gtk.WindowType.TOPLEVEL)
        self.rect = rect
        x, y, w, h = rect
        self.set_wmclass(wmclass, wmclass)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_accept_focus(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        if not popup:
            self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_size_request(w, h)
        self.move(x, y)
        self.connect("draw", self._draw)
        self.connect("realize", lambda *_: self._shape())
        if not clickable:
            self.connect("realize", lambda *_: self.input_shape_combine_region(cairo.Region()))

    def _shape(self):
        """cut the window to the pixels paint() covers. picom blurs the whole
        window shape, so without this the see-through parts would blur too"""
        w, h = self.rect[2], self.rect[3]
        img = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(img)
        cr.set_source_rgba(1, 1, 1, 1)
        self.paint(cr)
        self.shape_combine_region(Gdk.cairo_region_create_from_surface(img))

    def _draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(*rgba(FRAME, ALPHA))
        self.paint(cr)
        return False

    def paint(self, cr):
        cr.paint()


class Strip(Surface):
    """a piece of the frame; reserves its space so xmonad tiles around it"""

    def __init__(self, rect, strut, clickable=True):
        super().__init__("MellowFrame", rect, clickable=clickable)
        self.strut = strut
        self.realize()
        if strut:
            set_strut(self, **strut)

    def show_lowered(self):
        self.show_all()
        self.get_window().lower()  # stay under fullscreen windows


class Corner(Surface):
    """the rounded inside corner of the frame"""

    def __init__(self, x, y, cx, cy):
        super().__init__("MellowFrame", (x, y, FLARE, FLARE), clickable=False)
        self.centre = (cx, cy)

    def paint(self, cr):
        flare(cr, 0, 0, *self.centre)


class Popup(Surface):
    """a panel that slides out of the frame and hides once the pointer has been
    away from it for a moment. while open it checks the pointer a few times a
    second; crossing events are unreliable for windows mapped under the pointer."""

    POLL = 100      # ms between pointer checks while open
    GRACE = 300     # ms the pointer may be away before the panel hides

    def __init__(self, wmclass, rect, keep_open=lambda x, y: False):
        super().__init__(wmclass, rect, popup=True)
        self.keep_open = keep_open
        self.pinned = False   # opened from the keyboard: stays until the pointer visits and leaves
        self._timer = None
        self._away = 0

    def open(self, pinned=False):
        self.pinned = pinned
        self._away = 0
        if not self.get_visible():
            self.on_open()
            self.show_all()
        self.get_window().raise_()
        if not self._timer:
            self._timer = GLib.timeout_add(self.POLL, self._poll)

    def close(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        if self.get_visible():
            self.hide()
            self.on_close()

    def toggle(self):
        self.close() if self.get_visible() else self.open(pinned=True)

    def on_open(self):
        pass

    def on_close(self):
        pass

    def contains(self, x, y):
        return in_rect(x, y, self.rect)

    def _poll(self):
        x, y = pointer()
        if self.contains(x, y):
            self.pinned = False
            self._away = 0
        elif self.keep_open(x, y) or self.pinned:
            self._away = 0
        else:
            self._away += self.POLL
            if self._away >= self.GRACE:
                self._timer = None
                self.close()
                return False
        return True


# ----------------------------------------------------------------------------
# data sources

class Workspaces(threading.Thread):
    """watches xmonad's EWMH properties: current desktop and which have windows"""

    def __init__(self, on_change):
        super().__init__(daemon=True)
        self.on_change = on_change

    def run(self):
        d = xdisplay.Display()
        root = d.screen().root
        atom = d.intern_atom
        self.cur, self.names, self.clients = atom("_NET_CURRENT_DESKTOP"), atom("_NET_DESKTOP_NAMES"), atom("_NET_CLIENT_LIST")
        self.wm_desktop, self.utf8 = atom("_NET_WM_DESKTOP"), atom("UTF8_STRING")
        self.layout = atom("_MELLOW_LAYOUT")  # set by myLogHook in xmonad.hs
        watched = set()
        root.change_attributes(event_mask=X.PropertyChangeMask)
        self.publish(d, root, watched)
        while True:
            ev = d.next_event()
            if ev.type == X.PropertyNotify and ev.atom in (self.cur, self.names, self.clients, self.wm_desktop, self.layout):
                time.sleep(0.02)  # let a burst of changes land, then read once
                while d.pending_events():
                    d.next_event()
                self.publish(d, root, watched)

    def publish(self, d, root, watched):
        try:
            names = root.get_full_property(self.names, self.utf8).value.decode().split("\0")
            cur = int(root.get_full_property(self.cur, Xatom.CARDINAL).value[0])
            clients = root.get_full_property(self.clients, Xatom.WINDOW).value
        except Exception:
            return
        try:
            layout = root.get_full_property(self.layout, self.utf8).value.decode()
        except Exception:
            layout = ""
        occupied = set()
        for c in clients:
            w = d.create_resource_object("window", c)
            try:
                if c not in watched:
                    w.change_attributes(event_mask=X.PropertyChangeMask, onerror=lambda *_: None)
                    watched.add(c)
                p = w.get_full_property(self.wm_desktop, Xatom.CARDINAL)
                if p:
                    occupied.add(int(p.value[0]))
            except Exception:
                pass  # closed while we looked
        GLib.idle_add(self.on_change, names, cur, occupied, layout)


def follow(cmd, on_line):
    """run cmd forever, handing each output line to on_line on the gtk thread"""
    def loop():
        while True:
            try:
                p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                for line in p.stdout:
                    GLib.idle_add(on_line, line.rstrip("\n"))
                p.wait()
            except OSError:
                pass
            time.sleep(3)
    threading.Thread(target=loop, daemon=True).start()


def in_thread(work, done):
    """run work() off the gtk thread, then done(result) back on it"""
    threading.Thread(target=lambda: GLib.idle_add(done, work()), daemon=True).start()


class Stats:
    """cpu, memory, disk and temperature, read straight from /proc and /sys"""

    def __init__(self):
        self._last = None
        self.temp_path = self._find_temp()

    @staticmethod
    def _find_temp():
        base = "/sys/class/hwmon"
        for h in sorted(os.listdir(base)) if os.path.isdir(base) else []:
            try:
                with open(f"{base}/{h}/name") as f:
                    if f.read().strip() in ("coretemp", "k10temp", "zenpower", "cpu_thermal"):
                        return f"{base}/{h}/temp1_input"
            except OSError:
                pass
        return None

    def cpu(self):
        with open("/proc/stat") as f:
            v = [int(n) for n in f.readline().split()[1:]]
        idle, total = v[3] + v[4], sum(v)
        last, self._last = self._last, (idle, total)
        if not last or total == last[1]:
            return 0.0
        return 1 - (idle - last[0]) / (total - last[1])

    @staticmethod
    def mem():
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                info[k] = int(v.split()[0])
        total = info["MemTotal"]
        used = total - info["MemAvailable"]
        return used / total, used / 1048576, total / 1048576

    @staticmethod
    def disk(path="/"):
        s = os.statvfs(path)
        total = s.f_blocks * s.f_frsize
        used = total - s.f_bavail * s.f_frsize
        return used / total, used / 1e9, total / 1e9

    def temp(self):
        try:
            with open(self.temp_path) as f:
                return int(f.read()) / 1000
        except (OSError, TypeError, ValueError):
            return None


def uptime_text():
    with open("/proc/uptime") as f:
        s = int(float(f.read().split()[0]))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    parts = ([f"{d} day{'s' * (d != 1)}"] if d else []) + \
            ([f"{h} hour{'s' * (h != 1)}"] if h else []) + [f"{m} minute{'s' * (m != 1)}"]
    return "up " + ", ".join(parts[:2])


WEATHER_ICONS = [  # (words in the description, glyph)
    (("thunder",), "\U000F0593"),
    (("snow", "sleet", "blizzard", "ice"), "\U000F0598"),
    (("rain", "drizzle", "shower"), "\U000F0597"),
    (("fog", "mist", "haze"), "\U000F0591"),
    (("partly",), "\U000F0595"),
    (("cloud", "overcast"), "\U000F0590"),
    (("sun", "clear"), "\U000F0599"),
]


def weather_icon(desc):
    desc = desc.lower()
    for words, glyph in WEATHER_ICONS:
        if any(w in desc for w in words):
            return glyph
    return "\U000F0590"


def fetch_weather():
    try:
        req = urllib.request.Request(WEATHER_URL, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=10) as r:
            j = json.load(r)
        now, today = j["current_condition"][0], j["weather"][0]
        unit = "C" if CELSIUS else "F"
        return {
            "temp": now[f"temp_{unit}"], "feels": now[f"FeelsLike{unit}"],
            "desc": now["weatherDesc"][0]["value"].strip(),
            "high": today[f"maxtemp{unit}"], "low": today[f"mintemp{unit}"], "unit": unit,
        }
    except Exception:
        return None


def fetch_art(url):
    """album art url -> local file path (downloads http art into the cache)"""
    if not url:
        return None
    if url.startswith("file://"):
        return urllib.request.url2pathname(url[7:])
    if url.startswith("http"):
        os.makedirs(CACHE, exist_ok=True)
        path = os.path.join(CACHE, "art-" + hashlib.sha1(url.encode()).hexdigest()[:16])
        if not os.path.exists(path):
            try:
                urllib.request.urlretrieve(url, path)
            except Exception:
                return None
        return path
    return None


# ----------------------------------------------------------------------------
# widgets

class Ring(Gtk.Overlay):
    """a circular gauge with an icon and a value inside"""

    def __init__(self, glyph, size=64, width=5):
        super().__init__()
        self.size, self.width, self.frac = size, width, 0.0
        area = Gtk.DrawingArea()
        area.set_size_request(size, size)
        area.connect("draw", self._draw)
        self.area = area
        self.add(area)
        inner = box(True, 0, label(glyph, "icon"), lbl := label("", "small", "bold"))
        inner.set_halign(Gtk.Align.CENTER)
        inner.set_valign(Gtk.Align.CENTER)
        self.value = lbl
        self.add_overlay(inner)

    def set(self, frac, text):
        self.frac = max(0.0, min(1.0, frac))
        self.value.set_text(text)
        self.area.queue_draw()

    def _draw(self, _w, cr):
        c, r = self.size / 2, self.size / 2 - self.width
        cr.set_line_width(self.width)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(*rgba(CARD_HI))
        cr.arc(c, c, r, 0, 2 * math.pi)
        cr.stroke()
        if self.frac > 0.005:
            cr.set_source_rgba(*rgba(FG))
            cr.arc(c, c, r, -math.pi / 2, -math.pi / 2 + 2 * math.pi * self.frac)
            cr.stroke()


class Art(Gtk.DrawingArea):
    """round album art, or a music note when there is none"""

    def __init__(self, size):
        super().__init__()
        self.size, self.pix, self.path = size, None, None
        self.set_size_request(size, size)
        self.connect("draw", self._draw)

    def set_path(self, path):
        if path == self.path:
            return
        self.path = path
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file(path)
            s = min(pb.get_width(), pb.get_height())  # centre square crop
            pb = pb.new_subpixbuf((pb.get_width() - s) // 2, (pb.get_height() - s) // 2, s, s)
            self.pix = pb.scale_simple(self.size, self.size, GdkPixbuf.InterpType.BILINEAR)
        except (GLib.Error, TypeError):
            self.pix = None
        self.queue_draw()

    def _draw(self, _w, cr):
        c = self.size / 2
        cr.new_path()
        cr.arc(c, c, c, 0, 2 * math.pi)
        if self.pix:
            cr.save()
            cr.clip()
            Gdk.cairo_set_source_pixbuf(cr, self.pix, 0, 0)
            cr.paint()
            cr.restore()
        else:
            cr.set_source_rgba(*rgba(CARD_HI))
            cr.fill()
            cr.set_source_rgba(*rgba(DIM))
            cr.select_font_face(FONT)
            cr.set_font_size(self.size * 0.4)
            ext = cr.text_extents("\U000F075A")
            cr.move_to(c - ext.width / 2 - ext.x_bearing, c - ext.height / 2 - ext.y_bearing)
            cr.show_text("\U000F075A")


class Calendar(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        today = datetime.date.today()
        self.year, self.month = today.year, today.month
        self.title = label("", "cal-head")
        head = Gtk.Box()
        head.pack_start(button("\U000F0141", lambda: self.shift(-1), "cal-nav"), False, False, 0)
        head.set_center_widget(self.title)
        head.pack_end(button("\U000F0142", lambda: self.shift(1), "cal-nav"), False, False, 0)
        self.pack_start(head, False, False, 0)
        self.grid = Gtk.Grid(column_homogeneous=True, row_spacing=4)
        self.pack_start(self.grid, False, False, 0)
        self.render()

    def shift(self, by):
        m = self.month - 1 + by
        self.year, self.month = self.year + m // 12, m % 12 + 1
        self.render()

    def reset(self):
        today = datetime.date.today()
        self.year, self.month = today.year, today.month
        self.render()

    def render(self):
        for ch in self.grid.get_children():
            self.grid.remove(ch)
        self.title.set_text(datetime.date(self.year, self.month, 1).strftime("%B %Y"))
        cal = calendar.Calendar(firstweekday=6)  # sunday first
        for i, name in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            self.grid.attach(label(name, "cal-dow"), i, 0, 1, 1)
        today = datetime.date.today()
        for row, week in enumerate(cal.monthdatescalendar(self.year, self.month)):
            for col, day in enumerate(week):
                lb = label(str(day.day), "cal-day")
                if day.month != self.month:
                    lb.get_style_context().add_class("cal-other")
                elif day == today:
                    lb.get_style_context().add_class("cal-today")
                self.grid.attach(lb, col, row + 1, 1, 1)
        self.grid.show_all()


class Meter(Gtk.DrawingArea):
    """a thin bar with a dot at its end"""

    def __init__(self, width=-1):
        super().__init__()
        self.frac = 0.0
        self.set_size_request(width, 10)
        self.set_hexpand(width < 0)
        self.connect("draw", self._draw)

    def set(self, frac):
        self.frac = max(0.0, min(1.0, frac))
        self.queue_draw()

    def _draw(self, w, cr):
        width, mid = w.get_allocated_width(), w.get_allocated_height() / 2
        x = 3 + (width - 10) * self.frac
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(5)
        cr.set_source_rgba(*rgba(CARD_HI))
        cr.move_to(x, mid)
        cr.line_to(width - 8, mid)
        cr.stroke()
        cr.set_source_rgba(*rgba(FG, 0.9))
        cr.arc(width - 3, mid, 2, 0, 2 * math.pi)
        cr.fill()
        if self.frac > 0.01:
            cr.set_source_rgba(*rgba(FG))
            cr.move_to(3, mid)
            cr.line_to(x, mid)
            cr.stroke()


class Cookie(Gtk.DrawingArea):
    """a wavy-edged blob with a big number in it"""

    def __init__(self, size=70):
        super().__init__()
        self.size, self.text = size, ""
        self.set_size_request(size, size)
        self.connect("draw", self._draw)

    def set_text(self, text):
        self.text = text
        self.queue_draw()

    def _draw(self, _w, cr):
        c, r = self.size / 2, self.size / 2 - 2
        for i in range(181):
            a = 2 * math.pi * i / 180
            rr = r * (0.93 + 0.07 * math.cos(8 * a))
            (cr.move_to if i == 0 else cr.line_to)(c + rr * math.cos(a), c + rr * math.sin(a))
        cr.close_path()
        cr.set_source_rgba(*rgba(CARD_HI))
        cr.fill()
        cr.set_source_rgba(*rgba(FG))
        cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(self.size * 0.3)
        e = cr.text_extents(self.text)
        cr.move_to(c - e.width / 2 - e.x_bearing, c - e.height / 2 - e.y_bearing)
        cr.show_text(self.text)


class Gauge(Gtk.Overlay):
    """an open ring (270 degrees) with a value and a caption inside"""

    def __init__(self, size, width=8, caption="Used"):
        super().__init__()
        self.size, self.width, self.frac = size, width, 0.0
        area = Gtk.DrawingArea()
        area.set_size_request(size, size)
        area.connect("draw", self._draw)
        self.area = area
        self.add(area)
        self.value = label("", "pbig")
        inner = box(True, 0, self.value, label(caption, "dim", "small"))
        inner.set_halign(Gtk.Align.CENTER)
        inner.set_valign(Gtk.Align.CENTER)
        self.add_overlay(inner)

    def set(self, frac):
        self.frac = max(0.0, min(1.0, frac))
        self.value.set_text(f"{self.frac * 100:.0f}%")
        self.area.queue_draw()

    def _draw(self, _w, cr):
        c, r = self.size / 2, self.size / 2 - self.width / 2 - 1
        start, sweep = math.radians(135), math.radians(270)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(self.width)
        cr.set_source_rgba(*rgba(CARD_HI))
        cr.arc(c, c, r, start + sweep * self.frac + 0.15, start + sweep)
        cr.stroke()
        if self.frac > 0.005:
            cr.set_source_rgba(*rgba(FG))
            cr.arc(c, c, r, start, start + sweep * self.frac)
            cr.stroke()


class Graph(Gtk.DrawingArea):
    """recent download (filled) and upload (line) rates"""

    def __init__(self, points=60):
        super().__init__()
        self.down, self.up = [0.0] * points, [0.0] * points
        self.set_size_request(-1, 30)
        self.set_hexpand(True)
        self.connect("draw", self._draw)

    def push(self, down, up):
        self.down = self.down[1:] + [down]
        self.up = self.up[1:] + [up]
        self.queue_draw()

    def _draw(self, w, cr):
        width, h = w.get_allocated_width(), w.get_allocated_height()
        top = max(max(self.down), max(self.up), 1024)
        n = len(self.down)

        def path(vals):
            for i, v in enumerate(vals):
                (cr.move_to if i == 0 else cr.line_to)(width * i / (n - 1), h - 2 - (h - 4) * v / top)

        path(self.down)
        cr.line_to(width, h)
        cr.line_to(0, h)
        cr.close_path()
        cr.set_source_rgba(*rgba(FG, 0.25))
        cr.fill()
        path(self.down)
        cr.set_source_rgba(*rgba(FG, 0.9))
        cr.set_line_width(1.5)
        cr.stroke()
        path(self.up)
        cr.set_source_rgba(*rgba(ACCENT, 0.9))
        cr.stroke()


def cpu_name():
    with open("/proc/cpuinfo") as f:
        for line in f:
            if line.startswith("model name"):
                name = line.split(":", 1)[1]
                name = re.sub(r"\(R\)|\(TM\)|\d+th Gen |CPU ", "", name)
                return " ".join(name.split())
    return "CPU"


def read_gpu():
    """(name, temperature, usage 0-1), or None when there is no way to ask"""
    out = run("nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu --format=csv,noheader,nounits")
    if out:
        try:
            name, temp, use = [x.strip() for x in out.splitlines()[0].split(",")]
            return name, float(temp), float(use) / 100
        except ValueError:
            pass
    for busy in sorted(os.listdir("/sys/class/drm")):  # amd
        path = f"/sys/class/drm/{busy}/device/gpu_busy_percent"
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return "GPU", None, int(f.read()) / 100
            except (OSError, ValueError):
                pass
    return None


def disks():
    """{disk: [mountpoints]} for every disk with something mounted from it"""
    found = {}
    with open("/proc/mounts") as f:
        for line in f:
            dev, mnt = line.split()[:2]
            if not dev.startswith("/dev/") or "zram" in dev or "loop" in dev:
                continue
            part = os.path.basename(os.path.realpath(dev))
            parent = os.path.basename(os.path.dirname(os.path.realpath(f"/sys/class/block/{part}")))
            disk = parent if os.path.exists(f"/sys/block/{parent}") else part
            found.setdefault(disk, []).append(mnt.replace("\\040", " "))
    return found


def disk_usage(mounts):
    seen, used, total = set(), 0, 0
    for m in mounts:
        try:
            st = os.statvfs(m)
        except OSError:
            continue
        key = (st.f_blocks, st.f_bfree, st.f_fsid)
        if key in seen:
            continue  # the same filesystem mounted twice
        seen.add(key)
        total += st.f_blocks * st.f_frsize
        used += (st.f_blocks - st.f_bavail) * st.f_frsize
    return used, total


def net_bytes():
    rx = tx = 0
    with open("/proc/net/dev") as f:
        for line in f.readlines()[2:]:
            name, data = line.split(":", 1)
            if name.strip() == "lo":
                continue
            v = data.split()
            rx, tx = rx + int(v[0]), tx + int(v[8])
    return rx, tx


def human(n, rate=False):
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}{'/s' if rate else ''}" if unit == "B" else f"{n:.1f} {unit}{'/s' if rate else ''}"
        n /= 1024


# ----------------------------------------------------------------------------
# the pieces

class Media:
    """now-playing state from playerctl, shared by the dashboard and media tab.
    follows whichever player was active last, or the one picked with next_player()"""

    FMT = "\x1f".join(["{{status}}", "{{title}}", "{{artist}}", "{{album}}",
                       "{{mpris:artUrl}}", "{{mpris:length}}", "{{playerName}}", "{{playerInstance}}"])

    def __init__(self):
        self.listeners = []
        self.state = None
        self.player = None  # a playerctl instance name, or None for "most recent"
        self._proc = None
        threading.Thread(target=self._follow, daemon=True).start()

    def _sel(self):
        return f"-p {shlex.quote(self.player)}" if self.player else ""

    def ctl(self, args):
        spawn(f"playerctl {self._sel()} {args}")

    def position(self):
        try:
            return float(run(f"playerctl {self._sel()} position"))
        except ValueError:
            return None

    def next_player(self):
        players = run("playerctl -l").split()
        if not players:
            return
        cur = self.player or (self.state or {}).get("instance")
        i = players.index(cur) + 1 if cur in players else 0
        self.player = players[i % len(players)]
        if self._proc:
            self._proc.terminate()  # _follow restarts it for the new player

    def _follow(self):
        while True:
            try:
                self._proc = subprocess.Popen(f"playerctl {self._sel()} -F metadata --format '{self.FMT}'",
                                              shell=True, stdout=subprocess.PIPE,
                                              stderr=subprocess.DEVNULL, text=True)
                for line in self._proc.stdout:
                    GLib.idle_add(self._line, line.rstrip("\n"))
                killed = self._proc.wait() < 0
            except OSError:
                killed = False
            time.sleep(0.1 if killed else 3)

    def _line(self, line):
        f = line.split("\x1f")
        if len(f) < 8 or not (f[1] or f[2]):
            self.state = None
            self._emit()
            return
        status, title, artist, album, art, length, player, instance = f[:8]
        self.state = {"status": status, "title": title, "artist": artist, "album": album,
                      "length": int(length) / 1e6 if length.isdigit() else 0,
                      "player": player, "instance": instance, "art": None}
        self._emit()
        in_thread(lambda: fetch_art(art), self._art)

    def _art(self, path):
        if self.state is not None:
            self.state["art"] = path
            self._emit()

    def _emit(self):
        for fn in self.listeners:
            fn(self.state)


def fetch_lyrics(artist, title, length):
    """[(seconds or None, line)] from lrclib.net, synced when it has timings"""
    q = urllib.parse.urlencode({"artist_name": artist, "track_name": title, "duration": round(length)})
    j = None
    for url in (f"https://lrclib.net/api/get?{q}",
                "https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": f"{artist} {title}"})):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mellow-shell"})
            with urllib.request.urlopen(req, timeout=8) as r:
                j = json.load(r)
            if isinstance(j, list):
                j = j[0] if j else None
            if j:
                break
        except Exception:
            j = None
    if not j:
        return []
    if j.get("syncedLyrics"):
        lines = []
        for raw in j["syncedLyrics"].splitlines():
            if raw.startswith("[") and "]" in raw:
                stamp, text = raw[1:].split("]", 1)
                try:
                    m, sec = stamp.split(":")
                    lines.append((int(m) * 60 + float(sec), text.strip() or "♪"))
                except ValueError:
                    pass
        return lines
    return [(None, ln) for ln in (j.get("plainLyrics") or "").splitlines()]


class Cava:
    """runs cava with raw output while something wants the bars"""

    CONF = """[general]
framerate = 30
bars = {bars}
autosens = 1
sleep_timer = 0
[input]
method = pipewire
source = auto
[output]
method = raw
channels = mono
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 100
bar_delimiter = 59
frame_delimiter = 10
[smoothing]
monstercat = 1
noise_reduction = 60
"""

    def __init__(self, bars, on_frame):
        self.bars, self.on_frame = bars, on_frame
        self.proc = None

    def start(self):
        if self.proc or not GLib.find_program_in_path("cava"):
            return
        os.makedirs(CACHE, exist_ok=True)
        conf = os.path.join(CACHE, "cava-ring.conf")
        with open(conf, "w") as f:
            f.write(self.CONF.format(bars=self.bars))
        self.proc = proc = subprocess.Popen(["cava", "-p", conf], stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, text=True)

        def read():
            for line in proc.stdout:
                vals = [int(v) / 100 for v in line.strip().split(";") if v.isdigit()]
                GLib.idle_add(self.on_frame, vals)
        threading.Thread(target=read, daemon=True).start()

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None
            GLib.idle_add(self.on_frame, [])


class ArtProgress(Art):
    """round album art inside a ring that fills as the song plays, as a gentle
    wave like the media page's bar. click the ring to seek"""

    SWEEP = 2 * math.pi  # the whole way round; less leaves a gap at the bottom
    START = math.pi / 2 + (2 * math.pi - SWEEP) / 2  # where the ring begins

    def __init__(self, size, art, on_seek):
        super().__init__(art)
        self.art_size, self.box_size = art, size
        self.set_size_request(size, size)
        self.frac, self.phase, self.amp = 0.0, 0.0, 0.0
        self.playing = False
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self._click)
        self.on_seek = on_seek

    def step(self, dt):
        """advance the wave; called every frame while the dashboard is open"""
        self.phase += dt * 6
        target = 2.2 if self.playing else 0.0
        self.amp += (target - self.amp) * min(1, dt * 6)  # wave eases in and out
        if self.amp > 0.01 or target:
            self.queue_draw()

    def set_frac(self, frac):
        frac = max(0.0, min(1.0, frac))
        if abs(frac - self.frac) > 0.0005:
            self.frac = frac
            self.queue_draw()

    def _click(self, _w, ev):
        c = self.box_size / 2
        dx, dy = ev.x - c, ev.y - c
        if math.hypot(dx, dy) < self.art_size / 2:
            return  # clicks on the art itself do nothing
        along = (math.atan2(dy, dx) - self.START) % (2 * math.pi)  # clockwise from the start
        if along <= self.SWEEP:
            self.on_seek(along / self.SWEEP)  # clicks in the gap do nothing

    def _draw(self, w, cr):
        c = self.box_size / 2
        r = (self.box_size + self.art_size) / 4  # halfway between the art and the edge
        start = self.START
        end = start + self.SWEEP * self.frac
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(4)
        cr.set_source_rgba(*rgba(DIM, 0.25))  # the track still to come
        cr.arc(c, c, r, start, start + self.SWEEP)
        cr.stroke()
        if self.frac > 0.002:
            # played: a wave riding on the ring, same wavelength as the media bar
            cr.set_source_rgba(*rgba(FG))
            steps = max(2, int((end - start) * r / 1.5))
            for i in range(steps + 1):
                a = start + (end - start) * i / steps
                rr = r + self.amp * math.sin((a - start) * r / 3.2 - self.phase)
                (cr.move_to if i == 0 else cr.line_to)(c + rr * math.cos(a), c + rr * math.sin(a))
            cr.stroke()
        cr.set_source_rgba(*rgba(FG))  # where the song is now
        cr.arc(c + r * math.cos(end), c + r * math.sin(end), 4.5, 0, 2 * math.pi)
        cr.fill()
        off = (self.box_size - self.art_size) / 2
        cr.translate(off, off)
        super()._draw(w, cr)


class ArtRing(Art):
    """round album art with music bars standing around it, like a sun"""

    def __init__(self, size, art):
        super().__init__(art)
        self.art_size, self.box_size = art, size
        self.set_size_request(size, size)
        self.levels = []

    def set_levels(self, vals):
        self.levels = vals + vals[::-1]  # mirrored, so the ring is symmetric
        self.queue_draw()
        return False

    def _draw(self, w, cr):
        c = self.box_size / 2
        n = len(self.levels) or 48
        inner = self.art_size / 2 + 8
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(3)
        cr.set_source_rgba(*rgba(FG, 0.9))
        for i in range(n):
            v = self.levels[i] if self.levels else 0
            a = 2 * math.pi * i / n - math.pi / 2
            length = 2 + v * (c - inner - 4)
            cr.move_to(c + inner * math.cos(a), c + inner * math.sin(a))
            cr.line_to(c + (inner + length) * math.cos(a), c + (inner + length) * math.sin(a))
        cr.stroke()
        off = (self.box_size - self.art_size) / 2
        cr.translate(off, off)
        super()._draw(w, cr)


class WaveBar(Gtk.DrawingArea):
    """progress line: a gentle wave for the part already played. click to seek"""

    def __init__(self, on_seek):
        super().__init__()
        self.frac, self.phase, self.amp = 0.0, 0.0, 0.0
        self.playing = False
        self.set_size_request(-1, 22)
        self.set_hexpand(True)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", lambda w, e: on_seek(max(0, min(1, e.x / w.get_allocated_width()))))
        self.connect("draw", self._draw)

    def step(self, dt):
        self.phase += dt * 6
        target = 3.0 if self.playing else 0.0
        self.amp += (target - self.amp) * min(1, dt * 6)  # wave eases in and out
        self.queue_draw()

    def _draw(self, w, cr):
        width, h = w.get_allocated_width(), w.get_allocated_height()
        mid, x = h / 2, max(0, min(width, width * self.frac))
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        # played: a wave
        cr.set_line_width(3)
        cr.set_source_rgba(*rgba(FG))
        cr.move_to(0, mid)
        for px in range(0, int(x) - 4):
            cr.line_to(px, mid + self.amp * math.sin(px / 3.2 - self.phase))
        cr.stroke()
        # still to come: a flat line ending in a dot
        cr.set_source_rgba(*rgba(FAINT))
        if x + 6 < width - 4:
            cr.move_to(x + 6, mid)
            cr.line_to(width - 4, mid)
            cr.stroke()
        cr.arc(width - 2, mid, 2, 0, 2 * math.pi)
        cr.fill()
        # the thumb
        cr.set_source_rgba(*rgba(FG))
        cr.set_line_width(4)
        cr.move_to(x, mid - 8)
        cr.line_to(x, mid + 8)
        cr.stroke()


def fmt_time(s):
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


class Dashboard(Popup):
    W, H = 720, 240  # the panel below the top edge; grows to fit the content

    def __init__(self, screen, media, stats, keep_open):
        sx, sy, sw, sh = screen
        self.cx = (BAR + sw - EDGE) // 2
        super().__init__("MellowTop", self._rect(), keep_open)
        self.media, self.stats = media, stats
        self.is_open = False
        self.grabbed = False
        self.anim = None
        self.pos, self.pos_at = 0.0, time.monotonic()
        self.lyrics, self.lyrics_key, self.lyric_i = [], None, -2
        self.cava = Cava(24, lambda v: self.p_art.set_levels(v))
        self.weather = None
        self.weather_at = 0
        self.timers = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(EDGE + 4)
        root.set_margin_bottom(12)
        root.set_margin_start(FLARE + 10)
        root.set_margin_end(FLARE + 10)
        self.add(root)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(180)
        tabs = Gtk.Box(spacing=4, homogeneous=True)
        self.tabs = {}
        for name, glyph, page in [("Dashboard", "\U000F056E", self._dashboard()),
                                  ("Media", "\U000F075A", self._media()),
                                  ("Performance", "\U000F04C5", self._performance()),
                                  ("Terminal", "\U000F018D", self._terminal())]:
            self.stack.add_named(page, name)
            inner = box(False, 8, label(glyph, "icon"), label(name))
            inner.set_halign(Gtk.Align.CENTER)
            t = button(inner, lambda n=name: self.show_tab(n), "tab")
            self.tabs[name] = t
            tabs.pack_start(t, True, True, 0)
        root.pack_start(tabs, False, False, 0)
        root.pack_start(self.stack, True, True, 0)
        self.stack.set_size_request(-1, PAGE_H)
        self.show_tab("Dashboard")
        self._fit(root)
        media.listeners.append(self._on_media)
        self.refresh_weather()  # so it is there the first time the panel opens

    def _rect(self):
        return (self.cx - self.W // 2 - FLARE, 0, self.W + 2 * FLARE, EDGE + self.H)

    def _fit(self, root):
        """grow the panel to the tallest page, so nothing spills past its edge"""
        root.show_all()
        _, nat = root.get_preferred_size()
        self.W = max(self.W, nat.width + root.get_margin_start() + root.get_margin_end() - 2 * FLARE)
        self.H = max(self.H, nat.height + root.get_margin_top() + root.get_margin_bottom() - EDGE)
        self.rect = self._rect()
        self.set_size_request(self.rect[2], self.rect[3])
        self.move(self.rect[0], self.rect[1])

    def paint(self, cr):
        # starts below the top edge: overlapping it would double the see-through colour
        hanging_panel(cr, "top", EDGE, FLARE, self.W, self.H)

    def show_tab(self, name):
        self.stack.set_visible_child_name(name)
        self._media_view()
        self._keyboard()
        if name == "Performance" and hasattr(self, "q_disk_gauge"):
            self._update_disk()
            in_thread(read_gpu, self._on_gpu)
        for n, t in self.tabs.items():
            (t.get_style_context().add_class if n == name else t.get_style_context().remove_class)("active")

    # pages ------------------------------------------------------------------

    def _dashboard(self):
        g = Gtk.Grid(column_spacing=10, row_spacing=10)
        g.set_hexpand(True)
        g.set_vexpand(True)

        def fill(card, h=True, v=False):
            """stretch a card over its grid cell, keeping what is inside it centred"""
            inner = Gtk.Box()
            for ch in card.get_children():
                card.remove(ch)
                inner.pack_start(ch, False, False, 0)
            inner.set_spacing(card.get_spacing())
            inner.set_orientation(card.get_orientation())
            inner.set_halign(Gtk.Align.CENTER)
            inner.set_valign(Gtk.Align.CENTER)
            card.pack_start(inner, True, True, 0)
            card.set_hexpand(h)
            card.set_vexpand(v)
            return card

        # weather
        self.w_icon, self.w_temp = label("\U000F0590", "big"), label("--°", "big", "bold")
        self.w_desc, self.w_more = label("", "small", xalign=0), label("", "dim", "small", xalign=0)
        w = box(False, 12, self.w_icon, self.w_temp, box(True, 0, self.w_desc, self.w_more), cls="card")
        w.set_size_request(190, -1)
        g.attach(fill(w), 0, 0, 1, 1)

        # clock
        self.c_h, self.c_m, self.c_p = label("", "huge"), label("", "huge"), label("", "dim", "bold")
        c = box(True, 0, self.c_h, label("•••", "accent"), self.c_m, self.c_p, cls="card")

        # user
        hostname = socket.gethostname()
        self.u_up = label("", "dim", "small", xalign=0)
        u = box(False, 18, label("", "huge"),
                box(True, 2, label(f"{getpass.getuser()}@{hostname}", "bold", xalign=0), self.u_up), cls="card")
        u.get_children()[1].set_valign(Gtk.Align.CENTER)
        g.attach(fill(u), 1, 0, 1, 1)

        # calendar
        self.cal = Calendar()
        cal = box(True, 0, self.cal, cls="card")
        g.attach(fill(c, v=True), 0, 1, 1, 1)
        g.attach(fill(cal, v=True), 1, 1, 1, 1)

        # rings
        self.d_cpu, self.d_mem, self.d_disk = Ring("\U000F0EE0", 56), Ring("\U000F035B", 56), Ring("\U000F02CA", 56)
        rings = box(True, 8, self.d_cpu, self.d_mem, self.d_disk, cls="card")
        g.attach(fill(rings, h=False, v=True), 2, 0, 1, 2)

        # now playing
        self.m_art = ArtProgress(100, 78, self._seek)
        self.m_title = label("Nothing playing", "bold", ellipsize=True, width=18)
        self.m_artist = label("", "dim", "small", ellipsize=True, width=20)
        self.m_play = label("\U000F040A", "icon")
        controls = box(False, 6,
                       button("\U000F04AE", lambda: self.media.ctl("previous"), "ctl"),
                       button(self.m_play, lambda: self.media.ctl("play-pause"), "play"),
                       button("\U000F04AD", lambda: self.media.ctl("next"), "ctl"))
        controls.set_halign(Gtk.Align.CENTER)
        art = box(False, 0, self.m_art)
        art.set_halign(Gtk.Align.CENTER)
        m = box(True, 8, art, self.m_title, self.m_artist, controls, cls="card")
        m.set_size_request(170, -1)
        g.attach(fill(m, v=True), 3, 0, 1, 2)

        # the clock card takes what the weather card leaves
        c.set_size_request(190, -1)
        for child in (self.c_h, self.c_m):
            child.set_halign(Gtk.Align.CENTER)
        return g

    def _media(self):
        self.p_art = ArtRing(160, 100)
        self.p_art.set_valign(Gtk.Align.CENTER)

        # middle: what is playing and the controls
        self.p_title = label("Nothing playing", "title", xalign=0, ellipsize=True, width=22)
        self.p_artist = label("", xalign=0, ellipsize=True, width=28)
        self.p_album = label("", "dim", xalign=0, ellipsize=True, width=28)
        self.p_pos, self.p_len = label("0:00", "small", "dim"), label("0:00", "small", "dim")
        self.p_wave = WaveBar(self._seek)
        bar = Gtk.Box(spacing=10)
        bar.pack_start(self.p_pos, False, False, 0)
        bar.pack_start(self.p_wave, True, True, 0)
        bar.pack_start(self.p_len, False, False, 0)
        self.p_play = label("\U000F040A")
        controls = box(False, 8,
                       button("\U000F049D", lambda: self.media.ctl("shuffle toggle"), "sq", tooltip="shuffle"),
                       button("\U000F04AE", lambda: self.media.ctl("previous"), "sq"),
                       button(self.p_play, lambda: self.media.ctl("play-pause"), "bigplay"),
                       button("\U000F04AD", lambda: self.media.ctl("next"), "sq"),
                       button("\U000F0456", self._loop, "sq", tooltip="repeat"))
        controls.set_halign(Gtk.Align.CENTER)
        info = box(True, 4, self.p_title, self.p_artist, self.p_album)
        info.pack_start(bar, False, False, 14)
        info.pack_start(controls, False, False, 0)
        info.set_hexpand(True)
        info.set_size_request(300, -1)
        info.set_valign(Gtk.Align.CENTER)

        # right: lyrics, and which player is in charge
        head = Gtk.Box(spacing=8)
        head.pack_start(label("\U000F0CB8", "icon"), False, False, 0)
        head.pack_start(label("Lyrics", "bold"), False, False, 0)
        head.pack_end(button("\U000F0450", self._retry_lyrics, "ctl", tooltip="look again"), False, False, 0)
        self.l_stack = Gtk.Stack()
        self.l_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        none = box(True, 8, label("\U000F0CB8", "huge", "faint"), lb := label("No lyrics found", "dim"))
        self.l_none_text = lb
        none.set_valign(Gtk.Align.CENTER)
        self.l_stack.add_named(none, "none")
        self.l_lines = [label("", "lyric", ellipsize=True, width=26) for _ in range(5)]
        synced = box(True, 6, *self.l_lines)
        synced.set_valign(Gtk.Align.CENTER)
        self.l_stack.add_named(synced, "synced")
        self.l_plain = label("", "lyric", xalign=0)
        self.l_plain.set_line_wrap(True)
        self.l_plain.set_max_width_chars(28)
        plain = Gtk.ScrolledWindow()
        plain.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        plain.add(self.l_plain)
        self.l_stack.add_named(plain, "plain")
        self.p_player = label("", ellipsize=True, width=16)
        pill = button(box(False, 8, label("\U000F0379", "icon"), self.p_player, label("\U000F0140", "icon")),
                      self.media.next_player, "pill", tooltip="switch player")
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_size_request(220, -1)
        right.pack_start(head, False, False, 0)
        right.pack_start(self.l_stack, True, True, 0)
        right.pack_end(pill, False, False, 0)

        page = Gtk.Box(spacing=26)
        page.set_margin_start(6)
        page.pack_start(self.p_art, False, False, 0)
        page.pack_start(info, True, True, 0)
        page.pack_start(right, False, False, 0)
        page.set_size_request(-1, 170)
        return page

    def _performance(self):
        def chip(title, sub, glyph):
            ring = Ring(glyph, 38, 3)
            name = label(sub, "dim", xalign=0, ellipsize=True, width=28)
            head = box(True, 0, label(title, "ptitle", xalign=0), name)
            head.set_valign(Gtk.Align.CENTER)
            temp = label("--", "small")
            meter = Meter()
            cookie = Cookie(50)
            left = box(True, 6, box(False, 10, ring, head))
            tbox = Gtk.Box(spacing=6)
            tbox.pack_start(label("\U000F050F", "dim"), False, False, 0)
            tbox.pack_start(temp, False, False, 0)
            tbox.pack_start(meter, True, True, 4)
            left.pack_start(tbox, False, False, 0)
            left.set_hexpand(True)
            right = box(True, 4, label("Usage", "dim", "small"), cookie)
            right.set_valign(Gtk.Align.CENTER)
            card = Gtk.Box(spacing=12)
            card.get_style_context().add_class("pcard")
            card.pack_start(left, True, True, 0)
            card.pack_start(right, False, False, 0)
            return card, ring, name, temp, meter, cookie

        cpu, self.q_cpu_ring, _, self.q_cpu_temp, self.q_cpu_meter, self.q_cpu_use = \
            chip("CPU", cpu_name(), "\U000F0EE0")
        gpu, self.q_gpu_ring, self.q_gpu_name, self.q_gpu_temp, self.q_gpu_meter, self.q_gpu_use = \
            chip("GPU", "looking…", "\U000F08AE")
        for r in (self.q_cpu_ring, self.q_gpu_ring):
            r.value.hide()
            r.value.set_no_show_all(True)
        row1 = Gtk.Box(spacing=10, homogeneous=True)
        row1.pack_start(cpu, True, True, 0)
        row1.pack_start(gpu, True, True, 0)

        # storage
        self.disks = disks()
        root_disk = next((d for d, ms in self.disks.items() if "/" in ms), None)
        self.disk = root_disk or next(iter(self.disks), None)
        self.q_disk_gauge = Gauge(70, 6)
        self.q_disk_text = label("", "dim", "small", xalign=0)
        self.q_disk_name = label("", "bold")
        pill = button(box(False, 6, label("\U000F02CA"), self.q_disk_name, label("\U000F0140")),
                      self._next_disk, "pill", tooltip="switch disk")
        pill.set_halign(Gtk.Align.START)
        info = box(True, 3, label("Storage", "ptitle", xalign=0), self.q_disk_text, pill)
        info.set_valign(Gtk.Align.CENTER)
        storage = box(False, 12, self.q_disk_gauge, info, cls="pcard")

        # network: rates on one line, totals since boot in the corner
        self.net_last = None
        self.q_graph = Graph()
        self.q_down, self.q_up = label("", "small"), label("", "small")
        self.q_total = label("", "dim", "small")
        head = box(False, 8, label("\U000F04E1", "icon"), label("Network", "ptitle"))
        head.pack_end(self.q_total, False, False, 0)
        rates = Gtk.Box(spacing=6)
        rates.pack_start(label("\U000F01DA", "dim"), False, False, 0)
        rates.pack_start(self.q_down, False, False, 0)
        rates.pack_end(self.q_up, False, False, 0)
        rates.pack_end(label("\U000F0552", "dim"), False, False, 0)
        net = box(True, 4, head, cls="pcard")
        net.pack_start(self.q_graph, False, False, 0)
        net.pack_start(rates, False, False, 0)
        net.set_size_request(250, -1)

        # memory
        self.q_mem_gauge = Gauge(70, 6)
        self.q_mem_text = label("", "dim", "small", xalign=0)
        info = box(True, 3, box(False, 6, label("\U000F035B", "icon"), label("Memory", "ptitle")), self.q_mem_text)
        info.set_valign(Gtk.Align.CENTER)
        memory = box(False, 12, self.q_mem_gauge, info, cls="pcard")

        row2 = Gtk.Box(spacing=10)
        row2.pack_start(storage, True, True, 0)
        row2.pack_start(net, True, True, 0)
        row2.pack_start(memory, True, True, 0)
        page = box(True, 8, row1, row2)
        for row in (row1, row2):
            page.set_child_packing(row, True, True, 0, Gtk.PackType.START)
        return page

    def _next_disk(self):
        self.disks = disks()
        names = sorted(self.disks)
        if names:
            i = names.index(self.disk) + 1 if self.disk in names else 0
            self.disk = names[i % len(names)]
            self._update_disk()

    def _update_disk(self):
        if not self.disk:
            return
        used, total = disk_usage(self.disks.get(self.disk, []))
        self.q_disk_gauge.set(used / total if total else 0)
        self.q_disk_text.set_text(f"{human(used)} / {human(total)}")
        self.q_disk_name.set_text(self.disk)

    def _terminal(self):
        if Vte is None:
            return box(True, 8, label("\U000F018D", "huge", "faint"),
                       label("the terminal needs vte3:  sudo pacman -S vte3", "dim"), cls="term")
        self.term = term = Vte.Terminal()
        term.set_font(Pango.FontDescription(f"{FONT} 11"))
        palette = ["#171c1f", "#cc241d", "#98971a", "#d79921", "#458588", "#b16286", "#689d6a", "#a89984",
                   "#928374", "#fb4934", "#b8bb26", "#fabd2f", "#83a598", "#d3869b", "#8ec07c", "#ebdbb2"]
        colors = []
        for c in palette:
            g = Gdk.RGBA()
            g.parse(c)
            colors.append(g)
        fg, bg = Gdk.RGBA(), Gdk.RGBA()
        fg.parse(FG)
        bg.parse(CARD)
        bg.alpha = 0.0  # the card behind it shows through
        term.set_colors(fg, bg, colors)
        term.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        term.set_size(80, 8)  # vte asks for 24 rows by default, which would make the whole panel tall
        term.set_size_request(-1, 180)
        term.connect("child-exited", lambda *_: self._spawn_shell())
        self._spawn_shell()
        page = box(False, 0, cls="term")
        page.pack_start(term, True, True, 0)
        return page

    def _spawn_shell(self):
        shell = os.environ.get("SHELL", "/bin/sh")
        self.term.spawn_async(Vte.PtyFlags.DEFAULT, os.path.expanduser("~"), [shell], None,
                              GLib.SpawnFlags.DEFAULT, None, None, -1, None, None, None)

    def _keyboard(self):
        """the terminal tab takes the keyboard while it is on screen"""
        want = (self.is_open and Vte is not None and self.stack.get_visible_child_name() == "Terminal")
        seat = Gdk.Display.get_default().get_default_seat()
        if want and not self.grabbed and self.get_window():
            ok = seat.grab(self.get_window(), Gdk.SeatCapabilities.KEYBOARD, False, None, None, None, None)
            self.grabbed = ok == Gdk.GrabStatus.SUCCESS
            self.term.grab_focus()
        elif not want and self.grabbed:
            seat.ungrab()
            self.grabbed = False
        self.GRACE = 1200 if want else Popup.GRACE  # more forgiving while typing

    # updates ------------------------------------------------------------------

    def on_open(self):
        self.is_open = True
        self._media_view()
        GLib.idle_add(lambda: self._keyboard() or False)  # once the window is on screen
        self.cal.reset()
        self._tick()
        self.timers = [GLib.timeout_add(1000, self._tick)]
        self.refresh_weather()

    def refresh_weather(self):
        if time.time() - self.weather_at > 1800:
            self.weather_at = time.time()
            in_thread(fetch_weather, self._on_weather)

    def on_close(self):
        self.is_open = False
        self._media_view()
        self._keyboard()
        for t in self.timers:
            GLib.source_remove(t)
        self.timers = []

    def _tick(self):
        now = datetime.datetime.now()
        self.c_h.set_text(now.strftime("%I"))
        self.c_m.set_text(now.strftime("%M"))
        self.c_p.set_text(now.strftime("%p"))
        self.u_up.set_text(uptime_text())

        perf = self.stack.get_visible_child_name() == "Performance"
        rx, tx = net_bytes()
        if self.net_last:
            dt = time.monotonic() - self.net_last[2]
            down, up = (rx - self.net_last[0]) / dt, (tx - self.net_last[1]) / dt
            self.q_graph.push(down, up)
            self.q_down.set_text(human(down, rate=True))
            self.q_up.set_text(human(up, rate=True))
        self.net_last = (rx, tx, time.monotonic())
        self.q_total.set_text(f"↓{human(rx)} ↑{human(tx)}")  # since boot

        if now.second % 2 == 0 or not self.d_cpu.value.get_text():
            cpu = self.stats.cpu()
            mem, mu, mt = self.stats.mem()
            disk, du, dt = self.stats.disk()
            temp = self.stats.temp()
            self.d_cpu.set(cpu, f"{cpu * 100:.0f}%")
            self.d_mem.set(mem, f"{mem * 100:.0f}%")
            self.d_disk.set(disk, f"{disk * 100:.0f}%")
            self.q_cpu_ring.set(cpu, "")
            self.q_cpu_use.set_text(f"{cpu * 100:.0f}%")
            self.q_cpu_temp.set_text(f"{temp:.0f}°C" if temp else "--")
            self.q_cpu_meter.set((temp or 0) / 100)
            self.q_mem_gauge.set(mem)
            self.q_mem_text.set_text(f"{mu:.1f} / {mt:.1f} GiB")
            if perf:
                self._update_disk()
                in_thread(read_gpu, self._on_gpu)
        return True

    def _on_gpu(self, g):
        if not g:
            self.q_gpu_name.set_text("no gpu info")
            return
        name, temp, use = g
        self.q_gpu_name.set_text(name)
        self.q_gpu_ring.set(use, "")
        self.q_gpu_use.set_text(f"{use * 100:.0f}%")
        self.q_gpu_temp.set_text(f"{temp:.0f}°C" if temp is not None else "--")
        self.q_gpu_meter.set((temp or 0) / 100)

    # media page --------------------------------------------------------------

    def _media_view(self):
        """song position runs while the dashboard or media page is on screen;
        the music bars and lyrics only for the media page"""
        page = self.stack.get_visible_child_name() if self.is_open else None
        on = page in ("Dashboard", "Media")
        if on and not self.anim:
            self._poll_position()
            self._last_frame = time.monotonic()
            self.anim = GLib.timeout_add(33, self._frame)
        elif not on and self.anim:
            GLib.source_remove(self.anim)
            self.anim = None
        if page == "Media":
            self.cava.start()
            self._fetch_lyrics()
        else:
            self.cava.stop()

    def _now(self):
        st = self.media.state
        playing = st and st["status"] == "Playing"
        return self.pos + (time.monotonic() - self.pos_at if playing else 0)

    def _poll_position(self):
        if self.media.state:
            in_thread(self.media.position, self._on_position)

    def _on_position(self, pos):
        if pos is not None:
            self.pos, self.pos_at = pos, time.monotonic()

    def _frame(self):
        now = time.monotonic()
        dt, self._last_frame = now - self._last_frame, now
        if int(now) != int(now - dt):
            self._poll_position()  # once a second; in between the clock keeps time
        st = self.media.state
        pos = self._now()
        length = st["length"] if st else 0
        self.p_wave.playing = bool(st and st["status"] == "Playing")
        self.p_wave.frac = min(1.0, pos / length) if length else 0
        self.p_wave.step(dt)
        self.p_pos.set_text(fmt_time(pos) if st else "0:00")
        self.m_art.set_frac(self.p_wave.frac)
        self.m_art.playing = self.p_wave.playing
        self.m_art.step(dt)
        self._show_lyric(pos)
        return True

    def _seek(self, frac):
        st = self.media.state
        if st and st["length"]:
            self.pos, self.pos_at = frac * st["length"], time.monotonic()
            self.media.ctl(f"position {frac * st['length']:.1f}")

    def _fetch_lyrics(self, force=False):
        st = self.media.state
        key = st and (st["artist"], st["title"])
        if not st or (key == self.lyrics_key and not force):
            return
        self.lyrics_key, self.lyrics, self.lyric_i = key, [], -2
        self.l_none_text.set_text("Looking for lyrics…")
        self.l_stack.set_visible_child_name("none")
        artist, title, length = st["artist"], st["title"], st["length"]
        in_thread(lambda: fetch_lyrics(artist, title, length), lambda ls: self._on_lyrics(key, ls))

    def _retry_lyrics(self):
        self._fetch_lyrics(force=True)

    def _on_lyrics(self, key, lines):
        if key != self.lyrics_key:
            return  # the song changed while we were looking
        self.lyrics, self.lyric_i = lines, -2
        if not lines:
            self.l_none_text.set_text("No lyrics found")
            self.l_stack.set_visible_child_name("none")
        elif lines[0][0] is None:
            self.l_plain.set_text("\n".join(t for _, t in lines))
            self.l_stack.set_visible_child_name("plain")
        else:
            self.l_stack.set_visible_child_name("synced")

    def _show_lyric(self, pos):
        if not self.lyrics or self.lyrics[0][0] is None:
            return
        i = -1
        for n, (t, _) in enumerate(self.lyrics):
            if t <= pos + 0.2:
                i = n
            else:
                break
        if i == self.lyric_i:
            return
        self.lyric_i = i
        for slot, lb in enumerate(self.l_lines):  # one line before the current one, three after
            n = i - 1 + slot
            lb.set_text(self.lyrics[n][1] if 0 <= n < len(self.lyrics) else "")
            ctx = lb.get_style_context()
            for cls, on in (("now", slot == 1), ("near", slot in (0, 2))):
                (ctx.add_class if on else ctx.remove_class)(cls)

    def _on_weather(self, w):
        if not w:
            self.w_desc.set_text("no weather")
            self.weather_at = 0  # try again next time
            return
        self.w_icon.set_text(weather_icon(w["desc"]))
        self.w_temp.set_text(f"{w['temp']}°{w['unit']}")
        self.w_desc.set_text(w["desc"])
        self.w_more.set_text(f"feels {w['feels']}° · {w['high']}° / {w['low']}°")

    def _on_media(self, st):
        playing = st and st["status"] == "Playing"
        glyph = "\U000F03E4" if playing else "\U000F040A"
        self.m_play.set_text(glyph)
        self.p_play.set_text(glyph)
        if not st:
            for lb, text in [(self.m_title, "Nothing playing"), (self.p_title, "Nothing playing"),
                             (self.m_artist, ""), (self.p_artist, ""), (self.p_album, ""), (self.p_player, "no player")]:
                lb.set_text(text)
            self.m_art.set_path(None)
            self.m_art.set_frac(0)
            self.p_art.set_path(None)
            self.p_len.set_text("0:00")
            return
        self.m_title.set_text(st["title"] or "Unknown")
        self.p_title.set_text(st["title"] or "Unknown")
        self.m_artist.set_text(st["artist"])
        self.p_artist.set_text(st["artist"])
        self.p_album.set_text(st["album"] or "Unknown album")
        self.p_player.set_text(st["player"].replace("_", " ").title())
        self.p_len.set_text(fmt_time(st["length"]))
        self.m_art.set_path(st["art"])
        self.p_art.set_path(st["art"])
        self._poll_position()
        if self.anim and self.stack.get_visible_child_name() == "Media":
            self._fetch_lyrics()

    def _loop(self):
        sel = self.media._sel()
        spawn(f'[ "$(playerctl {sel} loop)" = None ] && playerctl {sel} loop Playlist || playerctl {sel} loop None')


class Volume(Popup):
    """the slider that peeks out of the right edge"""

    W, H = 52, 240

    def __init__(self, screen, keep_open):
        sx, sy, sw, sh = screen
        w, h = EDGE + self.W, self.H + 2 * FLARE
        super().__init__("MellowRight", (sw - w, (sh - h) // 2, w, h), keep_open)
        self.updating = False
        self.icon = label("", "icon")
        self.level = label("", "small", "dim")
        self.adj = Gtk.Adjustment(value=0, lower=0, upper=100, step_increment=5, page_increment=10)
        scale = Gtk.Scale(orientation=Gtk.Orientation.VERTICAL, adjustment=self.adj)
        scale.set_inverted(True)
        scale.set_draw_value(False)
        scale.set_can_focus(False)
        scale.set_halign(Gtk.Align.CENTER)
        self.adj.connect("value-changed", self._changed)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        col.pack_start(button(self.icon, lambda: (spawn("pamixer -t"), GLib.timeout_add(150, self.refresh)), "ctl"),
                       False, False, 0)
        col.pack_start(scale, True, True, 0)
        col.pack_start(self.level, False, False, 0)
        col.set_margin_top(FLARE + 14)
        col.set_margin_bottom(FLARE + 14)
        col.set_margin_start(8)
        col.set_margin_end(EDGE + 8)
        self.add(col)

    def paint(self, cr):
        w, h = self.rect[2], self.rect[3]
        hanging_panel(cr, "right", w - EDGE, FLARE, self.H, self.W)

    def on_open(self):
        self.refresh()

    def refresh(self):
        in_thread(read_volume, self._show)
        return False

    def _show(self, vol):
        level, muted = vol
        self.updating = True
        self.adj.set_value(level)
        self.updating = False
        self.icon.set_text(volume_icon(level, muted))
        self.level.set_text("mute" if muted else f"{level}")

    def _changed(self, adj):
        if self.updating:
            return
        v = int(adj.get_value())
        spawn(f"pamixer --set-volume {v}")
        self.level.set_text(str(v))
        self.icon.set_text(volume_icon(v, False))


def read_volume():
    out = run("pamixer --get-volume-human")
    if out == "muted":
        return int(run("pamixer --get-volume") or 0), True
    return int(out.rstrip("%") or 0) if out.rstrip("%").isdigit() else 0, False


def volume_icon(level, muted):
    if muted or level == 0:
        return "\U000F0581"
    return "\U000F057F" if level < 34 else "\U000F0580" if level < 67 else "\U000F057E"


class Sidebar(Popup):
    """notifications on the right, session buttons hanging off its left edge"""

    W = 380
    SESSION_W, SESSION_H = 66, 320

    def __init__(self, screen, keep_open):
        sx, sy, sw, sh = screen
        self.sh = sh
        w = EDGE + self.W + self.SESSION_W
        super().__init__("MellowRight", (sw - w, 0, w, sh), keep_open)
        self.u0 = (sh - self.SESSION_H) // 2
        self.connect("realize", lambda *_: self._input_shape())

        outer = Gtk.Box()
        self.add(outer)

        # session column
        self.armed = None
        session = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        session.set_size_request(self.SESSION_W, self.SESSION_H)
        session.set_valign(Gtk.Align.CENTER)
        session.set_margin_top(FLARE)
        session.set_margin_bottom(FLARE)
        actions = [("\U000F0343", "log out", "pkill -f xmonad-x86_64-linux", True),
                   ("\U000F0425", "shut down", "systemctl poweroff", True),
                   ("\U000F0709", "reboot", "systemctl reboot", True),
                   ("\U000F0594", "sleep", "systemctl suspend", False)]
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        inner.set_valign(Gtk.Align.CENTER)
        inner.set_vexpand(True)
        for glyph, name, cmd, confirm in actions:
            b = Gtk.Button(label=glyph)
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.set_can_focus(False)
            b.get_style_context().add_class("session")
            b.set_tooltip_text(name + (" (click twice)" if confirm else ""))
            b.set_halign(Gtk.Align.CENTER)
            b.connect("clicked", self._session, cmd, confirm)
            inner.pack_start(b, False, False, 0)
        session.pack_start(inner, True, True, 0)
        outer.pack_start(session, False, False, 0)

        # notifications
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        col.set_size_request(self.W - 16 - (EDGE + 16), -1)
        col.set_margin_top(EDGE + 16)
        col.set_margin_bottom(EDGE + 16)
        col.set_margin_start(16)
        col.set_margin_end(EDGE + 16)
        head = Gtk.Box()
        self.count = label("", "bold")
        head.pack_start(label("\U000F009A", "icon", "accent"), False, False, 0)
        head.pack_start(self.count, False, False, 10)
        head.pack_end(button("\U000F05E9", self._clear, "ctl", tooltip="clear all"), False, False, 0)
        col.pack_start(head, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll.add(self.list)
        col.pack_start(scroll, True, True, 0)
        outer.pack_start(col, True, True, 0)
        self.timer = None

    def _areas(self):
        """the painted parts, in window coordinates: the panel and the session column"""
        w, h = self.rect[2], self.rect[3]
        return [(self.SESSION_W - FLARE, 0, w - self.SESSION_W + FLARE, h),
                (0, self.u0 - FLARE, self.SESSION_W, self.SESSION_H + 2 * FLARE)]

    def _input_shape(self):
        # clicks on the see-through part go to the windows underneath
        self.input_shape_combine_region(cairo.Region([cairo.RectangleInt(*a) for a in self._areas()]))

    def contains(self, x, y):
        return any(in_rect(x - self.rect[0], y - self.rect[1], a) for a in self._areas())

    def paint(self, cr):
        w, h, x = self.rect[2], self.rect[3], self.SESSION_W
        # inside the frame only, so nothing is painted twice where it overlaps the
        # frame. the frame's own rounded corners sit at the two right-hand corners:
        # there, paint just the part inside their curve
        cx = w - EDGE - FLARE
        cr.save()
        cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        cr.rectangle(x, EDGE, w - EDGE - x, h - 2 * EDGE)
        cr.rectangle(cx, EDGE, FLARE, FLARE)
        cr.rectangle(cx, h - EDGE - FLARE, FLARE, FLARE)
        cr.fill()
        cr.restore()
        for sy, cy in ((EDGE, EDGE + FLARE), (h - EDGE - FLARE, h - EDGE - FLARE)):
            cr.save()
            cr.rectangle(cx, sy, FLARE, FLARE)
            cr.clip()
            cr.arc(cx, cy, FLARE, 0, 2 * math.pi)
            cr.fill()
            cr.restore()
        flare(cr, x - FLARE, EDGE, x - FLARE, EDGE + FLARE)
        flare(cr, x - FLARE, h - EDGE - FLARE, x - FLARE, h - EDGE - FLARE)
        hanging_panel(cr, "right", x, self.u0, self.SESSION_H, self.SESSION_W)

    def on_open(self):
        self.refresh()
        self.timer = GLib.timeout_add(3000, lambda: self.refresh() or True)

    def on_close(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = None
        self._disarm()

    def refresh(self):
        in_thread(read_notifications, self._render)

    def _render(self, items):
        for ch in self.list.get_children():
            self.list.remove(ch)
        self.count.set_text(f"{len(items)} notification{'s' * (len(items) != 1)}" if items else "No notifications")
        for n in items:
            title = box(False, 6, label(n["app"], "bold", xalign=0, ellipsize=True, width=24))
            title.pack_end(button("\U000F0156", lambda i=n["id"]: self._remove(i), "ctl"), False, False, 0)
            title.pack_end(label(n["age"], "dim", "small"), False, False, 0)
            text = box(True, 2, title)
            if n["summary"]:
                text.pack_start(label(n["summary"], xalign=0, ellipsize=True, width=34), False, False, 0)
            if n["body"]:
                body = label(n["body"], "dim", "small", xalign=0)
                body.set_line_wrap(True)
                body.set_lines(2)
                body.set_ellipsize(Pango.EllipsizeMode.END)
                body.set_max_width_chars(40)
                text.pack_start(body, False, False, 0)
            icon = label("\U000F009A", "notif-icon")
            icon.set_valign(Gtk.Align.START)
            row = box(False, 12, icon, cls="notif")
            row.pack_start(text, True, True, 0)
            self.list.pack_start(row, False, False, 0)
        self.list.show_all()

    def _remove(self, nid):
        spawn(f"dunstctl history-rm {nid}")
        GLib.timeout_add(150, lambda: self.refresh() or False)

    def _clear(self):
        spawn("dunstctl history-clear")
        GLib.timeout_add(150, lambda: self.refresh() or False)

    def _session(self, btn, cmd, confirm):
        if confirm and self.armed is not btn:
            self._disarm()
            self.armed = btn
            btn.get_style_context().add_class("armed")
            GLib.timeout_add(3000, self._disarm)
            return
        self._disarm()
        self.close()
        spawn(cmd)

    def _disarm(self):
        if self.armed:
            self.armed.get_style_context().remove_class("armed")
            self.armed = None
        return False


def read_notifications():
    out = run("dunstctl history")
    try:
        groups = json.loads(out)["data"]
    except (ValueError, KeyError, TypeError):
        return []
    now = time.monotonic() * 1e6  # dunst timestamps are monotonic microseconds
    items = []
    for n in (groups[0] if groups else []):
        age = max(0, (now - n["timestamp"]["data"]) / 1e6)
        items.append({
            "id": n["id"]["data"], "app": n["appname"]["data"] or "notification",
            "summary": n["summary"]["data"], "body": n["body"]["data"],
            "age": "now" if age < 60 else f"{age // 60:.0f}m" if age < 3600
                   else f"{age // 3600:.0f}h" if age < 86400 else f"{age // 86400:.0f}d",
        })
    return items


class LeftBar(Strip):
    def __init__(self, screen, toggle_dashboard, toggle_sidebar):
        sx, sy, sw, sh = screen
        super().__init__((0, 0, BAR, sh), {"left": BAR})
        self.names, self.current, self.occupied = [], 0, set()

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        col.set_margin_top(10)
        col.set_margin_bottom(10)
        col.set_halign(Gtk.Align.CENTER)
        self.add(col)

        logo = button(label(""), lambda: spawn("rofi -theme ~/.config/xmonad/rofi/gruvbox.rasi -show drun"),
                      "logo", tooltip="apps")
        col.pack_start(logo, False, False, 0)

        self.ws_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.ws_box.set_halign(Gtk.Align.CENTER)
        self.ws_box.set_margin_top(12)
        self.ws = {}
        for name in WORKSPACES:
            b = Gtk.Button()
            b.set_can_focus(False)
            b.set_relief(Gtk.ReliefStyle.NONE)
            b.get_style_context().add_class("ws")
            b.set_halign(Gtk.Align.CENTER)
            b.set_tooltip_text(f"workspace {name}")
            b.connect("clicked", lambda _b, n=name: self.switch(n))
            self.ws[name] = b
            self.ws_box.pack_start(b, False, False, 0)
        col.pack_start(self.ws_box, False, False, 0)

        # which layout the current workspace uses; click to cycle
        self.layout = label("", "icon", "dim")
        layout = button(self.layout, lambda: spawn("xdotool key super+space"), "barbtn", tooltip="layout")
        layout.set_halign(Gtk.Align.CENTER)
        layout.set_margin_top(8)
        self.layout_btn = layout
        col.pack_start(layout, False, False, 0)

        # bottom: clock, status, power
        self.h, self.m, self.p = label("", "clock"), label("", "clock"), label("", "small", "dim")
        clock = button(box(True, 0, self.h, self.m, self.p), toggle_dashboard, "barbtn", tooltip="dashboard")
        self.net = label("", "icon")
        self.vol = label("", "icon")
        vol = button(self.vol, lambda: spawn("pavucontrol"), "barbtn", tooltip="volume")
        vol.add_events(Gdk.EventMask.SCROLL_MASK)
        vol.connect("scroll-event", self._scroll)
        self.bell = label("\U000F009C", "icon")
        bell = button(self.bell, toggle_sidebar, "barbtn", tooltip="notifications")
        power = button("\U000F0425", toggle_sidebar, "barbtn", tooltip="session")

        # input method (fcitx5): EN, or あ while typing japanese. click to switch
        self.ime = label("EN", "ime")
        ime = button(self.ime, lambda: spawn("fcitx5-remote -t"), "barbtn", tooltip="input method (ctrl+space)")

        for w in reversed([clock, ime, box(True, 0, self.net), vol, bell, power]):
            w.set_halign(Gtk.Align.CENTER)
            col.pack_end(w, False, False, 0)
        clock.set_margin_bottom(10)

        Workspaces(self._on_workspaces).start()
        follow("pactl subscribe", self._on_pulse)
        self._vol_pending = False
        self._clock()
        every(10, self._net)
        every(4, self._notifications)
        # fcitx5-remote: 2 = japanese, 1 = english, 0 = no text field; nothing = not running
        follow("while :; do fcitx5-remote 2>/dev/null || echo; sleep 0.3; done", self._on_ime)
        self._ime_state = None
        self._volume()

    def switch(self, name):
        if name in self.names:
            spawn(f"xdotool set_desktop {self.names.index(name)}")

    LAYOUT_ICONS = {"grid": "\U000F0570", "tall": "\U000F0574", "wide": "\U000F0BCB", "full": "\U000F0293"}

    def _on_workspaces(self, names, current, occupied, layout):
        self.names = names
        self.layout.set_text(self.LAYOUT_ICONS.get(layout, "\U000F0570"))
        self.layout_btn.set_tooltip_text(f"layout: {layout or '?'} (click to change)")
        cur = names[current] if current < len(names) else None
        busy = {names[i] for i in occupied if i < len(names)}
        for name, b in self.ws.items():
            ctx = b.get_style_context()
            for cls, on in (("active", name == cur), ("occupied", name in busy)):
                (ctx.add_class if on else ctx.remove_class)(cls)

    def _clock(self):
        now = datetime.datetime.now()
        self.h.set_text(now.strftime("%I"))
        self.m.set_text(now.strftime("%M"))
        self.p.set_text(now.strftime("%p").lower())
        GLib.timeout_add((60 - now.second) * 1000 + 50, self._clock)  # next minute
        return False

    def _net(self):
        icon = "\U000F0318"  # disconnected
        for dev in sorted(os.listdir("/sys/class/net")):
            if dev == "lo":
                continue
            try:
                with open(f"/sys/class/net/{dev}/operstate") as f:
                    up = f.read().strip() == "up"
            except OSError:
                continue
            if up:
                icon = "\U000F05A9" if os.path.isdir(f"/sys/class/net/{dev}/wireless") else "\U000F0200"
                break
        self.net.set_text(icon)

    def _on_ime(self, state):
        if state == self._ime_state:
            return
        self._ime_state = state
        ja = state == "2"
        self.ime.set_text("あ" if ja else "EN" if state in ("0", "1") else "--")
        ctx = self.ime.get_style_context()
        (ctx.add_class if ja else ctx.remove_class)("ja")

    def _notifications(self):
        in_thread(lambda: run("dunstctl count history"), self._bell)

    def _bell(self, out):
        self.bell.set_text("\U000F009A" if out.isdigit() and int(out) > 0 else "\U000F009C")
        ctx = self.bell.get_style_context()
        (ctx.add_class if out.isdigit() and int(out) > 0 else ctx.remove_class)("accent")

    def _on_pulse(self, line):
        if ("sink" in line or "server" in line) and not self._vol_pending:
            self._vol_pending = True
            GLib.timeout_add(100, self._volume)

    def _volume(self):
        self._vol_pending = False
        in_thread(read_volume, lambda v: self.vol.set_text(volume_icon(*v)))
        return False

    def _scroll(self, _w, ev):
        up = ev.direction == Gdk.ScrollDirection.UP or (
            ev.direction == Gdk.ScrollDirection.SMOOTH and ev.get_scroll_deltas()[2] < 0)
        spawn(f"pamixer {'-i' if up else '-d'} 5")


# ----------------------------------------------------------------------------

class Shell:
    def __init__(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)
        mon = Gdk.Display.get_default().get_monitor(0).get_geometry()
        sw, sh = mon.width, mon.height
        screen = (0, 0, sw, sh)

        self.top = Strip((BAR, 0, sw - BAR, EDGE), {"top": EDGE})
        self.right = Strip((sw - EDGE, EDGE, EDGE, sh - 2 * EDGE), {"right": EDGE})
        self.bottom = Strip((BAR, sh - EDGE, sw - BAR, EDGE), {"bottom": EDGE})
        # inside corners of the frame; the circle centre is in the tile's own coordinates
        corners = [Corner(BAR, EDGE, FLARE, FLARE),
                   Corner(sw - EDGE - FLARE, EDGE, 0, FLARE),
                   Corner(BAR, sh - EDGE - FLARE, FLARE, 0),
                   Corner(sw - EDGE - FLARE, sh - EDGE - FLARE, 0, 0)]

        media, stats = Media(), Stats()
        top_zone = (BAR + (sw - BAR) // 4, 0, (sw - BAR) // 2, EDGE + 1)
        self.dashboard = Dashboard(screen, media, stats, lambda x, y: in_rect(x, y, self.top.rect))
        right_zone = self.right.rect
        self.sidebar = Sidebar(screen, lambda x, y: False)
        self.volume = Volume(screen, lambda x, y: in_rect(x, y, right_zone) and not self.sidebar.get_visible())
        self.bar = LeftBar(screen, self.dashboard.toggle, self.sidebar.toggle)

        # hover the middle of the top edge -> dashboard
        # hover the right edge -> volume; stay there -> sidebar
        self._watching = None
        for strip in (self.top, self.right):
            strip.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.top.connect("motion-notify-event", lambda *_: self._watch(top_zone, [(120, self.dashboard.open)]))
        self.right.connect("enter-notify-event", lambda *_: self._watch(
            self.right.rect, [(80, self.volume.open), (900, self._open_sidebar)]))

        for w in [self.bar, self.top, self.right, self.bottom]:
            w.show_lowered()
        for c in corners:
            c.show_all()
            c.get_window().lower()

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: safely(self.dashboard.toggle))
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, lambda: safely(self.sidebar.toggle))
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, Gtk.main_quit)

    def _watch(self, zone, steps):
        """while the pointer stays inside zone, fire each (after_ms, action) once.
        goes by pointer position, not by window, since the panels it opens
        cover the edge that started it."""
        if self._watching or self.sidebar.get_visible():
            return
        state = {"ms": 0, "steps": list(steps)}

        def tick():
            if not in_rect(*pointer(), zone):
                self._watching = None
                return False
            state["ms"] += 40
            while state["steps"] and state["ms"] >= state["steps"][0][0]:
                state["steps"].pop(0)[1]()
            if not state["steps"]:
                self._watching = None
                return False
            return True

        self._watching = GLib.timeout_add(40, tick)

    def _open_sidebar(self):
        self.volume.close()
        self.sidebar.open()


if __name__ == "__main__":
    Shell()
    Gtk.main()
