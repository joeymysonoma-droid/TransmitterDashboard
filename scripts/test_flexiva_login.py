import hashlib
import time
import urllib.request
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
base = "http://10.2.10.152"
user, pw = "gates", "gates"

key = opener.open(base + "/key", timeout=8).read().decode().strip()
print("KEY", key)
seed = hashlib.md5((key + user.upper() + pw).encode()).hexdigest()
print("SEED", seed)

urls = [
    f"{base}/login?seed={seed}",
    f"{base}/login?seed={seed}&_={int(time.time() * 1000)}",
]
for url in urls:
    try:
        r = opener.open(url, timeout=8)
        body = r.read().decode()
        cookies = [(c.name, c.value) for c in cj]
        print("LOGIN", r.status, body[:500], "cookies", cookies)
    except Exception as e:
        print("LOGIN FAIL", url, e)

# After login attempt, try checkseed and wssajax
for path in ["/checkseed?seed=" + seed, "/wssajax", "/data", "/json"]:
    try:
        r = opener.open(base + path, timeout=8)
        body = r.read().decode()
        print("GET", path, r.status, body[:300])
    except Exception as e:
        print("GET FAIL", path, e)
