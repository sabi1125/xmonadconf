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
import signal
import socket
import subprocess
import threading
import time
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
from Xlib import display as xdisplay  # noqa: E402

# ----------------------------------------------------------------------------
# look

BAR = 40        # left bar width
EDGE = 8        # frame thickness on the other three sides
FLARE = 16      # radius of the concave curves where pieces meet the frame
ROUND = 18      # radius of the outer corners of panels

FONT = "JetBrainsMono Nerd Font Propo"  # Propo: icons keep their real shape

# gruvbox dark, to match the rest of the rice
FRAME = "#1d2021"
CARD = "#282828"
CARD_HI = "#3c3836"
FG = "#ebdbb2"
DIM = "#a89984"
FAINT = "#665c54"
ACCENT = "#d79921"
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
.huge {{ font-size: 40px; font-weight: bold; }}
.dim, .dim * {{ color: {DIM}; }}
.faint {{ color: {FAINT}; }}
.bold {{ font-weight: bold; }}
.accent {{ color: {ACCENT}; }}
.small {{ font-size: 10px; }}

/* left bar */
.logo {{ font-size: 18px; color: {ACCENT}; min-height: 32px; min-width: 32px; }}
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

/* panels */
.card {{ background: {CARD}; border-radius: 14px; padding: 12px; }}
.tab {{ padding: 6px 14px; border-radius: 10px; }}
.tab label {{ color: {DIM}; }}
.tab.active label {{ color: {FG}; }}
.tab.active {{ box-shadow: inset 0 -2px {ACCENT}; border-radius: 10px 10px 2px 2px; }}

.cal-head {{ font-weight: bold; }}
.cal-dow {{ color: {DIM}; font-size: 11px; }}
.cal-day {{ min-width: 30px; min-height: 22px; font-size: 11px; }}
.cal-other {{ color: {FAINT}; }}
.cal-today {{ background: {ACCENT}; color: {FRAME}; border-radius: 99px; font-weight: bold; }}

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

