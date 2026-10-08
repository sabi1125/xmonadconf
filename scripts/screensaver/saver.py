#!/usr/bin/env python3
"""the screensaver: a big gruvbox clock and a quote from the new tab library.

opened by idle.py in a fullscreen alacritty; any key closes it. the block
moves somewhere else every minute so nothing burns in.

while spotify is playing it shows a music view in the center instead: a
visualizer, the album cover, the song, and prev / play-pause / next. those are clickable,
or h / space / l (arrows work too); any other key or click closes it.
idle.py leaves the closing to us while the music view is up (FLAG), so the
mouse can move to the buttons.
"""

import curses
import hashlib
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib

LIBRARY = Path.home() / ".config/xmonad/firefox/newtab/quotes.js"
CAVA_CONF = Path.home() / ".config/xmonad/config/cava-saver.conf"
FLAG = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "screensaver-media"
MOVE_SECS, QUOTE_SECS = 60, 30
BARS, LEVELS = 32, 12  # must match bars / ascii_max_range in cava-saver.conf
ART = 16  # cover in pixels; drawn ART cells wide, ART // 2 tall (two pixels per cell)
CACHE = Path.home() / ".cache/media-card"  # shared with the bar's media card

# 3x5 digits, each pixel drawn two cells wide
FONT = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": ["  #", "  #", "  #", "  #", "  #"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
}

KEYS = {
    ord("h"): "previous", curses.KEY_LEFT: "previous",
    ord(" "): "play-pause", ord("k"): "play-pause",
    ord("l"): "next", curses.KEY_RIGHT: "next",
}


def load_items():
    try:
        js = LIBRARY.read_text()
        lib = json.loads(js[js.index("{"):js.rindex("}") + 1])
        items = lib["own"] + lib["synced"]
        if items:
            return items
    except (OSError, ValueError, KeyError):
        pass
    return [{"kind": "quote", "text": "talk is cheap. show me the code.", "label": "—  linus torvalds"}]


def big(text):
    rows = [""] * 5
    for ch in text:
        for r, line in enumerate(FONT[ch]):
            rows[r] += line.replace("#", "██").replace(" ", "  ") + "  "
    return [r.rstrip() for r in rows]


def wrap(text, width):
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else lines


def spotify(*args):
    try:
        out = subprocess.run(["playerctl", "-p", "spotify", *args],
                             capture_output=True, text=True, timeout=1)
        return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def put(scr, y, x, text, attr=0):
    h, w = scr.getmaxyx()
    if 0 <= y < h - 1:
        try:
            scr.addstr(y, max(0, x), text[: max(0, w - 1 - max(0, x))], attr)
        except curses.error:
            pass


class Visualizer:
    """cava's bar heights (0..LEVELS), read in the background while running"""

    def __init__(self):
        self.proc = None
        self.levels = [0] * BARS

    def start(self):
        if self.proc:
            return
        try:
            self.proc = subprocess.Popen(["cava", "-p", str(CAVA_CONF)], stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True)
        except OSError:
            return
        threading.Thread(target=self.read, args=(self.proc,), daemon=True).start()

    def read(self, proc):
        for line in proc.stdout:
            levels = [int(v) for v in line.strip().split(";") if v.isdigit()]
            if levels:
                self.levels = levels

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc = None
        self.levels = [0] * BARS


class Cover:
    """the album art as rows of truecolor half blocks, loaded in the background"""

    def __init__(self):
        self.url = None
        self.rows = None

    def want(self, url):
        if url != self.url:
            self.url, self.rows = url, None
            if url:
                threading.Thread(target=self.load, args=(url,), daemon=True).start()

    def load(self, url):
        path = None
        if url.startswith("file://"):
            path = url[len("file://"):]
        elif url.startswith("http"):
            CACHE.mkdir(parents=True, exist_ok=True)
            path = CACHE / hashlib.sha1(url.encode()).hexdigest()
            if not path.exists():
                try:
                    urllib.request.urlretrieve(url, path)
                except OSError:
                    return
        if not path:
            return
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), ART, ART, False)
        except GLib.Error:
            return
        n, stride, px = pix.get_n_channels(), pix.get_rowstride(), pix.get_pixels()

        def rgb(x, y):
            i = y * stride + x * n
            return f"{px[i]};{px[i + 1]};{px[i + 2]}"

        # ▀ = top pixel as the foreground, bottom pixel as the background
        rows = ["".join(f"\x1b[38;2;{rgb(x, y)}m\x1b[48;2;{rgb(x, y + 1)}m▀" for x in range(ART)) + "\x1b[0m"
                for y in range(0, ART, 2)]
        if url == self.url:
            self.rows = rows


