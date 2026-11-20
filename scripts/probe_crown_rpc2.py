"""Probe Audemat cgi-bin/rpcBridge and look for get/set parameter APIs."""
from __future__ import annotations

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

# Find parameter path strings under sys.applications.fmngip.tx
tx_params = sorted(
    set(re.findall(r"sys\.applications\.fmngip\.tx\.[A-Za-z0-9_.]+", text))
)
print("tx params", len(tx_params))
for p in tx_params:
    print(p)

print("\n=== meas params ===")
meas = sorted(set(re.findall(r"sys\.applications\.fmngip\.meas\.[A-Za-z0-9_.]+", text)))
for p in meas:
    print(p)

# Find GWT service interfaces
print("\n=== service interface names ===")
for m in re.finditer(r"com\.wcs\.[A-Za-z0-9_.]+Service", text):
    print(m.group(0))
services = sorted(set(re.findall(r"com\.wcs\.[A-Za-z0-9_.$]+", text)))
for s in services:
    if "Service" in s or "Rpc" in s or "Bridge" in s:
        print(s)


def try_url(path: str, data: bytes | None = None, content_type: str | None = None):
    headers = {"User-Agent": "Mozilla/5.0"}
    if content_type:
        headers["Content-Type"] = content_type
    method = "POST" if data is not None else "GET"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10, context=CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(method, path, resp.status, body[:250].replace("\n", " "))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(method, "HTTP", path, e.code, body[:250].replace("\n", " "))
    except Exception as e:
        print(method, "FAIL", path, e)


print("\n=== endpoints ===")
for p in [
    "/cgi-bin/rpcBridge",
    "/cgi-bin/rpcBridge?",
    "/cgi-bin/status",
    "/cgi-bin/get",
    "/cgi-bin/param",
]:
    try_url(p)

# POST form-ish
try_url(
    "/cgi-bin/rpcBridge",
    data=b"action=get&path=sys.applications.fmngip.tx.pwr",
    content_type="application/x-www-form-urlencoded",
)
try_url(
    "/cgi-bin/rpcBridge",
    data=b'{"method":"get","params":["sys.applications.fmngip.tx.pwr"]}',
    content_type="application/json",
)

# Search nearby rpcBridge usage for payload format
idx = text.find("cgi-bin/rpcBridge")
print("\n=== rpcBridge context ===")
print(text[max(0, idx - 400) : idx + 600])
