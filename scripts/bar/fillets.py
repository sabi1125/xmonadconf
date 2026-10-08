#!/usr/bin/env python3
# concave "flare" corners where each xmobar island meets the top screen edge,
# so the islands look like they grow out of it. picom can only round corners
# inward, so each flare is its own tiny window: bar colour with a quarter
# ellipse cut out. island positions are read from the xmobar .rc files.

import glob
import os
import re
import warnings

import gi

warnings.filterwarnings("ignore", category=DeprecationWarning)  # set_wmclass, still needed for the picom rule

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

SPREAD = 16       # how far each flare reaches out along the top edge
CORNER = 8        # picom corner-radius for the bars (picom.conf)
COLOR = (0x1D, 0x20, 0x21)  # xmobar bgColor
ALPHA = 200                 # xmobar alpha
RC_DIR = os.path.expanduser("~/.config/xmonad/xmobar")

CSS = b"window { background-color: transparent; }"


def islands():
    """(x, width, visible height) of every xmobar island hanging from the top edge"""
    found = []
    for rc in sorted(glob.glob(os.path.join(RC_DIR, "*.rc"))):
        with open(rc) as f:
            m = re.search(r"xpos\s*=\s*(-?\d+),\s*ypos\s*=\s*(-?\d+),\s*"
                          r"width\s*=\s*(\d+),\s*height\s*=\s*(\d+)", f.read())
        if m and int(m.group(2)) <= 0:
            x, y, w, h = map(int, m.groups())
            found.append((x, w, y + h))
    return found


def flare(left, depth, ss=4):
    """SPREAD x depth tile: bar colour outside a quarter ellipse. the curve
    leaves the top edge horizontally and reaches the island vertically right
    where picom's bottom corner begins, so the two read as one S-curve.
    ss x ss supersampling per pixel for a smooth edge."""
    a, b = SPREAD, depth
    cx = 0 if left else a  # ellipse centre sits on the side away from the island
    px = bytearray()
    for y in range(b):
        for x in range(a):
            inside = 0
            for sy in range(ss):
                for sx in range(ss):
                    dx = (x + (sx + 0.5) / ss - cx) / a
                    dy = (y + (sy + 0.5) / ss - b) / b
                    inside += dx * dx + dy * dy < 1
            cover = 1 - inside / (ss * ss)
            px += bytes((*COLOR, round(ALPHA * cover)))
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(px)), GdkPixbuf.Colorspace.RGB,
                                           True, 8, a, b, a * 4)


class Flare(Gtk.Window):
    def __init__(self, x, left, depth):
        super().__init__()
        self.set_wmclass("barfillet", "BarFillet")
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)  # xmonad leaves docks untiled
        self.set_decorated(False)
        self.set_accept_focus(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.stick()
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_default_size(SPREAD, depth)
        self.set_size_request(SPREAD, depth)
        self.set_resizable(False)
        self.add(Gtk.Image.new_from_pixbuf(flare(left, depth)))
        self.move(x, 0)
        self.show_all()


def main():
    style = Gtk.CssProvider()
    style.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style,
                                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    for x, width, visible in islands():
        depth = visible - CORNER
        Flare(x - SPREAD, left=True, depth=depth)
        Flare(x + width, left=False, depth=depth)
    Gtk.main()


if __name__ == "__main__":
    main()
