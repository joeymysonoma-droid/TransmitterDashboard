from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)

needles = [
    "var salt",
    "salt=",
    "gaFaxTempKey",
    "checkAuth",
    "loginSuccessful",
    "dataStartupRequest",
    'url:"/data',
    'url:"/json',
    "secCom=!0",
    "secCom=true",
    "wssajax",
]
for needle in needles:
    print("\n====", needle, "====")
    for m in re.finditer(re.escape(needle), text):
        i = m.start()
        print(text[max(0, i - 150) : i + 400])
        print("---")
        break
