"""See what Crown/Audemat exposes without credentials."""
from __future__ import annotations

import ssl
import urllib.error
import urllib.request

CTX = ssl._create_unverified_context()
BASE = "http://10.2.10.106"


def fetch(path: str, data: bytes | None = None, headers: dict | None = None):
    hdrs = {"User-Agent": "Mozilla/5.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers=hdrs,
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8, context=CTX) as resp:
            body = resp.read(500).decode("utf-8", errors="replace")
            print("OK", path, resp.status, body[:200].replace("\n", " "))
    except urllib.error.HTTPError as e:
        body = e.read(300).decode("utf-8", errors="replace")
        print("HTTP", path, e.code, body[:180].replace("\n", " "))
    except Exception as e:
        print("FAIL", path, e)


# Common public/status paths
for p in [
    "/",
    "/fmngip/",
    "/cgi-bin/rpcBridge",
    "/snmp/",
    "/mib/",
    "/status",
    "/login",
    "/auth",
]:
    fetch(p)

# Try a few common default logins against likely auth endpoints (read-only discovery).
# These are vendor defaults, not a credential attack list.
defaults = [
    ("admin", "admin"),
    ("admin", "password"),
    ("admin", "audemat"),
    ("admin", "worldcast"),
    ("guest", "guest"),
    ("operator", "operator"),
    ("user", "user"),
]
print("\n=== default login probes (POST form-ish) ===")
for user, pw in defaults:
    body = f"username={user}&password={pw}&user={user}&pass={pw}&login={user}".encode()
    for path in ["/login", "/cgi-bin/login", "/auth/login", "/fmngip/login"]:
        fetch(
            path,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
