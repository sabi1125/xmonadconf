#!/usr/bin/env python3
# hover a workspace dot on the left island to peek at the windows open there.
# xmobar has no hover events, so this polls the pointer and pops a small card
# under the dot while it sits over one. dot positions are measured from the
# island in left.rc and the bar font; windows come from the EWMH properties.

import os
import re
import subprocess
import warnings

import gi

warnings.filterwarnings("ignore", category=DeprecationWarning)  # set_wmclass, still needed for the picom rule

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

RC = os.path.expanduser("~/.config/xmonad/xmobar/left.rc")
BAR_FONT = "JetBrainsMono Nerd Font Bold 10"
WORKSPACES = ["1", "2", "3", "4", "5"]  # myWorkspaces
VISIBLE = 30   # visible bar height (the top 8px are off-screen)
REACH = 12     # hover zone either side of a dot's centre
GAP = 8        # between the bar and the card
POLL = 80      # ms

ICONS = {
    "firefox": "\U000f0239", "alacritty": "\uf120", "chromium": "\uf268", "google-chrome": "\uf268",
    "spotify": "\U000f04c7", "discord": "\U000f066f", "code": "\U000f0a1e", "thunar": "\U000f024b",
    "nautilus": "\U000f024b", "pavucontrol": "\U000f057e", "mpv": "\uf144", "vlc": "\U000f057c",
    "obsidian": "\U000f082e", "steam": "\uf1b6", "telegram": "\uf2c6", "gimp": "\uf338",
    "libreoffice": "\U000f0219", "zathura": "\uf1c1", "keepassxc": "\U000f030b",
}
DEFAULT_ICON = "\uf2d0"

CSS = b"""
* { font-family: "JetBrainsMono Nerd Font"; font-size: 9pt; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6); }  /* legible on the glass */
#card   { background-color: rgba(29, 32, 33, 0.94); padding: 12px 18px 14px; }  /* fills the window edge to edge */
#head   { color: #d79921; font-weight: bold; margin-bottom: 4px; }
#empty  { color: #928374; }
.icon   { color: #a89984; font-size: 11pt; }
.title  { color: #d5c4a1; }
.active .icon  { color: #d79921; }
.active .title { color: #fbf1c7; font-weight: bold; }
"""


def island():
    """(x, width) of the left island from left.rc"""
    with open(RC) as f:
        m = re.search(r"xpos\s*=\s*(-?\d+).*?width\s*=\s*(\d+)", f.read(), re.S)
    return int(m.group(1)), int(m.group(2))


