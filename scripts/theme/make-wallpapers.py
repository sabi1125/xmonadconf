#!/usr/bin/env python3
# draws the mellow-*.png wallpapers: minimal, abstract, in the rice's colours
# (gruvbox on near-black). run again with a different SEED for new variations.
#   python3 make-wallpapers.py [out_dir]

import math
import os
import random
import subprocess
import sys

import cairo

W, H = 1920, 1080
SEED = 7
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.config/xmonad/wallpapers")

BG0, BG1, BG2, BG3 = "#0c1012", "#111618", "#171c1f", "#1e2326"
FG, GREEN, BGREEN, AQUA, BAQUA = "#ebdbb2", "#98971a", "#b8bb26", "#689d6a", "#8ec07c"
BLUE, ORANGE, BORANGE, YELLOW = "#83a598", "#d65d0e", "#fe8019", "#fabd2f"


def rgb(c, a=1.0):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


def mix(a, b, t):
    a, b = rgb(a), rgb(b)
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3)) + (1.0,)


def canvas(top=BG1, bottom=BG0):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    cr = cairo.Context(surf)
    g = cairo.LinearGradient(0, 0, 0, H)
    g.add_color_stop_rgba(0, *rgb(top))
    g.add_color_stop_rgba(1, *rgb(bottom))
    cr.set_source(g)
    cr.paint()
    return surf, cr


def glow(cr, x, y, r, color, alpha):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, *rgb(color, alpha))
    g.add_color_stop_rgba(1, *rgb(color, 0))
    cr.set_source(g)
    cr.arc(x, y, r, 0, 2 * math.pi)
    cr.fill()


def save(surf, name, blur=None, grain=True):
    path = os.path.join(OUT, f"mellow-{name}.png")
    surf.write_to_png(path)
    ops = []
    if blur:
        ops += ["-blur", blur]
    if grain:  # a little film grain so gradients do not band
        ops += ["-attenuate", "0.25", "+noise", "Gaussian"]
    if ops:
        subprocess.run(["magick", path, *ops, path], check=True)
    print(path)


def hills():
    """layered night hills under a soft moon"""
    surf, cr = canvas(BG2, BG0)
    rnd = random.Random(SEED)
    for _ in range(140):  # stars
        cr.set_source_rgba(*rgb(FG, rnd.uniform(0.15, 0.6)))
        cr.arc(rnd.uniform(0, W), rnd.uniform(0, H * 0.55), rnd.uniform(0.6, 1.6), 0, 2 * math.pi)
        cr.fill()
    glow(cr, W * 0.72, H * 0.28, 260, FG, 0.10)
    cr.set_source_rgba(*rgb(FG, 0.9))
    cr.arc(W * 0.72, H * 0.28, 46, 0, 2 * math.pi)
    cr.fill()
    layers = 5
    for i in range(layers):
        t = i / (layers - 1)
        base = H * (0.55 + 0.1 * i)
        cr.move_to(0, H)
        ph, amp, freq = rnd.uniform(0, 6), 70 - 10 * i, rnd.uniform(1.2, 2.2)
        for x in range(0, W + 8, 8):
            y = base - amp * math.sin(x / W * math.pi * freq + ph) - 20 * math.sin(x / 140 + ph * 2)
            cr.line_to(x, y)
        cr.line_to(W, H)
        cr.close_path()
        cr.set_source_rgba(*mix("#232b26", BG0, t))
        cr.fill()
    save(surf, "hills")


def waves():
    """stacked lines that swell in the middle"""
    surf, cr = canvas(BG1, BG0)
    rnd = random.Random(SEED + 1)
    rows = 46
    cr.set_line_width(1.6)
    for r in range(rows):
        y0 = H * 0.16 + r * (H * 0.7 / rows)
        amp = rnd.uniform(30, 70) * (0.4 + 0.6 * math.sin(r / rows * math.pi))
        ph = rnd.uniform(0, 6)
        pts = []
        for x in range(0, W + 6, 6):
            d = (x - W / 2) / (W * 0.18)
            bump = math.exp(-d * d) * (1 + 0.35 * math.sin(x / 61 + ph) + 0.2 * math.sin(x / 23 + 2 * ph))
            pts.append((x, y0 - bump * amp))
        cr.move_to(*pts[0])  # fill under the line so rows overlap cleanly
        for p in pts[1:]:
            cr.line_to(*p)
        cr.line_to(W, H)
        cr.line_to(0, H)
        cr.close_path()
        cr.set_source_rgba(*rgb(BG0))
        cr.fill()
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        hot = abs(r - rows * 0.55) < 2
        cr.set_source_rgba(*(rgb(BGREEN, 0.85) if hot else rgb(FG, 0.18 + 0.25 * (r / rows))))
        cr.stroke()
    save(surf, "waves")


