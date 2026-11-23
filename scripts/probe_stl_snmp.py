"""Read-only SNMPv2c probe for an Intraplex HD Link or IP Link.

Does not SNMP SET. Host and community come from the command line so they
are not stored in this file.

Examples:
  python scripts/probe_stl_snmp.py --host 192.0.2.20 --community public --model hdlink
  python scripts/probe_stl_snmp.py --host 192.0.2.21 --community public --model iplink
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nautel_monitor.snmp_client import SnmpError, snmp_get  # noqa: E402
from nautel_monitor.stl_oids import (  # noqa: E402
    HD_SCALARS,
    IP_CONNECTED_COLUMN,
    IP_METER_COLUMNS,
    IP_NAME_COLUMN,
    IP_STREAM_TABLE,
    SYS_DESCR,
    SYS_NAME,
    SYS_OBJECT_ID,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only STL SNMP probe")
    parser.add_argument("--host", required=True)
    parser.add_argument("--community", required=True)
    parser.add_argument("--model", choices=("auto", "hdlink", "iplink"), default="auto")
    parser.add_argument("--port", type=int, default=161)
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()

    identity = [SYS_DESCR, SYS_OBJECT_ID, SYS_NAME]
    try:
        result = snmp_get(
            args.host,
            args.community,
            identity,
            port=args.port,
            timeout=args.timeout,
            retries=1,
        )
    except SnmpError as error:
        print(f"FAIL {args.host}: {error}")
        return 1

    descr = str(result.get(SYS_DESCR) or "")
    print(f"sysDescr    {descr}")
    print(f"sysObjectID {result.get(SYS_OBJECT_ID)}")
    print(f"sysName     {result.get(SYS_NAME)}")

    model = args.model
    if model == "auto":
        low = descr.lower()
        if "hdlink" in low or "hd link" in low:
            model = "hdlink"
        elif "iplink" in low or "ip link" in low:
            model = "iplink"
        else:
            print("Could not tell HD Link from IP Link. Pass --model.")
            return 0

    if model == "hdlink":
        oids = [item.oid for item in HD_SCALARS]
        try:
            values = snmp_get(
                args.host,
                args.community,
                oids,
                port=args.port,
                timeout=args.timeout,
                retries=1,
            )
        except SnmpError as error:
            print(f"HD Link scalar GET failed: {error}")
            return 1
        for item in HD_SCALARS:
            print(f"{item.key:16} {values.get(item.oid)!r}")
        return 0

    try:
        from nautel_monitor.snmp_client import snmp_getnext

        current = IP_NAME_COLUMN
        indexes: list[str] = []
        for _ in range(8):
            nxt, value = snmp_getnext(
                args.host,
                args.community,
                current,
                port=args.port,
                timeout=args.timeout,
                retries=1,
            )
            prefix = IP_NAME_COLUMN + "."
            if not nxt.startswith(prefix) or "." in nxt[len(prefix) :]:
                break
            indexes.append(nxt[len(prefix) :])
            print(f"stream {indexes[-1]} name {value!r}")
            current = nxt
    except SnmpError as error:
        print(f"IP Link stream walk failed: {error}")
        return 1

    columns = [IP_CONNECTED_COLUMN, *(col for col, *_rest in IP_METER_COLUMNS)]
    for index in indexes:
        oids = [f"{IP_STREAM_TABLE}.{col}.{index}" for col in columns]
        try:
            values = snmp_get(
                args.host,
                args.community,
                oids,
                port=args.port,
                timeout=args.timeout,
                retries=1,
            )
        except SnmpError as error:
            print(f"stream {index} GET failed: {error}")
            continue
        for col, oid in zip(columns, oids):
            print(f"  col {col} = {values.get(oid)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
