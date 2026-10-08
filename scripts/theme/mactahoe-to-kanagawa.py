#!/usr/bin/env python3
# one-off: swap the macOS Tahoe dark colours for kanagawa dragon
# (rebelot/kanagawa.nvim) in the given files.
import re
import sys

MAP = {
    # backgrounds, darkest first
    "141416": "12120f", "1c1c1e": "181616", "1f1f22": "1d1c19", "232326": "1d1c19",
    "2c2c2e": "282727", "2c2c30": "282727", "3a3a3c": "393836", "48484a": "625e5a",
    # greys and text
    "636366": "737c73", "8e8e93": "7a8382", "98989d": "a6a69c", "aeaeb2": "9e9b93",
    "c7c7cc": "c8c093", "f2f2f7": "c5c9c5", "ffffff": "dcd7ba",
    # accent (was soft white) -> dragon gold
    "d6cfbf": "c4b28a",
    # colours
    "ff453a": "c4746e", "ff6961": "e46876",
    "30d158": "8a9a7b", "4cd964": "87a987",
    "ffd60a": "c4b28a", "ffe55c": "e6c384",
    "0a84ff": "8ba4b0", "409cff": "7fb4ca", "64d2ff": "8ea4a2",
    "bf5af2": "a292a3", "da8fff": "938aa9",
    "5ac8fa": "8ea4a2", "70d7ff": "7aa89f",
    "ff9f0a": "b6927b", "ffb340": "b98d7b",
}

for path in sys.argv[1:]:
    with open(path) as f:
        text = f.read()
    hits = [m for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text) if m.group(1).lower() in MAP]
    text = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: "#" + MAP.get(m.group(1).lower(), m.group(1)), text)
    with open(path, "w") as f:
        f.write(text)
    print(f"{len(hits):4d}  {path}")
