import re
import sys

path = sys.argv[1]
pattern = re.compile(r"\s*\d+,\s*(\d+),\s*\d+,\s*\d+,\s*'[a-z]',\s*'(.+)'")

rows = []
with open(path, encoding="utf-8", errors="replace") as fh:
    for line in fh:
        m = pattern.match(line)
        if m:
            rows.append((int(m.group(1)), m.group(2)))

rows.sort(key=lambda x: -x[0])
total = sum(r[0] for r in rows)
print(f"entries={len(rows)}  total={total/1e6:.2f} MB")
for size, name in rows[:40]:
    print(f"{size/1e6:8.2f} MB  {name}")