from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)
print("secCom count", text.count("secCom"))
for m in re.finditer(r".{0,80}secCom.{0,160}", text):
    print(m.group(0))
    print("---")
    if m.start() > 200000:
        break

print("\n=== ajax login ===")
idx = text.find("login:function")
print(text[idx : idx + 1000])

# Find HTTP endpoints
print("\n=== /cgi or ajax urls ===")
for m in re.finditer(r'["\'](/[^"\']*(?:cgi|login|json|xml|data)[^"\']*)["\']', text, re.I):
    print(m.group(1))
