from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in ["/login", "/key", "/checkseed", "dataStartup", "url:\"/"]:
    print("\n====", needle, "====")
    idxs = [m.start() for m in re.finditer(re.escape(needle), text)]
    for idx in idxs[:3]:
        print(text[max(0, idx - 200) : idx + 500])
        print("---")
