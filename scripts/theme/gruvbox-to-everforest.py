#!/usr/bin/env python3
# swap gruvbox hex colours for everforest dark (hard) in the given files.
# yellow was the accent, so it becomes everforest green -- except in
# terminal palettes (--terminal), where yellow has to stay yellow.
import re
import sys

MAP = {
    "1d2021": "1e2326", "282828": "272e33", "32302f": "2e383c", "3c3836": "2e383c",
    "504945": "374145", "665c54": "4f5b58", "7c6f64": "7a8478", "928374": "859289",
    "a89984": "9da9a0", "bdae93": "9da9a0", "d5c4a1": "d3c6aa", "ebdbb2": "d3c6aa",
    "fbf1c7": "d3c6aa",
    "cc241d": "e67e80", "fb4934": "e67e80",
    "98971a": "a7c080", "b8bb26": "a7c080",
    "d79921": "a7c080", "fabd2f": "a7c080",
    "458588": "7fbbb3", "83a598": "7fbbb3",
    "b16286": "d699b6", "d3869b": "d699b6",
    "689d6a": "83c092", "8ec07c": "83c092",
    "d65d0e": "e69875", "fe8019": "e69875",
}
TERMINAL = dict(MAP, d79921="dbbc7f", fabd2f="dbbc7f")

args = sys.argv[1:]
table = TERMINAL if args and args[0] == "--terminal" else MAP
for path in (args[1:] if table is TERMINAL else args):
    with open(path) as f:
        text = f.read()
    hits = [m for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text) if m.group(1).lower() in table]
    text = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: "#" + table.get(m.group(1).lower(), m.group(1)), text)
    with open(path, "w") as f:
        f.write(text)
    print(f"{len(hits):4d}  {path}")
