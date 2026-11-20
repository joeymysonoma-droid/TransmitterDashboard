"""Find GWT login / get-parameter RPC shapes in FmNgIp cache.js."""
from __future__ import annotations

import re
from pathlib import Path

text = Path(
    r"D:\nautel-tx-dashboard\scraped\crown\fmngip__8258E2936B5D912B9F8F579C431E1C52.cache.js"
).read_text(encoding="utf-8", errors="ignore")

needles = [
    "login",
    "Login",
    "password",
    "Password",
    "authenticate",
    "getParam",
    "getValue",
    "readParam",
    "rpcBridge",
    "UserService",
    "AuthService",
    "SessionService",
    "ParameterService",
    "SysService",
    "pfwd",
    "7|0|",
]
for needle in needles:
    idxs = [m.start() for m in re.finditer(re.escape(needle), text)]
    print(f"\n==== {needle} ({len(idxs)}) ====")
    for i in idxs[:3]:
        print(text[max(0, i - 100) : i + 220])
        print("---")

# Service proxy class names
print("\n==== wcs service proxies ====")
for m in re.finditer(r"com\.wcs\.[A-Za-z0-9_.]+", text):
    s = m.group(0)
    if any(x in s for x in ("Service", "Login", "Auth", "Param", "User", "Sys")):
        pass
services = sorted(
    {
        m.group(0)
        for m in re.finditer(r"com\.wcs\.[A-Za-z0-9_.]+(?:Service|Proxy)[A-Za-z0-9_.]*", text)
    }
)
for s in services[:80]:
    print(s)
