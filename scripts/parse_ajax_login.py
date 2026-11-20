from pathlib import Path
import re

text = Path(r"D:\nautel-tx-dashboard\scraped\flexiva\js__lpfm_min_press.js.gz").read_text(
    encoding="utf-8", errors="ignore"
)

for needle in ["/wssajax", "wssajax", "login.php", "/login", "username=", "password="]:
    print(needle, text.count(needle))

idx = text.find("/wssajax")
print("\n=== /wssajax context ===")
print(text[max(0, idx - 400) : idx + 800])

# Find classLogin login function ajax
idx = text.find("classLogin")
print("\n=== classLogin area urls ===")
chunk = text[idx : idx + 8000] if idx >= 0 else ""
for m in re.finditer(r'url:"([^"]+)"', chunk):
    print(m.group(1))

# Broader search for login ajax
print("\n=== login ajax urls ===")
for m in re.finditer(r'.{0,120}url:"([^"]+)".{0,80}login|login.{0,80}url:"([^"]+)"', text, re.I):
    print(m.group(0)[:200])
    print("---")
