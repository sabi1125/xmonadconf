#!/usr/bin/env python3
# move every everforest background down the shade ladder (one pass, so
# a colour is never shifted twice). text and accent colours stay.
import re
import sys

# ladder, darkest first; below #1e2326 it is extended at the same step size
LADDER = ["0c1012", "111618", "171c1f", "1e2326", "272e33", "2e383c", "374145", "414b50", "495156"]
# steps to go darker; negative goes lighter
STEPS = int(sys.argv.pop(1)) if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit() else 1
MAP = {c: LADDER[i - STEPS] for i, c in enumerate(LADDER) if 0 <= i - STEPS < len(LADDER)}

for path in sys.argv[1:]:
    with open(path) as f:
        text = f.read()
    hits = [m for m in re.finditer(r"#([0-9a-fA-F]{6})\b", text) if m.group(1).lower() in MAP]
    text = re.sub(r"#([0-9a-fA-F]{6})\b", lambda m: "#" + MAP.get(m.group(1).lower(), m.group(1)), text)
    with open(path, "w") as f:
        f.write(text)
    print(f"{len(hits):4d}  {path}")
