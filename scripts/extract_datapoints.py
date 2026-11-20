from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)
keys = sorted(set(re.findall(r'["\']((?:tx|lptx|mod\d*)\.[a-z0-9_.\-]+)["\']', text, flags=re.I)))
for k in keys:
    if any(x in k.lower() for x in ("power", "vswr", "temp", "volt", "curr", "tx_on", "fault", "rfl", "fwd", "fan")):
        print(k)
