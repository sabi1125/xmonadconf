#!/usr/bin/env python3
# floating now-playing card under the center island: album art, title,
# artist, progress and prev / play-pause / next. toggled by media-popup.sh

import hashlib
import os
import subprocess
import threading
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

# center island is x 680..1240, y 0..30 on screen; the card hangs centered below it
WIDTH, HEIGHT = 360, 112
X, Y = 960 - WIDTH // 2, 38
ART = 88
CACHE = os.path.expanduser("~/.cache/media-card")

CSS = b"""
* { font-family: "JetBrainsMono Nerd Font"; }
#card { background-color: rgba(29, 32, 33, 0.88); }
#title  { color: #ebdbb2; font-weight: bold; font-size: 10pt; }
#artist { color: #a89984; font-size: 9pt; }
button {
    background: none; border: none; box-shadow: none;
    color: #7c6f64; font-size: 14pt; padding: 0 6px; min-height: 0;
}
button:hover { color: #ebdbb2; }
#play { color: #8ec07c; font-size: 16pt; }
#play:hover { color: #b8bb26; }
progressbar trough, progressbar progress { min-height: 3px; border-radius: 2px; border: none; }
progressbar trough { background-color: #3c3836; }
progressbar progress { background-color: #d79921; }
"""


def playerctl(*args):
    try:
        out = subprocess.run(["playerctl", *args], capture_output=True, text=True, timeout=1)
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def rounded(art, radius=6):
    """the cover (or a blank tile) with its corners cut round"""
    if art is None:
        art = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, ART, ART)
        art.fill(0x3C3836FF)
    art = art.add_alpha(False, 0, 0, 0)
    stride, px = art.get_rowstride(), bytearray(art.get_pixels())
    for y in range(ART):
        for x in range(ART):
            cx = radius if x < radius else ART - radius - 1 if x >= ART - radius else x
            cy = radius if y < radius else ART - radius - 1 if y >= ART - radius else y
            if (x - cx) ** 2 + (y - cy) ** 2 > radius * radius:
                px[y * stride + x * 4 + 3] = 0
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(px)), GdkPixbuf.Colorspace.RGB,
                                           True, 8, ART, ART, stride)


class Card(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_wmclass("mediacard", "MediaCard")
        self.set_default_size(WIDTH, HEIGHT)
        self.move(X, Y)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.art_url = None

        root = Gtk.Box(spacing=14, name="card")
        root.set_border_width(12)
        self.add(root)

        self.cover = Gtk.Image()
        self.cover.set_valign(Gtk.Align.CENTER)
        self.cover.set_from_pixbuf(rounded(None))
        root.pack_start(self.cover, False, False, 0)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info.set_valign(Gtk.Align.CENTER)
        root.pack_start(info, True, True, 0)

        self.title = Gtk.Label(name="title", xalign=0, ellipsize=3)
        self.artist = Gtk.Label(name="artist", xalign=0, ellipsize=3)
        info.pack_start(self.title, False, False, 0)
        info.pack_start(self.artist, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.set_margin_top(8)
        self.progress.set_margin_bottom(4)
        info.pack_start(self.progress, False, False, 0)

        controls = Gtk.Box(homogeneous=True)
        self.play = None
        for glyph, cmd, name in (("󰒮", "previous", None),
                                 ("󰐊", "play-pause", "play"),
                                 ("󰒭", "next", None)):
            btn = Gtk.Button(label=glyph)
            if name:
                btn.set_name(name)
                self.play = btn
            btn.connect("clicked", lambda _b, c=cmd: (playerctl(c), self.refresh()))
            controls.pack_start(btn, True, True, 0)
        info.pack_start(controls, False, False, 0)

        self.refresh()
        GLib.timeout_add(1000, self.refresh)

    def refresh(self):
        status = playerctl("status")
        if status not in ("Playing", "Paused"):
            Gtk.main_quit()
            return False

        fields = playerctl("metadata", "--format",
                           "{{title}}\t{{artist}}\t{{mpris:artUrl}}\t{{mpris:length}}\t{{position}}").split("\t")
        title, artist, url, length, position = (fields + [""] * 5)[:5]
        self.title.set_text(title or "unknown")
        self.artist.set_text(artist)
        self.play.set_label("󰏤" if status == "Playing" else "󰐊")
        try:
            self.progress.set_fraction(min(1.0, int(position) / int(length)))
        except (ValueError, ZeroDivisionError):
            self.progress.set_fraction(0)

        if url != self.art_url:
            self.art_url = url
            threading.Thread(target=self.load_art, args=(url,), daemon=True).start()
        return True

    def load_art(self, url):
        path = None
        if url.startswith("file://"):
            path = url[len("file://"):]
        elif url.startswith("http"):
            os.makedirs(CACHE, exist_ok=True)
            path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest())
            if not os.path.exists(path):
                try:
                    urllib.request.urlretrieve(url, path)
                except OSError:
                    path = None
        art = None
        if path:
            try:
                art = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, ART, ART, False)
            except GLib.Error:
                pass
        GLib.idle_add(self.set_art, url, rounded(art))

    def set_art(self, url, art):
        if url == self.art_url:
            self.cover.set_from_pixbuf(art)
        return False


provider = Gtk.CssProvider()
provider.load_from_data(CSS)
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider,
                                         Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
card = Card()
card.show_all()
Gtk.main()
