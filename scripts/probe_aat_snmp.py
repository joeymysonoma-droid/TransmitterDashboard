import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nautel_monitor.snmp_client import SnmpError, snmp_get

HOST = "10.2.10.58"
BASE = "1.3.6.1.4.1.51550.4.2"
keys = [
    ("sysDescr", "1.3.6.1.2.1.1.1.0"),
    ("sysName", "1.3.6.1.2.1.1.5.0"),
    ("fwd", f"{BASE}.1.0"),
    ("rfl", f"{BASE}.2.0"),
    ("vswr", f"{BASE}.3.0"),
    ("cur1", f"{BASE}.4.0"),
    ("cur2", f"{BASE}.5.0"),
    ("cur3", f"{BASE}.6.0"),
    ("vlt1", f"{BASE}.7.0"),
    ("vlt2", f"{BASE}.8.0"),
    ("vlt3", f"{BASE}.9.0"),
    ("hs", f"{BASE}.10.0"),
    ("amb", f"{BASE}.11.0"),
    ("exc", f"{BASE}.12.0"),
    ("fault", f"{BASE}.13.0"),
    ("amp", f"{BASE}.14.0"),
]
for name, oid in keys:
    try:
        r = snmp_get(HOST, "public", [oid], timeout=3, retries=1)
        print(f"{name:8s} {r.get(oid)!r}")
    except SnmpError as e:
        print(f"{name:8s} FAIL {e}")
