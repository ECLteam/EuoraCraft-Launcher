import csv
import glob
import os

sp = r"e:\Projects\EuoraCraft-Launcher\EuoraCraft-Launcher\.venv\Lib\site-packages"

sizes = {}
for di in glob.glob(os.path.join(sp, "*.dist-info")):
    name = os.path.basename(di)[: -len(".dist-info")]
    path = os.path.join(di, "RECORD")
    if not os.path.exists(path):
        continue
    total = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.reader(f):
            if len(row) >= 3 and row[2]:
                try:
                    total += int(row[2])
                except ValueError:
                    pass
    sizes[name] = total

grand = sum(sizes.values())
print(f"total records = {grand/1e6:.2f} MB")
for name, size in sorted(sizes.items(), key=lambda kv: -kv[1])[:35]:
    print(f"{size/1e6:8.2f} MB  {name}")