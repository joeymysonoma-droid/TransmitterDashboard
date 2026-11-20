"""Inspect Audemat FmNgIp cache for RPC methods and try /rpcBridge."""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

CTX = ssl._create_unverified_context()
BASE = "http://10.2.10.106"
CACHE = Path(
    r"D:\nautel-tx-dashboard\scraped\crown\fmngip__8258E2936B5D912B9F8F579C431E1C52.cache.js"
)
text = CACHE.read_text(encoding="utf-8", errors="ignore")

# Find Forward/VSWR/power related string literals
print("=== interesting string literals ===")
for m in re.finditer(
    r'"([^"]{0,80}(?:Forward|forward|VSWR|vswr|Reflected|Power|Crown|Transmitter|Meter)[^"]{0,80})"',
    text,
):
    s = m.group(1)
    if len(s) < 120:
        print(s)

print("\n=== rpcBridge / service snippets ===")
for needle in ["rpcBridge", "RemoteService", "getForward", "forwardPower", "FmNgIp"]:
    idxs = [m.start() for m in re.finditer(re.escape(needle), text)]
    print(needle, "count", len(idxs))
    for i in idxs[:2]:
        print(text[max(0, i - 80) : i + 200])
        print("---")


def request(path: str, data: bytes | None = None, headers: dict | None = None):
    hdrs = {"User-Agent": "Mozilla/5.0", "Content-Type": "text/x-gwt-rpc; charset=utf-8"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10, context=CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print("OK", path, resp.status, body[:300])
            return body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print("HTTP", path, e.code, body[:300])
        return body
    except Exception as e:
        print("FAIL", path, e)
        return None


print("\n=== endpoint probes ===")
for p in ["/rpcBridge", "/FmNgIp", "/FmNgIp/target/FmNgIp-1.8.0_es"]:
    # GET
    try:
        req = urllib.request.Request(BASE + p, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8, context=CTX) as resp:
            print("GET", p, resp.status, resp.read(200))
    except Exception as e:
        print("GET FAIL", p, e)
    # empty POST
    request(p, data=b"")

# Try a minimal GWT-RPC ping
request(
    "/rpcBridge",
    data=b"7|0|4|http://10.2.10.106/fmngip/|X|com.google.gwt.user.client.rpc.XsrfTokenService|getNewXsrfToken|1|2|3|4|",
)
