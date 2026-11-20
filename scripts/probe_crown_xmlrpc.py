"""Try Audemat XML-RPC over cgi-bin/rpcBridge with Basic Auth Admin/admin."""
from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

CTX = ssl._create_unverified_context()
BASE = "http://10.2.10.106"
AUTH = base64.b64encode(b"Admin:admin").decode()
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Authorization": f"Basic {AUTH}",
    "Content-Type": "text/xml",
}

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
    "sys.applications.fmngip.meas.pfwd",
    "sys.applications.fmngip.meas.pref",
    "sys.applications.fmngip.meas.vswr",
    "sys.applications.fmngip.meas.heat1",
    "sys.applications.fmngip.meas.amb",
]


def xmlrpc(method: str, params_xml: str) -> str:
    body = f"""<?xml version="1.0"?>
<methodCall>
  <methodName>{method}</methodName>
  <params>{params_xml}</params>
</methodCall>
""".encode()
    req = urllib.request.Request(
        BASE + "/cgi-bin/rpcBridge",
        data=body,
        headers=HEADERS,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=CTX) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: " + e.read().decode("utf-8", errors="replace")[:500]


def string_param(value: str) -> str:
    return f"<param><value><string>{value}</string></value></param>"


def array_of_strings(values: list[str]) -> str:
    members = "".join(f"<value><string>{v}</string></value>" for v in values)
    return f"<param><value><array><data>{members}</data></array></value></param>"


# Try several method shapes
print("=== getValuesHash with path array ===")
params = array_of_strings(PATHS[:5]) + string_param("0") + string_param("0")
print(xmlrpc("config.getValuesHash", params)[:800])

print("\n=== getValuesHash single path ===")
params = string_param(PATHS[0]) + string_param("0") + string_param("0")
print(xmlrpc("config.getValuesHash", params)[:800])

print("\n=== sys.executeLRPCWithParams ===")
# Guess JSON-RPC style payload as string
payload = json.dumps({"paths": PATHS[:5]})
print(xmlrpc("sys.executeLRPCWithParams", string_param(payload))[:800])

# WebSocket login probe
print("\n=== websocket login ===")
try:
    import asyncio
    import websockets

    async def main():
        for url in [
            "ws://10.2.10.106/ws",
            "ws://10.2.10.106/",
            "ws://10.2.10.106/cgi-bin/rpcBridge",
            "ws://10.2.10.106/websocket",
            "ws://10.2.10.106/fmngip/websocket",
        ]:
            try:
                async with websockets.connect(url, open_timeout=4, close_timeout=2) as ws:
                    msg = '{"login@auth":{"login":"Admin","pass":"admin"}}\n'
                    await ws.send(msg)
                    for i in range(5):
                        try:
                            r = await asyncio.wait_for(ws.recv(), timeout=3)
                            print(url, "RECV", repr(r)[:300])
                        except asyncio.TimeoutError:
                            print(url, "timeout")
                            break
            except Exception as e:
                print("WS FAIL", url, e)

    asyncio.run(main())
except Exception as e:
    print("websockets unavailable", e)
