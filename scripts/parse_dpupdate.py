from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)

idx = text.find("dpUpdate")
print("=== first dpUpdate ===")
print(text[idx : idx + 800])

# Find function definitions containing dpUpdate
for m in re.finditer(r".{0,40}dpUpdate.{0,200}", text):
    s = m.group(0)
    if "function" in s or "dpUpdate:" in s or "prototype" in s:
        print("---")
        print(s)

print("\n=== case get ===")
idx = text.find('case"get"')
print(text[idx : idx + 900])

# How initial data dictionary is built
idx = text.find("hrs={")
print("\n=== hrs={ ===", idx)
print(text[idx : idx + 600] if idx >= 0 else "not found")

idx = text.find("data:{}")
print("\n=== data:{} contexts ===")
for m in re.finditer(r".{0,80}data:\{\}.{0,80}", text):
    print(m.group(0))
    print("---")
