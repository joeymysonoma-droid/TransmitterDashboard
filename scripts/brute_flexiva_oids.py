"""Brute likely Flexiva meter OIDs under enterprise 43768."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nautel_monitor.snmp_client import snmp_get  # noqa: E402

HOST = "10.2.10.152"
COMMUNITY = "public"


def try_oids(oids: list[str]) -> None:
    # chunk to avoid huge requests
    for i in range(0, len(oids), 12):
        chunk = oids[i : i + 12]
        try:
            result = snmp_get(HOST, COMMUNITY, chunk, timeout=2.0, retries=0)
        except Exception:
            # try one by one
            for oid in chunk:
                try:
                    result = snmp_get(HOST, COMMUNITY, [oid], timeout=1.5, retries=0)
                    for k, v in result.items():
                        print("HIT", k, "=", v)
                except Exception:
                    pass
            continue
        for k, v in result.items():
            print("HIT", k, "=", v)


def main() -> None:
    candidates: list[str] = []
    # Broad tables under enterprise
    for a in range(1, 20):
        for b in range(0, 30):
            for c in range(0, 20):
                candidates.append(f"1.3.6.1.4.1.43768.{a}.{b}.{c}.0")
                candidates.append(f"1.3.6.1.4.1.43768.{a}.{b}.{c}.1.0")
    # Focused under .7 branch from sysObjectID
    for a in range(1, 15):
        for b in range(0, 40):
            for c in range(0, 40):
                candidates.append(f"1.3.6.1.4.1.43768.7.{a}.{b}.{c}.0")
                candidates.append(f"1.3.6.1.4.1.43768.7.1.{a}.{b}.{c}.0")
                candidates.append(f"1.3.6.1.4.1.43768.7.1.1.{a}.{b}.0")
                candidates.append(f"1.3.6.1.4.1.43768.7.1.1.2.{a}.{b}.0")

    # Dedupe while preserving order
    seen = set()
    uniq = []
    for oid in candidates:
        if oid not in seen:
            seen.add(oid)
            uniq.append(oid)

    print(f"probing {len(uniq)} OIDs...")
    try_oids(uniq)


if __name__ == "__main__":
    main()
