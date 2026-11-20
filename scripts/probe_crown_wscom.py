"""Login to Crown/Audemat via /wscom and fetch meter paths."""
from __future__ import annotations

import asyncio
import json
import ssl

import websockets

HOST = "10.2.10.106"
PATHS = [
    "sys.applications.fmngip.tx.pfwd",
    "sys.applications.fmngip.tx.pref",
    "sys.applications.fmngip.tx.vswr",
    "sys.applications.fmngip.tx.opmode",
    "sys.applications.fmngip.tx.rfPresent",
    "sys.applications.fmngip.tx.fault",
    "sys.applications.fmngip.tx.warning",
    "sys.applications.fmngip.tx.type",
    "sys.applications.fmngip.tx.name",
    "sys.applications.fmngip.tx.pwr",
    "sys.applications.fmngip.tx.pwrMax",
    "sys.applications.fmngip.meas.pfwd",
    "sys.applications.fmngip.meas.pref",
    "sys.applications.fmngip.meas.vswr",
    "sys.applications.fmngip.meas.heat1",
    "sys.applications.fmngip.meas.heat2",
    "sys.applications.fmngip.meas.amb",
    "sys.applications.fmngip.meas.cur1",
    "sys.applications.fmngip.meas.volt1",
]


async def try_url(url: str, sslctx=None):
    print(f"\n=== {url} ===")
    try:
        async with websockets.connect(
            url,
            ssl=sslctx,
            open_timeout=8,
            max_size=10_000_000,
            additional_headers=[("Origin", f"http://{HOST}")],
        ) as ws:
            print("OPEN")
            login = '{"login@auth":{"login":"Admin","pass":"admin"}}\n'
            await ws.send(login)
            for i in range(8):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=4)
                    print("AUTH", i, repr(msg)[:400])
                    if "Valid" in str(msg) or "accessRight" in str(msg) or "ok" in str(msg).lower():
                        break
                except asyncio.TimeoutError:
                    print("AUTH timeout")
                    break

            # Try JSON-RPC getValuesHash variants
            reqs = []
            rid = 1
            for method, params in [
                ("config.getValuesHash", [PATHS, 0, 0]),
                ("config.getValuesHash", PATHS),
                ("config.getPartValuesHash", [PATHS, 0, 0]),
                ("sys.executeLRPCWithParams", ["config.getValuesHash", PATHS]),
            ]:
                payload = {
                    "jsonrpc@jsonrpc": {
                        "jsonrpc": "2.0",
                        "id": rid,
                        "method": method,
                        "params": params,
                    }
                }
                reqs.append((rid, method, json.dumps(payload) + "\n"))
                rid += 1

            for rid, method, body in reqs:
                print("SEND", method)
                await ws.send(body)
                for i in range(6):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=4)
                        print("RECV", rid, repr(msg)[:500])
                    except asyncio.TimeoutError:
                        print("timeout", rid)
                        break
    except Exception as e:
        print("FAIL", type(e).__name__, e)


async def main():
    sslctx = ssl._create_unverified_context()
    await try_url(f"ws://{HOST}/wscom")
    await try_url(f"wss://{HOST}/wscom", sslctx=sslctx)


asyncio.run(main())