class Clock:
    """the normal screen: big clock, date and a quote, moving every minute"""

    def __init__(self):
        self.items = load_items()
        random.shuffle(self.items)
        self.pick, self.moved, self.changed = 0, 0.0, 0.0
        self.top = self.left = 0

    def draw(self, scr):
        now = time.monotonic()
        if now - self.changed >= QUOTE_SECS:
            self.pick, self.changed = (self.pick + 1) % len(self.items), now
            self.moved = 0.0  # the new text has a new size: place it again
        item = self.items[self.pick]

        h, w = scr.getmaxyx()
        clock = big(time.strftime("%H:%M"))
        date = time.strftime("%A, %d %B").lower()
        text = wrap(item["text"], min(70, w - 4))[:4]
        block = clock + ["", date, "", ""] + text + ["", item["label"]]
        bw = max(len(line) for line in block)

        if now - self.moved >= MOVE_SECS:
            self.top = random.randint(0, max(0, h - len(block) - 1))
            self.left = random.randint(0, max(0, w - bw - 1))
            self.moved = now

        for i, line in enumerate(block):
            if i < len(clock):
                attr = curses.color_pair(1)
            elif i < len(clock) + 4 or i == len(block) - 1:
                attr = curses.color_pair(3)
            else:
                attr = curses.color_pair(2)
            put(scr, self.top + i, self.left + (bw - len(line)) // 2, line, attr)


def draw_media(scr, levels, title, artist, playing, cover):
    """the music view, dead center. returns the buttons as (y, x0, x1, command)
    and where the cover goes (y, x), or None when there is none or no room"""
    h, w = scr.getmaxyx()
    height = LEVELS + 11
    art_h = ART // 2
    show_art = cover is not None and h > height + art_h
    if show_art:
        height += art_h
    top, mid = max(0, (h - height) // 2), w // 2

    # led bars: green at the bottom, yellow, orange on top; unlit leds stay dim
    left = mid - (BARS * 3 - 1) // 2
    for i in range(BARS):
        level = levels[i] if i < len(levels) else 0
        for row in range(1, LEVELS + 1):
            if row > level:
                pair = 7
            elif row > LEVELS * 3 // 4:
                pair = 6
            elif row > LEVELS * 5 // 12:
                pair = 5
            else:
                pair = 4
            put(scr, top + LEVELS - row, left + i * 3, "▄▄", curses.color_pair(pair))

    # the cover sits right under the bars
    y = top + LEVELS + 2
    art_at = None
    if show_art:
        art_at = (top + LEVELS + 1, mid - ART // 2)
        y += art_h
    title = title or "unknown"
    if len(title) > w - 6:
        title = title[: w - 7] + "…"
    put(scr, y, mid - len(title) // 2, title, curses.color_pair(2) | curses.A_BOLD)
    put(scr, y + 1, mid - len(artist) // 2, artist, curses.color_pair(3))

    y += 4
    buttons = []
    for dx, glyph, key, cmd, pair in ((-10, "󰒮", "h", "previous", 3),
                                      (0, "󰏤" if playing else "󰐊", "space", "play-pause", 8),
                                      (10, "󰒭", "l", "next", 3)):
        put(scr, y, mid + dx, glyph, curses.color_pair(pair) | curses.A_BOLD)
        put(scr, y + 1, mid + dx - len(key) // 2, key, curses.color_pair(7))
        buttons.append((y, mid + dx - 3, mid + dx + 3, cmd))

    clock = time.strftime("%H:%M  ·  %A, %d %B").lower()
    put(scr, y + 4, mid - len(clock) // 2, clock, curses.color_pair(3))
    return buttons, art_at


def main(scr):
    curses.curs_set(0)
    curses.use_default_colors()
    rich = curses.COLORS >= 256
    curses.init_pair(1, curses.COLOR_YELLOW, -1)   # clock     #e5e5ea
    curses.init_pair(2, curses.COLOR_WHITE, -1)    # quote     (fg)
    curses.init_pair(3, 8, -1)                     # date/label #8e8e93
    curses.init_pair(4, 14, -1)                    # led low   #70d7ff
    curses.init_pair(5, curses.COLOR_YELLOW, -1)   # led mid   #e5e5ea
    curses.init_pair(6, 166 if rich else 1, -1)    # led high  ~#ff9f0a
    curses.init_pair(7, 237 if rich else 0, -1)    # led off / hints
    curses.init_pair(8, 14, -1)                    # play button
    # clicks only (no motion), so the mouse can travel to the buttons
    curses.mousemask(curses.BUTTON1_PRESSED)
    curses.mouseinterval(0)

    clock, viz, cover = Clock(), Visualizer(), Cover()
    media, status, title, artist = False, "", "", ""
    checked, buttons, shown = 0.0, [], None
    try:
        while True:
            if time.monotonic() - checked >= 1:
                checked = time.monotonic()
                status = spotify("status")
                # stay in the music view when it was paused from here
                media = status == "Playing" or (media and status == "Paused")
                if media:
                    meta = spotify("metadata", "--format", "{{title}}\t{{artist}}\t{{mpris:artUrl}}")
                    title, artist, url = (meta.split("\t") + ["", ""])[:3]
                    cover.want(url)
                    FLAG.touch()
                    viz.start()
                    scr.timeout(33)
                else:
                    FLAG.unlink(missing_ok=True)
                    viz.stop()
                    scr.timeout(1000)

            scr.erase()
            art_at = None
            if media:
                buttons, art_at = draw_media(scr, viz.levels, title, artist, status == "Playing", cover.rows)
            else:
                clock.draw(scr)
            # curses doesn't know about the cover (it thinks those cells are blank and
            # leaves them alone), so when it changes: repaint everything, then the cover
            art = (cover.rows, art_at) if art_at else None
            if art != shown:
                scr.redrawwin()
            scr.refresh()
            if art and art != shown:
                y, x = art_at
                sys.stdout.write("".join(f"\x1b[{y + i + 1};{x + 1}H{row}" for i, row in enumerate(cover.rows)))
                sys.stdout.flush()
            shown = art

            ch = scr.getch()
            if ch == -1:
                continue
            if not media:
                return  # any key closes it
            cmd = KEYS.get(ch)
            if ch == curses.KEY_MOUSE:
                try:
                    _, x, y, _, state = curses.getmouse()
                except curses.error:
                    continue
                if not state & curses.BUTTON1_PRESSED:
                    continue
                cmd = next((c for by, x0, x1, c in buttons if by == y and x0 <= x <= x1), None)
            if cmd is None:
                return
            spotify(cmd)
            checked = 0.0  # show the new state right away
    finally:
        FLAG.unlink(missing_ok=True)
        viz.stop()


try:
    curses.wrapper(main)
except KeyboardInterrupt:
    pass
