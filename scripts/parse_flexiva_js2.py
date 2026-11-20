from __future__ import annotations

import re
from pathlib import Path

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in [
    "ip_ad=",
    "websocketURL",
    "forward_power",
    "fwdPwr",
    "sendlogin",
    "hrs.gui.wss",
    "TxOnState",
]:
    print(f"\n===== {needle} =====")
    for m in re.finditer(re.escape(needle), text):
        start = max(0, m.start() - 120)
        end = min(len(text), m.end() + 250)
        print(text[start:end])
        print("---")
        if needle in ("ip_ad=", "websocketURL") and m.start() > 0:
            break

# Find likely meter object keys
keys = sorted(set(re.findall(r"[A-Za-z_]*(?:[Pp]ower|[Vv]swr|[Tt]emp|[Cc]urrent|[Vv]olt)[A-Za-z0-9_]*", text)))
print("\n===== meter-like keys =====")
for k in keys[:80]:
    print(k)
