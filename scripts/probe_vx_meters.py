"""Probe curated VX meter OIDs one-at-a-time against KVRV Main."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nautel_monitor.oids import VX_CONTROLLER, _oid  # noqa: E402
from nautel_monitor.snmp_client import SnmpError, snmp_get  # noqa: E402

HOST = "10.6.10.205"

# leaf, label, scale divisor (1 = identity)
CANDIDATES = [
    (8, "Local/Remote", 1),
    (257, "Reflected Power", 1000),
    (258, "IPA Reflected Power", 1000),
    (259, "Reject Power", 1000),
    (260, "VSWR", 1000),
    (262, "DC Efficiency", 1000),
    (263, "Average PA Volts", 100),
    (264, "Total PA Current", 1000),
    (265, "Forward Power", 1000),
    (276, "+12V", 1000),
    (277, "+5V", 1000),
    (289, "Modulation Peak", 100),
    (290, "MPX RMS", 100),
    (514, "RF State", 1),
    (320, "PA1 Dissipation", 1000),
    (321, "PA2 Dissipation", 1000),
    (4352, "RF Drive Power", 1000),
    (4353, "PA1 Voltage", 100),
    (4354, "PA1 Current", 1000),
    (4356, "PA2 Voltage", 100),
    (4357, "PA2 Current", 1000),
    (4359, "PA3 Voltage", 100),
    (4360, "PA3 Current", 1000),
    (4362, "PA4 Voltage", 100),
    (4363, "PA4 Current", 1000),
    (4371, "IPA Current", 1000),
    (4381, "PS A Input Voltage", 100),
    (4384, "PS B Input Voltage", 100),
    (4387, "PS C Input Voltage", 100),
    (4389, "IPA Voltage", 100),
    (4704, "Heatsink Temp", 10),
    (272, "+3.3V", 1000),
    (273, "+1.1V", 1000),
    (274, "+2.5V", 1000),
    (275, "+1.5V", 1000),
]

for leaf, label, div in CANDIDATES:
    oid = _oid(VX_CONTROLLER, leaf)
    try:
        raw = snmp_get(HOST, "public", [oid], timeout=2.5, retries=1).get(oid)
    except SnmpError as e:
        print(f"{leaf:5d}  FAIL  {label}: {e}")
        continue
    if raw is None:
        print(f"{leaf:5d}  None  {label}")
        continue
    if isinstance(raw, int):
        val = raw if div == 1 else raw / div
        print(f"{leaf:5d}  {raw:12d}  -> {val:10.3f}  {label}")
    else:
        print(f"{leaf:5d}  {raw!r}  {label}")
