"""Extract VX controller meter-like OBJECT-TYPEs from the Nautel MIB."""
from __future__ import annotations

import re
from pathlib import Path

mib = Path(r"D:\nautel-tx-dashboard\mibs\NAUTEL-VX-7.1.0-MIB.txt").read_text(
    encoding="utf-8", errors="ignore"
)

# Match OBJECT-TYPE blocks under vxController
pattern = re.compile(
    r"^(\w+)\s+OBJECT-TYPE\s+"
    r"SYNTAX\s+(\S+(?:\s+\S+)?)\s+"
    r'(?:.*?DESCRIPTION\s+"((?:[^"]|\\")*)")?'
    r".*?::=\s*\{\s*vxController\s+(\d+)\s*\}",
    re.MULTILINE | re.DOTALL,
)

interesting = []
for m in pattern.finditer(mib):
    name, syntax, desc, leaf = m.group(1), m.group(2), m.group(3) or "", m.group(4)
    low = name.lower()
    if any(
        k in low
        for k in (
            "meter",
            "power",
            "vswr",
            "swr",
            "temp",
            "volt",
            "current",
            "fan",
            "rfstate",
            "localremote",
            "pa",
            "ipa",
            "supply",
            "ambient",
            "heatsink",
            "exciter",
            "drive",
            "dc",
            "ac",
        )
    ):
        interesting.append((int(leaf), name, syntax.strip(), desc[:80].replace("\n", " ")))

interesting.sort()
for leaf, name, syntax, desc in interesting:
    print(f"{leaf:5d}  {name:55s}  {syntax:20s}  {desc}")
print("TOTAL", len(interesting))
