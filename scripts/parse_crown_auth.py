"""Extract auth + config.getValuesHash call path from FmNgIp cache."""
from __future__ import annotations

import re
from pathlib import Path

text = Path(
    r"D:\nautel-tx-dashboard\scraped\crown\fmngip__8258E2936B5D912B9F8F579C431E1C52.cache.js"
).read_text(encoding="utf-8", errors="ignore")

for needle in [
    "login@auth",
    "config.getValuesHash",
    "config.getValue",
    "methodName=",
    "cgi-bin/rpcBridge",
    "XML RPC",
    "xmlrpc",
    "WebSocket",
    "ws://",
    "wss://",
    "@auth",
    "@config",
    "getValuesHash",
]:
    print(f"\n==== {needle} ====")
    for m in re.finditer(re.escape(needle), text):
        i = m.start()
        print(text[max(0, i - 250) : i + 400])
        print("---")
        break

# Find JSON message patterns like "something@something"
msgs = sorted(set(re.findall(r'"([a-zA-Z]+@[a-zA-Z]+)"', text)))
print("\n==== @ messages ====")
for m in msgs:
    print(m)

msgs2 = sorted(set(re.findall(r"'([a-zA-Z.]+@[a-zA-Z.]+)'", text)))
print("\n==== @ messages single ====")
for m in msgs2:
    print(m)

# look for function Emb / Mpc / Lmb related to RPC send
for needle in ["function Emb", "function Mpc", "function Lmb", "function Kmb", "rpcBridge"]:
    print(f"\n==== def {needle} ====")
    for m in re.finditer(re.escape(needle), text):
        i = m.start()
        print(text[i : i + 800])
        print("---")
        break