def dots():
    """a dot grid lit by a green glow"""
    surf, cr = canvas(BG1, BG0)
    cx, cy, reach = W * 0.68, H * 0.42, 620
    glow(cr, cx, cy, reach * 1.3, GREEN, 0.10)
    step = 30
    for y in range(step // 2, H, step):
        for x in range(step // 2, W, step):
            d = math.hypot(x - cx, y - cy) / reach
            light = max(0.0, 1 - d)
            cr.set_source_rgba(*mix(BG3, BGREEN, light ** 2 * 0.8))
            cr.arc(x, y, 1.6 + 1.6 * light, 0, 2 * math.pi)
            cr.fill()
    save(surf, "dots")


def aurora():
    """soft ribbons of light"""
    surf, cr = canvas(BG1, BG0)
    rnd = random.Random(SEED + 3)
    for color, alpha, y in [(AQUA, 0.22, 0.38), (BGREEN, 0.16, 0.48), (BLUE, 0.14, 0.30), (YELLOW, 0.08, 0.56)]:
        for k in range(3):
            cr.set_line_width(rnd.uniform(60, 140))
            cr.set_source_rgba(*rgb(color, alpha / (k + 1)))
            y0 = H * y + rnd.uniform(-40, 40)
            cr.move_to(-100, y0)
            cr.curve_to(W * 0.3, y0 - rnd.uniform(80, 220), W * 0.6, y0 + rnd.uniform(60, 200), W + 100, y0 - 80)
            cr.stroke()
    save(surf, "aurora", blur="0x45")


def peaks():
    """flat mountains in front of a low orange sun"""
    surf, cr = canvas(BG2, BG0)
    rnd = random.Random(SEED + 4)
    glow(cr, W * 0.38, H * 0.62, 420, BORANGE, 0.16)
    cr.set_source_rgba(*rgb(BORANGE, 0.85))
    cr.arc(W * 0.38, H * 0.6, 70, 0, 2 * math.pi)
    cr.fill()
    for i in range(4):
        t = i / 3
        base = H * (0.66 + 0.09 * i)
        cr.move_to(0, H)
        x = -50
        cr.line_to(x, base)
        while x < W + 50:
            x += rnd.uniform(90, 240)
            cr.line_to(x, base - rnd.uniform(40, 220) * (1 - t * 0.5))
            x += rnd.uniform(90, 240)
            cr.line_to(x, base - rnd.uniform(0, 40))
        cr.line_to(W + 50, H)
        cr.close_path()
        cr.set_source_rgba(*mix("#262a22", BG0, t))
        cr.fill()
    save(surf, "peaks")


def rings():
    """topographic rings around a few hills"""
    surf, cr = canvas(BG1, BG0)
    rnd = random.Random(SEED + 5)
    centres = [(W * 0.25, H * 0.35), (W * 0.7, H * 0.6), (W * 0.85, H * 0.2)]
    cr.set_line_width(1.3)
    for ci, (cx, cy) in enumerate(centres):
        ph = [rnd.uniform(0, 6) for _ in range(4)]
        for k in range(1, 26):
            r = k * 22
            for i in range(181):
                a = 2 * math.pi * i / 180
                wob = (9 * math.sin(3 * a + ph[0]) + 6 * math.sin(5 * a + ph[1] + k * 0.2)
                       + 4 * math.sin(7 * a + ph[2]))
                rr = r + wob * (1 + k / 12)
                (cr.move_to if i == 0 else cr.line_to)(cx + rr * math.cos(a), cy + rr * 0.8 * math.sin(a))
            cr.close_path()
            accent = ci == 1 and k == 6
            cr.set_source_rgba(*(rgb(BAQUA, 0.7) if accent else rgb(FG, max(0.03, 0.14 - k * 0.004))))
            cr.stroke()
    save(surf, "rings")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for make in (hills, waves, dots, aurora, peaks, rings):
        make()