.notif {{ background: {CARD}; border-radius: 14px; padding: 10px 12px; margin-bottom: 8px; }}
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
        if not clickable:
            self.connect("realize", lambda *_: self.input_shape_combine_region(cairo.Region()))

    def _draw(self, _w, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(*rgba(FRAME))
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
        watched = set()
        root.change_attributes(event_mask=X.PropertyChangeMask)
        self.publish(d, root, watched)
        while True:
            ev = d.next_event()
            if ev.type == X.PropertyNotify and ev.atom in (self.cur, self.names, self.clients, self.wm_desktop):
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
        GLib.idle_add(self.on_change, names, cur, occupied)


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
            cr.set_source_rgba(*rgba(ACCENT))
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
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        today = datetime.date.today()
        self.year, self.month = today.year, today.month
        self.title = label("", "cal-head")
        head = Gtk.Box()
        head.pack_start(button("\U000F0141", lambda: self.shift(-1), "ctl"), False, False, 0)
        head.set_center_widget(self.title)
        head.pack_end(button("\U000F0142", lambda: self.shift(1), "ctl"), False, False, 0)
        self.pack_start(head, False, False, 0)
        self.grid = Gtk.Grid(column_homogeneous=True, row_spacing=2)
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


# ----------------------------------------------------------------------------
# the pieces

class Media:
    """now-playing state from playerctl, shared by the dashboard and media tab"""

    FMT = "\x1f".join(["{{status}}", "{{title}}", "{{artist}}", "{{album}}",
                       "{{mpris:artUrl}}", "{{mpris:length}}", "{{playerName}}"])

    def __init__(self):
        self.listeners = []
        self.state = None
        follow(f"playerctl -F metadata --format '{self.FMT}'", self._line)

    def _line(self, line):
        f = line.split("\x1f")
        if len(f) < 7 or not (f[1] or f[2]):
            self.state = None
            self._emit()
            return
        status, title, artist, album, art, length, player = f[:7]
        self.state = {"status": status, "title": title, "artist": artist, "album": album,
                      "length": int(length) / 1e6 if length.isdigit() else 0, "player": player, "art": None}
        self._emit()
        in_thread(lambda: fetch_art(art), self._art)

    def _art(self, path):
        if self.state is not None:
            self.state["art"] = path
            self._emit()

    def _emit(self):
        for fn in self.listeners:
            fn(self.state)


def fmt_time(s):
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


class Dashboard(Popup):
    W, H = 800, 330  # the panel below the top edge; grows to fit the content

    def __init__(self, screen, media, stats, keep_open):
        sx, sy, sw, sh = screen
        self.cx = (BAR + sw - EDGE) // 2
        super().__init__("MellowTop", self._rect(), keep_open)
        self.media, self.stats = media, stats
        self.weather = None
        self.weather_at = 0
        self.timers = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_top(EDGE + 6)
        root.set_margin_bottom(16)
        root.set_margin_start(FLARE + 16)
        root.set_margin_end(FLARE + 16)
        self.add(root)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(180)
        tabs = Gtk.Box(spacing=4, homogeneous=True)
        self.tabs = {}
        for name, glyph, page in [("Dashboard", "\U000F056E", self._dashboard()),
                                  ("Media", "\U000F075A", self._media()),
                                  ("Performance", "\U000F04C5", self._performance())]:
            self.stack.add_named(page, name)
            t = button(box(True, 2, label(glyph, "icon"), label(name)), lambda n=name: self.show_tab(n), "tab")
            self.tabs[name] = t
            tabs.pack_start(t, True, True, 0)
        root.pack_start(tabs, False, False, 0)
        root.pack_start(self.stack, True, True, 0)
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
        cr.rectangle(0, 0, self.rect[2], EDGE)  # the top edge itself, so there is no seam
        cr.fill()
        hanging_panel(cr, "top", EDGE, FLARE, self.W, self.H)

    def show_tab(self, name):
        self.stack.set_visible_child_name(name)
        for n, t in self.tabs.items():
            (t.get_style_context().add_class if n == name else t.get_style_context().remove_class)("active")

    # pages ------------------------------------------------------------------

    def _dashboard(self):
        g = Gtk.Grid(column_spacing=10, row_spacing=10)

        # weather
        self.w_icon, self.w_temp = label("\U000F0590", "huge"), label("--°", "big", "bold")
        self.w_desc, self.w_more = label("", xalign=0), label("", "dim", "small", xalign=0)
        w = box(False, 12, self.w_icon, box(True, 2, self.w_temp, self.w_desc, self.w_more), cls="card")
        w.set_size_request(220, -1)
        g.attach(w, 0, 0, 1, 1)

        # clock
        self.c_h, self.c_m, self.c_p = label("", "huge"), label("", "huge"), label("", "dim", "bold")
        c = box(True, 0, self.c_h, label("•••", "accent"), self.c_m, self.c_p, cls="card")
        c.set_valign(Gtk.Align.FILL)
        clock_row = box(False, 10, c)

        # user
        hostname = socket.gethostname()
        self.u_up = label("", "dim", "small", xalign=0)
        u = box(False, 18, label("", "huge", "accent"),
                box(True, 2, label(f"{getpass.getuser()}@{hostname}", "bold", xalign=0), self.u_up), cls="card")
        u.get_children()[1].set_valign(Gtk.Align.CENTER)
        g.attach(u, 1, 0, 1, 1)

        # calendar
        self.cal = Calendar()
        cal = box(True, 0, self.cal, cls="card")
        g.attach(clock_row, 0, 1, 1, 1)
        clock_row.set_halign(Gtk.Align.START)
        g.attach(cal, 1, 1, 1, 1)

        # rings
        self.d_cpu, self.d_mem, self.d_disk = Ring("\U000F0EE0", 58), Ring("\U000F035B", 58), Ring("\U000F02CA", 58)
        rings = box(True, 8, self.d_cpu, self.d_mem, self.d_disk, cls="card")
        rings.set_valign(Gtk.Align.FILL)
        g.attach(rings, 2, 0, 1, 2)

        # now playing
        self.m_art = Art(96)
        self.m_title = label("Nothing playing", "bold", ellipsize=True, width=18)
        self.m_artist = label("", "dim", "small", ellipsize=True, width=20)
        self.m_play = label("\U000F040A", "icon")
        controls = box(False, 6,
                       button("\U000F04AE", lambda: spawn("playerctl previous"), "ctl"),
                       button(self.m_play, lambda: spawn("playerctl play-pause"), "play"),
                       button("\U000F04AD", lambda: spawn("playerctl next"), "ctl"))
        controls.set_halign(Gtk.Align.CENTER)
        art = box(False, 0, self.m_art)
        art.set_halign(Gtk.Align.CENTER)
        m = box(True, 8, art, self.m_title, self.m_artist, controls, cls="card")
        m.set_size_request(190, -1)
        g.attach(m, 3, 0, 1, 2)

        # the clock card takes what the weather card leaves
        c.set_size_request(220, -1)
        for child in (self.c_h, self.c_m):
            child.set_halign(Gtk.Align.CENTER)
        return g

    def _media(self):
        self.p_art = Art(170)
        self.p_title = label("Nothing playing", "big", "bold", xalign=0, ellipsize=True, width=28)
        self.p_artist = label("", xalign=0, ellipsize=True, width=34)
        self.p_album = label("", "dim", xalign=0, ellipsize=True, width=34)
        self.p_pos, self.p_len = label("0:00", "small", "dim"), label("0:00", "small", "dim")
        self.p_bar = Gtk.ProgressBar()
        self.p_bar.set_valign(Gtk.Align.CENTER)
        bar = Gtk.Box(spacing=8)
        bar.pack_start(self.p_pos, False, False, 0)
        bar.pack_start(self.p_bar, True, True, 0)
        bar.pack_start(self.p_len, False, False, 0)
        self.p_play = label("\U000F040A", "icon")
        controls = box(False, 8,
                       button("\U000F049D", lambda: spawn("playerctl shuffle toggle"), "ctl", tooltip="shuffle"),
                       button("\U000F04AE", lambda: spawn("playerctl previous"), "ctl"),
                       button(self.p_play, lambda: spawn("playerctl play-pause"), "play"),
                       button("\U000F04AD", lambda: spawn("playerctl next"), "ctl"),
                       button("\U000F0456", self._loop, "ctl", tooltip="repeat"))
        controls.set_halign(Gtk.Align.CENTER)
        self.p_player = label("", "dim", "small", xalign=0)
        info = box(True, 6, self.p_title, self.p_artist, self.p_album)
        info.pack_end(self.p_player, False, False, 0)
        info.pack_end(controls, False, False, 4)
        info.pack_end(bar, False, False, 4)
        info.set_hexpand(True)
        page = box(False, 24, self.p_art, cls="card")
        page.pack_start(info, True, True, 0)
        self.p_art.set_valign(Gtk.Align.CENTER)
        return page

    def _performance(self):
        self.q_cpu, self.q_temp = Ring("\U000F0EE0", 120, 9), Ring("\U000F050F", 120, 9)
        self.q_mem, self.q_disk = Ring("\U000F035B", 120, 9), Ring("\U000F02CA", 120, 9)
        self.q_sub = {}
        row = Gtk.Box(spacing=16, homogeneous=True)
        for key, ring, name in [("cpu", self.q_cpu, "CPU"), ("temp", self.q_temp, "Temperature"),
                                ("mem", self.q_mem, "Memory"), ("disk", self.q_disk, "Disk")]:
            sub = label("", "dim", "small")
            self.q_sub[key] = sub
            col = box(True, 6, ring, label(name, "bold"), sub)
            col.set_valign(Gtk.Align.CENTER)
            row.pack_start(col, True, True, 0)
        page = box(False, 0, cls="card")
        page.pack_start(row, True, True, 0)
        return page

    # updates ------------------------------------------------------------------

    def on_open(self):
        self.cal.reset()
        self._tick()
        self.timers = [GLib.timeout_add(1000, self._tick)]
        self.refresh_weather()

    def refresh_weather(self):
        if time.time() - self.weather_at > 1800:
            self.weather_at = time.time()
            in_thread(fetch_weather, self._on_weather)

    def on_close(self):
        for t in self.timers:
            GLib.source_remove(t)
        self.timers = []

    def _tick(self):
        now = datetime.datetime.now()
        self.c_h.set_text(now.strftime("%I"))
        self.c_m.set_text(now.strftime("%M"))
        self.c_p.set_text(now.strftime("%p"))
        self.u_up.set_text(uptime_text())

        if now.second % 2 == 0 or not self.d_cpu.value.get_text():
            cpu = self.stats.cpu()
            mem, mu, mt = self.stats.mem()
            disk, du, dt = self.stats.disk()
            temp = self.stats.temp()
            for ring, frac in [(self.d_cpu, cpu), (self.q_cpu, cpu)]:
                ring.set(frac, f"{cpu * 100:.0f}%")
            for ring in (self.d_mem, self.q_mem):
                ring.set(mem, f"{mem * 100:.0f}%")
            for ring in (self.d_disk, self.q_disk):
                ring.set(disk, f"{disk * 100:.0f}%")
            self.q_temp.set((temp or 0) / 100, f"{temp:.0f}°C" if temp else "--")
            self.q_sub["cpu"].set_text(f"{os.cpu_count()} threads")
            self.q_sub["mem"].set_text(f"{mu:.1f} / {mt:.1f} GiB")
            self.q_sub["disk"].set_text(f"{du:.0f} / {dt:.0f} GB")
            self.q_sub["temp"].set_text("cpu package")

        if self.media.state and self.stack.get_visible_child_name() == "Media":
            in_thread(lambda: run("playerctl position"), self._on_position)
        return True

    def _on_position(self, out):
        st = self.media.state
        try:
            pos = float(out)
        except ValueError:
            return
        self.p_pos.set_text(fmt_time(pos))
        if st and st["length"]:
            self.p_bar.set_fraction(min(1.0, pos / st["length"]))

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
                             (self.m_artist, ""), (self.p_artist, ""), (self.p_album, ""), (self.p_player, "")]:
                lb.set_text(text)
            self.m_art.set_path(None)
            self.p_art.set_path(None)
            self.p_bar.set_fraction(0)
            return
        self.m_title.set_text(st["title"] or "Unknown")
        self.p_title.set_text(st["title"] or "Unknown")
        self.m_artist.set_text(st["artist"])
        self.p_artist.set_text(st["artist"])
        self.p_album.set_text(st["album"] or "")
        self.p_player.set_text(f"via {st['player']}")
        self.p_len.set_text(fmt_time(st["length"]))
        self.m_art.set_path(st["art"])
        self.p_art.set_path(st["art"])

    def _loop(self):
        spawn('[ "$(playerctl loop)" = None ] && playerctl loop Playlist || playerctl loop None')


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
        cr.rectangle(w - EDGE, 0, EDGE, h)
        cr.fill()
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
        cr.rectangle(x, 0, w - x, h)
        cr.fill()
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

        for w in reversed([clock, box(True, 0, self.net), vol, bell, power]):
            w.set_halign(Gtk.Align.CENTER)
            col.pack_end(w, False, False, 0)
        clock.set_margin_bottom(10)

        Workspaces(self._on_workspaces).start()
        follow("pactl subscribe", self._on_pulse)
        self._vol_pending = False
        self._clock()
        every(10, self._net)
        every(4, self._notifications)
        self._volume()

    def switch(self, name):
        if name in self.names:
            spawn(f"xdotool set_desktop {self.names.index(name)}")

    def _on_workspaces(self, names, current, occupied):
        self.names = names
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

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, lambda: self.dashboard.toggle() or True)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR2, lambda: self.sidebar.toggle() or True)
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
