#!/usr/bin/env python3
# move every everforest background one shade down the ladder (one pass, so
# a colour is never shifted twice). text and accent colours stay.
import re
import sys

MAP = {"1e2326": "171c1f", "272e33": "1e2326", "2e383c": "272e33", "374145": "2e383c"}

for path in sys.argv[1:]:
    with open(path) as f:
        text = f.read()
    hits = [m for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text) if m.group(1).lower() in MAP]
    text = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: "#" + MAP.get(m.group(1).lower(), m.group(1)), text)
    with open(path, "w") as f:
        f.write(text)
    print(f"{len(hits):4d}  {path}")
