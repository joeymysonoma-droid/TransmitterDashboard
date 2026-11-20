import re
import ssl
import urllib.request
from pathlib import Path

CTX = ssl._create_unverified_context()
BASE = "http://10.2.10.106"
OUT = Path(r"D:\nautel-tx-dashboard\scraped\crown")
text = (OUT / "fmngip.nocache.js").read_text(encoding="utf-8", errors="ignore")
strongs = sorted(set(re.findall(r"'([A-F0-9]{32})'", text)))
print("strongs", strongs)

# Dump a snippet around each strong name
for s in strongs:
    idx = text.find(s)
    print("\nCONTEXT", s)
    print(text[max(0, idx - 120) : idx + 160])


def get(path: str) -> bytes:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
        return resp.read()


candidates = []
for s in strongs:
    candidates.extend(
        [
            f"/fmngip/{s}.cache.js",
            f"/fmngip/{s}.cache.html",
            f"/{s}.cache.js",
            f"/fmngip/deferredjs/{s}/1.cache.js",
        ]
    )

print("\n=== fetch caches ===")
for p in candidates:
    try:
        data = get(p)
        name = p.strip("/").replace("/", "__")
        (OUT / name).write_bytes(data)
        print("OK", p, len(data))
        t = data.decode("utf-8", errors="replace")
        for needle in [
            "forward",
            "Forward",
            "power",
            "VSWR",
            "vswr",
            "RemoteService",
            "servlet",
            "Crown",
            "transmitter",
            "Meter",
            "rpc",
        ]:
            c = t.count(needle)
            if c:
                print(f"  {needle}: {c}")
        urls = sorted(
            set(
                re.findall(
                    r"/(?:fmngip|cgi-bin|services?|rpc|remote|JSON)[A-Za-z0-9_./%-]*",
                    t,
                    flags=re.I,
                )
            )
        )
        print("  urls", urls[:50])
    except Exception as e:
        print("FAIL", p, e)
