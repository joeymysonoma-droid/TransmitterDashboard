"""Walk Flexiva under known sysObjectID branches and probe meter leaves."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from walk_flexiva import snmp_getnext, walk  # noqa: E402
from nautel_monitor.snmp_client import snmp_get  # noqa: E402


def main() -> None:
    host = "10.2.10.152"
    community = "public"
    roots = [
        "1.3.6.1.4.1.43768.7",
        "1.3.6.1.4.1.43768.7.1",
        "1.3.6.1.4.1.43768.7.1.1",
        "1.3.6.1.4.1.43768.7.1.1.2",
        "1.3.6.1.4.1.43768.7.1.2",
        "1.3.6.1.4.1.43768.7.2",
        "1.3.6.1.4.1.43768.1",
        "1.3.6.1.4.1.43768.2",
    ]
    for root in roots:
        print(f"\n=== walk {root} ===")
        rows = walk(host, community, root, limit=80)
        print(f"count={len(rows)}")
        for oid, value in rows[:40]:
            print(f"{oid} = {value!r}")

    # Brute scalar leaves under 43768.7.1.1.2.*
    print("\n=== brute scalars under sysObjectID ===")
    base = "1.3.6.1.4.1.43768.7.1.1.2"
    hits = []
    for a in range(0, 30):
        for b in list(range(0, 20)) + [100, 256]:
            for suffix in (f".{a}.{b}.0", f".{a}.{b}", f".{a}.0"):
                oid = base + suffix
                try:
                    result = snmp_get(host, community, [oid], timeout=1.2, retries=0)
                    if result:
                        hits.append((oid, result.get(oid)))
                        print("HIT", oid, result.get(oid))
                except Exception:
                    pass
    print(f"brute hits={len(hits)}")


if __name__ == "__main__":
    main()
