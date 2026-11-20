"""Probe Crown/Audemat FMNGIP UI at 10.2.10.106 for meter endpoints."""
from __future__ import annotations

import re
import ssl
import urllib.request
from pathlib import Path

HOST = "10.2.10.106"
CTX = ssl._create_unverified_context()
OUT = Path(r"D:\nautel-tx-dashboard\scraped\crown")
OUT.mkdir(parents=True, exist_ok=True)


def get(path: str) -> tuple[int, str, str]:
    url = f"http://{HOST}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8, context=CTX) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, resp.headers.get("Content-Type", ""), body


status, ctype, html = get("/")
(OUT / "index.html").write_text(html, encoding="utf-8")
print("INDEX", status, ctype, "len", len(html))

# Extract script/css/ajax hints
for pat in [
    r'src=["\']([^"\']+)["\']',
    r'href=["\']([^"\']+)["\']',
    r'["\'](/[^"\']*(?:json|xml|cgi|api|status|meter|data)[^"\']*)["\']',
    r'fmngip/[^"\']+',
]:
    hits = sorted(set(re.findall(pat, html, flags=re.I)))
    print(f"\n=== {pat} ({len(hits)}) ===")
    for h in hits[:40]:
        print(h)

# Probe common paths
paths = [
    "/fmngip/",
    "/fmngip/index.html",
    "/fmngip/login.html",
    "/cgi-bin/status",
    "/status.xml",
    "/status.json",
    "/data.json",
    "/meters.json",
    "/rpc",
    "/jsonrpc",
    "/api/v1/status",
    "/worldcast/",
]
print("\n=== path probe ===")
for p in paths:
    try:
        st, ct, body = get(p)
        print("OK", p, st, ct, body[:120].replace("\n", " "))
    except Exception as e:
        print("FAIL", p, e)
