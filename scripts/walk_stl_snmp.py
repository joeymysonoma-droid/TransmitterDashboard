"""Read-only SNMPv2c walk of an Intraplex STL enterprise tree.

Host and community are arguments. Output defaults to scraped/stl/, which
is gitignored. This script never sends SNMP SET.

The enterprise is the branch under 1.3.6.1.4.1 inside sysObjectID.
Do not walk 1.3.6.1.4.1.43768 here; that tree is Flexiva FM only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nautel_monitor.snmp_client import SnmpError, snmp_get, snmp_getnext  # noqa: E402
from nautel_monitor.stl_oids import SYS_OBJECT_ID  # noqa: E402


def enterprise_root(sys_object_id: str) -> str:
    parts = [part for part in str(sys_object_id).split(".") if part]
    marker = ["1", "3", "6", "1", "4", "1"]
    if parts[:6] != marker or len(parts) < 7:
        raise SystemExit(f"sysObjectID is not under enterprises: {sys_object_id}")
    return ".".join(parts[:7])


def walk(host: str, community: str, root: str, port: int, timeout: float, limit: int):
    current = root
    rows: list[tuple[str, object]] = []
    prefix = root.rstrip(".")
    for _ in range(limit):
        try:
            nxt, value = snmp_getnext(
                host, community, current, port=port, timeout=timeout, retries=0
            )
        except SnmpError as error:
            print(f"STOP {current} {error}")
            break
        if nxt != prefix and not nxt.startswith(prefix + "."):
            break
        rows.append((nxt, value))
        current = nxt
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only STL enterprise walk")
    parser.add_argument("--host", required=True)
    parser.add_argument("--community", required=True)
    parser.add_argument("--port", type=int, default=161)
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--root",
        default="",
        help="OID to walk. Default: enterprise number inside sysObjectID.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="File path. Default: scraped/stl/<host>-enterprise.txt",
    )
    args = parser.parse_args()

    root = args.root.strip()
    if not root:
        try:
            identity = snmp_get(
                args.host,
                args.community,
                [SYS_OBJECT_ID],
                port=args.port,
                timeout=args.timeout,
                retries=1,
            )
        except SnmpError as error:
            print(f"FAIL {error}")
            return 1
        root = enterprise_root(str(identity.get(SYS_OBJECT_ID) or ""))
        print(f"sysObjectID {identity.get(SYS_OBJECT_ID)} -> {root}")

    rows = walk(args.host, args.community, root, args.port, args.timeout, args.limit)
    output = Path(args.output) if args.output else ROOT / "scraped" / "stl" / f"{args.host}-enterprise.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# host={args.host} root={root} count={len(rows)}"]
    for oid, value in rows:
        text = str(value).replace("\r", " ").replace("\n", " ")
        if len(text) > 200:
            text = text[:200] + "..."
        lines.append(f"{oid} = {text}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
