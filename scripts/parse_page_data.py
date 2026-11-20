from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)
print("page_data count", text.count("page_data"))
for m in re.finditer(r".{0,60}page_data.{0,200}", text):
    print(m.group(0))
    print("---")

# Look for how values are assigned into hrs.data[<key>].value
print("\n=== assign patterns ===")
for pat in [
    r"hrs\.data\[([^\]]+)\]\.value\s*=",
    r"\.value=e\.value",
    r"new Data\w*\(",
    r"DatapointMap",
    r"dataMap",
]:
    hits = re.findall(pat, text)
    print(pat, "->", len(hits), hits[:10])
