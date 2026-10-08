#!/usr/bin/env python3
# one-off: swap gruvbox hex colours for macOS Tahoe dark ones in the given files.
# yellow was the accent everywhere, so it becomes macOS blue.
import re
import sys

MAP = {
    "1d2021": "141416", "282828": "1c1c1e", "32302f": "232326", "3c3836": "2c2c2e",
    "504945": "3a3a3c", "665c54": "48484a", "7c6f64": "636366", "928374": "8e8e93",
    "a89984": "98989d", "bdae93": "aeaeb2", "d5c4a1": "c7c7cc", "ebdbb2": "f2f2f7",
    "fbf1c7": "ffffff",
    "cc241d": "ff453a", "fb4934": "ff6961",
    "98971a": "30d158", "b8bb26": "4cd964",
    "d79921": "0a84ff", "fabd2f": "409cff",
    "458588": "0a84ff", "83a598": "64d2ff",
    "b16286": "bf5af2", "d3869b": "da8fff",
    "689d6a": "5ac8fa", "8ec07c": "70d7ff",
    "d65d0e": "ff9f0a", "fe8019": "ffb340",
}

for path in sys.argv[1:]:
    with open(path) as f:
        text = f.read()
    new, n = re.subn(r"#([0-9a-fA-F]{6})\b",
                     lambda m: "#" + MAP.get(m.group(1).lower(), m.group(1)), text)
    changed = sum(1 for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text) if m.group(1).lower() in MAP)
    with open(path, "w") as f:
        f.write(new)
    print(f"{changed:4d}  {path}")
