import re
import ssl
import urllib.request
from pathlib import Path

CTX = ssl._create_unverified_context()
BASE = "http://10.2.10.106"
OUT = Path(r"D:\nautel-tx-dashboard\scraped\crown")
OUT.mkdir(parents=True, exist_ok=True)


def get(path: str) -> bytes:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=12, context=CTX) as resp:
        return resp.read()


js = get("/fmngip/fmngip.nocache.js")
(OUT / "fmngip.nocache.js").write_bytes(js)
text = js.decode("utf-8", errors="replace")
print("nocache len", len(text))

for pat in [
    r"[A-Za-z0-9_$]{20,}\.cache\.js",
    r"/fmngip/[A-Za-z0-9_./%-]+",
    r"remoteService|RemoteService|servlet|JSON|xmlhttp",
]:
    hits = sorted(set(re.findall(pat, text, flags=re.I)))
    print(f"\n=== {pat} ({len(hits)}) ===")
    for h in hits[:40]:
        print(" ", h)

# Try common GWT strong-name discovery: look for unflattened keys
strong = re.findall(r"'([A-F0-9]{32})'", text)
print("\nstrong hex", len(set(strong)))
for s in sorted(set(strong))[:10]:
    print(" ", s)

# Probe likely RPC paths
paths = [
    "/fmngip/remote",
    "/fmngip/rpc",
    "/fmngip/dispatch",
    "/fmngip/service",
    "/fmngip/services",
    "/remote",
    "/JSON-RPC",
    "/xmlrpc",
    "/cgi-bin/fmngip",
    "/fmngip/fmngip",
]
print("\n=== rpc probe ===")
for p in paths:
    try:
        data = get(p)
        print("OK", p, len(data), data[:100])
    except Exception as e:
        print("FAIL", p, e)

# If we found a cache.js, fetch it and search for endpoints
caches = sorted(set(re.findall(r"[A-Za-z0-9_$]{20,}\.cache\.js", text)))
for name in caches[:3]:
    path = f"/fmngip/{name}" if not name.startswith("/") else name
    try:
        blob = get(path)
        (OUT / Path(name).name).write_bytes(blob)
        t = blob.decode("utf-8", errors="replace")
        print("\nCACHE", path, "len", len(t))
        for needle in ["forward", "power", "vswr", "RemoteService", "servlet", "/fmngip/", "Crown", "transmitter"]:
            print(needle, t.lower().count(needle.lower()))
        urls = sorted(set(re.findall(r"/[A-Za-z0-9_./%-]{4,80}", t)))
        interesting = [u for u in urls if any(x in u.lower() for x in ("rpc", "service", "cgi", "json", "xml", "status", "meter"))]
        print("interesting urls", interesting[:40])
    except Exception as e:
        print("CACHE FAIL", path, e)
