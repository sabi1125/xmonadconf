#!/usr/bin/env python3
# gruvbox colours on darker backgrounds: swap only gruvbox's background
# shades for near-black (everforest-tinted) ones. every other colour stays
# gruvbox. --accent also turns the yellow accent into bright green
# (not for terminal palettes, where yellow must stay yellow).
import re
import sys

BG = {"1d2021": "111618", "282828": "171c1f", "32302f": "171c1f",
      "3c3836": "1e2326", "504945": "272e33"}
ACCENT = {"d79921": "b8bb26"}

args = sys.argv[1:]
table = dict(BG)
if args and args[0] == "--accent":
    args = args[1:]
    table.update(ACCENT)
for path in args:
    with open(path) as f:
        text = f.read()
    hits = [m for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text) if m.group(1).lower() in table]
    text = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: "#" + table.get(m.group(1).lower(), m.group(1)), text)
    with open(path, "w") as f:
        f.write(text)
    print(f"{len(hits):4d}  {path}")
