"""Probe Flexiva SNMP for enterprise OID and sample meters."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nautel_monitor.snmp_client import snmp_get  # noqa: E402


def try_get(host: str, community: str, oids: list[str]) -> dict:
    try:
        return snmp_get(host, community, oids, timeout=2.5, retries=0)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": str(exc)}


def main() -> None:
    host = "10.2.10.152"
    community = "public"

    print("sysObjectID / descr:")
    print(
        try_get(
            host,
            community,
            [
                "1.3.6.1.2.1.1.2.0",
                "1.3.6.1.2.1.1.1.0",
                "1.3.6.1.2.1.1.5.0",
            ],
        )
    )

    enterprises = [
        1977,
        28107,
        30826,
        4413,
        11606,
        17713,
        25878,
        31883,
        33735,
        13859,
        24845,
        25506,
        8072,
    ]
    for ent in enterprises:
        for leaf in (".1.0", ".1.1.0", ".1.1.1.0", ".2.1.0", ".0"):
            oid = f"1.3.6.1.4.1.{ent}{leaf}"
            result = try_get(host, community, [oid])
            if "__error__" not in result:
                print("HIT", oid, result)


if __name__ == "__main__":
    main()
