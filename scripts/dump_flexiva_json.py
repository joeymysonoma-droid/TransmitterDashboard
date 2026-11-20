import hashlib
import json
import urllib.request
import http.cookiejar

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
base = "http://10.2.10.152"
user, pw = "gates", "gates"

# Try /json without login first
try:
    raw = opener.open(base + "/json", timeout=10).read().decode()
    data = json.loads(raw)
    print("NOLOGIN keys", len(data), "privileges", data.get("currentuser_privileges"))
except Exception as e:
    print("NOLOGIN FAIL", e)
    data = {}

interesting = [
    "tx.forward_power",
    "tx.reflected_pwr",
    "tx.reflected_power",
    "tx.vswr",
    "tx.tx_on",
    "tx.cfg.tx_on",
    "tx.exciter_power",
    "tx.pa_voltage",
    "tx.pa_current",
    "tx.final_temp",
    "tx.heatsink_temp",
    "tx.drive_power",
    "tx.rf_drive",
    "tx.frequency",
    "tx.fault",
    "tx.alarm",
    "tx.status",
    "tx_model",
    "tx.serial_number",
]
print("\n--- interesting ---")
for k in interesting:
    if k in data:
        print(f"{k}={data[k]!r}")

# Search keys containing power/vswr/temp/fault/on
print("\n--- matching keys ---")
for k in sorted(data):
    kl = k.lower()
    if any(x in kl for x in ("power", "vswr", "refl", "temp", "fault", "alarm", "tx_on", "forward", "status")):
        print(f"{k}={data[k]!r}")

# Login then /json again
key = opener.open(base + "/key", timeout=8).read().decode().strip()
seed = hashlib.md5((key + user.upper() + pw).encode()).hexdigest()
login = json.loads(opener.open(base + f"/login?seed={seed}", timeout=8).read().decode())
print("\nLOGIN", login)
raw2 = opener.open(base + "/json", timeout=10).read().decode()
data2 = json.loads(raw2)
print("AFTERLOGIN privileges", data2.get("currentuser_privileges"), "keys", len(data2))
for k in interesting:
    if k in data2:
        print(f"L {k}={data2[k]!r}")
print("\n--- after login matching ---")
for k in sorted(data2):
    kl = k.lower()
    if any(x in kl for x in ("power", "vswr", "refl", "temp", "fault", "alarm", "tx_on", "forward")):
        print(f"{k}={data2[k]!r}")
