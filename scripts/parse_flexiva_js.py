"""Extract useful strings from Flexiva minified JS."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz")
text = SRC.read_text(encoding="utf-8", errors="ignore")

patterns = [
    r"wss_create",
    r"WebSocket",
    r"43768",
    r"1\.3\.6(?:\.\d+){3,}",
    r"forward[_A-Za-z]*[Pp]ower",
    r"[Rr]eflected",
    r"VSWR|vswr",
    r"ws://[^\"'\s]+",
    r"wss://[^\"'\s]+",
    r"new WebSocket\([^)]+\)",
    r"TX_ON|TX_OFF|FwdPwr|RflPwr|fwdPwr|rflPwr",
]

for pat in patterns:
    matches = re.findall(pat, text)
    uniq = sorted(set(matches))[:30]
    print(f"\n=== {pat} ({len(matches)} hits, {len(set(matches))} unique) ===")
    for m in uniq:
        print(m)

# Context around wss_create
idx = text.find("function wss_create")
if idx < 0:
    idx = text.find("wss_create")
print("\n=== context wss_create ===")
print(text[max(0, idx - 200) : idx + 800])

idx2 = text.find("new WebSocket")
print("\n=== context new WebSocket ===")
print(text[max(0, idx2 - 200) : idx2 + 800])
