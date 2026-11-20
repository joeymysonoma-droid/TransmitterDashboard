from pathlib import Path
import re
text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(encoding="utf-8", errors="ignore")
# Find WssLogin sendlogin body
idx = text.find("WssLogin=Class.extend")
print(text[idx:idx+2500])
print("\n\n==== responselogin ====")
idx = text.find("responselogin:")
print(text[idx:idx+1500])
print("\n\n==== onMessage json handling ====")
idx = text.find('case"json"')
print(text[idx:idx+2000])
print("\n\n==== hrs.data assignment ====")
for m in re.finditer(r"hrs\.data\[", text):
    pass
# find where data values get set from websocket
idx = text.find("parseJSON")
print("parseJSON contexts:")
for m in re.finditer(r".{0,80}parseJSON.{0,120}", text):
    print(m.group(0))
    print("---")
