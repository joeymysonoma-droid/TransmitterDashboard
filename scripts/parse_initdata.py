from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)

idx = text.find("initData:")
print("=== initData: ===")
print(text[idx : idx + 1200])

print("\n=== sendMsg message samples ===")
for m in re.finditer(r"sendMsg\(\{message:([^}]+)\}", text):
    print(m.group(1)[:200])
    print("---")
    if m.start() > 500000:
        break

print("\n=== message:\" samples ===")
for m in re.finditer(r'message:"([^"]{1,120})"', text):
    msg = m.group(1)
    if any(x in msg for x in ("login", "get", "data", "xml", "json", "~~")):
        print(msg)