def dot_centres(widget):
    """x centre of each dot, laid out exactly as myPP / left.rc render them"""
    layout = widget.create_pango_layout("")
    layout.set_font_description(Pango.FontDescription(BAR_FONT))

    def width(text):
        layout.set_text(text, -1)
        return layout.get_pixel_size()[0]

    pad, dot, sep = "   ", "●", "  "  # template padding, ppCurrent glyph, ppWsSep
    line = pad + sep.join([dot] * len(WORKSPACES)) + "    " + "tall" + pad  # ppSep + layout name
    x, w = island()
    start = x + (w - width(line)) // 2
    return [start + width(pad + (dot + sep) * i) + width(dot) // 2 for i in range(len(WORKSPACES))]


def xprop(*args):
    try:
        return subprocess.run(["xprop", *args], capture_output=True, text=True, timeout=1).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def strings(line):
    return [re.sub(r"\\(.)", r"\1", s) for s in re.findall(r'"((?:[^"\\]|\\.)*)"', line)]


def prop(out, name):
    for line in out.splitlines():
        if line.startswith(name + "("):
            rest = line.split(")", 1)[1]  # "(TYPE) = value" or "(TYPE): window id # value"
            return rest.split("=" if "=" in rest else ":", 1)[1].strip() if rest.strip() else ""
    return ""


def windows(tag):
    """[(class, title, active)] of the windows on workspace `tag`"""
    root = xprop("-root", "_NET_DESKTOP_NAMES", "_NET_CLIENT_LIST", "_NET_ACTIVE_WINDOW")
    names = strings(prop(root, "_NET_DESKTOP_NAMES"))
    if tag not in names:
        return []
    desk = str(names.index(tag))
    ids = re.findall(r"0x[0-9a-f]+", prop(root, "_NET_CLIENT_LIST"))
    active = (re.findall(r"0x[0-9a-f]+", prop(root, "_NET_ACTIVE_WINDOW")) or [""])[0]

    found = []
    for wid in ids:
        out = xprop("-id", wid, "_NET_WM_DESKTOP", "WM_CLASS", "_NET_WM_NAME", "WM_NAME")
        if prop(out, "_NET_WM_DESKTOP") != desk:
            continue
        cls = (strings(prop(out, "WM_CLASS")) or ["?"])[-1]
        title = (strings(prop(out, "_NET_WM_NAME")) or strings(prop(out, "WM_NAME")) or [cls])[0]
        found.append((cls, title, int(wid, 16) == int(active or "0", 16)))
    return found


def fullscreen_active():
    """don't pop up over a fullscreen video when the pointer brushes the corner"""
    active = re.findall(r"0x[0-9a-f]+", prop(xprop("-root", "_NET_ACTIVE_WINDOW"), "_NET_ACTIVE_WINDOW"))
    if not active or int(active[0], 16) == 0:
        return False
    return "FULLSCREEN" in xprop("-id", active[0], "_NET_WM_STATE")


class Peek(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass("wspeek", "WsPeek")
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, name="card")
        self.add(self.box)

        self.centres = dot_centres(self)
        self.pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
        self.hovered = None
        self.ticks = 0
        GLib.timeout_add(POLL, self.poll)

    def dot_under_pointer(self):
        _, x, y = self.pointer.get_position()
        if y >= VISIBLE:
            return None
        for i, cx in enumerate(self.centres):
            if abs(x - cx) < REACH:
                return i
        return None

    def poll(self):
        dot = self.dot_under_pointer()
        if dot != self.hovered:
            self.hovered = dot
            if dot is None or fullscreen_active():
                self.hide()
            else:
                self.fill(dot)
        elif dot is not None and self.get_visible():
            self.ticks += 1
            if self.ticks * POLL >= 1000:  # keep it fresh while hovering
                self.fill(dot)
        return True

    def fill(self, dot):
        self.ticks = 0
        tag = WORKSPACES[dot]
        for child in self.box.get_children():
            self.box.remove(child)

        self.box.pack_start(Gtk.Label(label=f"workspace {tag}", name="head", xalign=0), False, False, 0)
        wins = windows(tag)
        if not wins:
            self.box.pack_start(Gtk.Label(label="empty", name="empty", xalign=0), False, False, 0)
        for cls, title, active in wins:
            row = Gtk.Box(spacing=12)
            if active:
                row.get_style_context().add_class("active")
            icon = Gtk.Label(label=ICONS.get(cls.lower(), DEFAULT_ICON))
            icon.get_style_context().add_class("icon")
            text = Gtk.Label(label=title, xalign=0, ellipsize=Pango.EllipsizeMode.END, max_width_chars=40)
            text.set_width_chars(min(len(title), 40))  # ellipsized labels otherwise shrink to nothing
            text.get_style_context().add_class("title")
            row.pack_start(icon, False, False, 0)
            row.pack_start(text, True, True, 0)
            self.box.pack_start(row, False, False, 0)

        self.box.show_all()
        # size the window exactly to its contents (no leftover space from a bigger list)
        width = self.box.get_preferred_width()[1]
        height = self.box.get_preferred_height_for_width(width)[1]
        self.resize(width, height)
        self.move(max(8, self.centres[dot] - width // 2), VISIBLE + GAP)
        self.show_all()


provider = Gtk.CssProvider()
provider.load_from_data(CSS)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                         Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
Peek()
Gtk.main()
