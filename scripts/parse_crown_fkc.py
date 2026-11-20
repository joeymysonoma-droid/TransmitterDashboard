import re
from pathlib import Path

text = Path(
    r"D:\nautel-tx-dashboard\scraped\crown\fmngip__8258E2936B5D912B9F8F579C431E1C52.cache.js"
).read_text(encoding="utf-8", errors="ignore")

for needle in [
    "function FKc",
    "gde=",
    "rle=",  # cgi-bin/rpcBridge
    "function zmb",  # build xmlrpc payload
    "function Emb",
    "XmlRpcClient",
    "setServiceUrl",
    "serviceUrl",
]:
    print(f"\n==== {needle} ====")
    for m in re.finditer(re.escape(needle), text):
        i = m.start()
        print(text[max(0, i - 80) : i + 500])
        print("---")
        break

# Find assignments that set rpcBridge as URL
for m in re.finditer(r"rle", text):
    # too many; look near XmlRpc or FKc
    pass

# Search for string concat with rpcBridge variable usage patterns
idx = text.find("cgi-bin/rpcBridge")
# find the var name assignment - already know rle=
# find uses of rle as URL: often something like host+rle
print("\n==== uses near path= ====")
for needle in ["vle=", "sle=", "tle=", "jle=", "xle=", "ule=", "hle=", "ile=", "gle="]:
    m = re.search(re.escape(needle) + r"'([^']*)'", text)
    if m:
        print(needle, repr(m.group(1)))
