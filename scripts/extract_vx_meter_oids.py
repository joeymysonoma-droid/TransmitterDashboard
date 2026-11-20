"""Parse VX controller meter OBJECT-TYPEs + leaf IDs from the MIB."""
from __future__ import annotations

import re
from pathlib import Path

text = Path(r"D:\nautel-tx-dashboard\mibs\NAUTEL-VX-7.1.0-MIB.txt").read_text(
    encoding="utf-8", errors="ignore"
)

block_re = re.compile(
    r"^(vxController(?:Meter|LocalRemote|RfState|Status)\w*)\s+OBJECT-TYPE\n"
    r"(.*?)\n"
    r"\s*::=\s*\{\s*vxController\s+(\d+)\s*\}",
    re.MULTILINE | re.DOTALL,
)

rows = []
for m in block_re.finditer(text):
    name, body, leaf = m.group(1), m.group(2), int(m.group(3))
    syn = re.search(r"SYNTAX\s+([^\n]+)", body)
    syntax = syn.group(1).strip() if syn else "?"
    rows.append((leaf, name, syntax))

rows.sort()
for leaf, name, syntax in rows:
    print(f"{leaf:5d}  {name:55s}  {syntax}")
print("COUNT", len(rows))
