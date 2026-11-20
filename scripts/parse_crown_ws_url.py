import re
from pathlib import Path

text = Path(
    r"D:\nautel-tx-dashboard\scraped\crown\fmngip__8258E2936B5D912B9F8F579C431E1C52.cache.js"
).read_text(encoding="utf-8", errors="ignore")

for needle in [
    "Connect to ws://",
    "Connect to wss://",
    "new WebSocket",
    "WebSocket(",
    ":8080",
    ":9080",
    ":8001",
    "/ws",
    "websocket",
    "OPEN",
    "login@auth",
    "jsonrpc@jsonrpc",
]:
    print(f"\n==== {needle} ====")
    for m in re.finditer(re.escape(needle), text, flags=re.I):
        i = m.start()
        print(text[max(0, i - 200) : i + 350])
        print("---")
        break
