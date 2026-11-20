from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)
for needle in [
    "hrs.data=",
    "hrs.data[",
    "DataPoint",
    "updateData",
    "setData",
    "datapoint",
    "dpUpdate",
    "parseData",
]:
    print(needle, text.count(needle))

# Find class that owns data map
idx = text.find("hrs.data")
print("first hrs.data context:")
print(text[idx : idx + 500])

# Look for message types that carry values
for m in re.finditer(r'case"[a-z]+"', text[170000:190000]):
    pass
chunk = text[170000:190000]
print("\ncases in onMessage region:")
print(sorted(set(re.findall(r'case"([a-z]+)"', chunk))))
