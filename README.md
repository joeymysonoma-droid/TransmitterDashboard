# ASMG TX Dashboard

Local web dashboard for **Nautel VS300 / VX**, **AAT FM**, **GatesAir Flexiva**, and **Crown/Ecreso (Audemat)** transmitters, plus **Intraplex HD Link / IP Link**, **Comrex ACCESS**, **BRIC-Link**, and **Inovonics Instream** STL paths. Polls meters and alarms (SNMPv2c for Nautel/AAT/STL, HTTP `/json` for Flexiva, WebSocket `/wscom` for Crown), stores history in SQLite, and shows a fleet overview plus per-TX detail charts. STL links are a second device class: they have their own page, table, and alert keys.

## Features

- Fleet cards: online / degraded / offline, RF state, forward/reflected power, VSWR, temp, alarm count
- **STL page** (`/stl`): HD Link, IP Link, Comrex, BRIC-Link, and Inovonics Instream cards (link state, a few meters, alarm count). Not mixed into the transmitter fleet.
- **Wall / TOC view** (`/wall`): large high-contrast cards for TV displays
- **Settings** (`/settings`): edit transmitters, alerts, and RF control gating in the browser
- Per-TX detail: grouped meters, active alarms, **model-aware** history charts (1h / 24h / 7d / 30d)
- Alerts: dashboard banner + toast, **Ack / Snooze**, recent event history, optional SMTP email
- **RF controls** (default **off**): gated RF On/Off on detail pages (password + confirm)
- Automatic polling (default 30s) with SQLite history (90-day retention)
- Links to Nautel AUI / Flexiva GUI where available
- Nautel OID maps from official MIBs (`mibs/`)

## Quick start

```powershell
cd D:\nautel-tx-dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Edit `config/transmitters.yaml` — set each transmitter’s `host` (and `snmp_community` for Nautel, or `http_username` / `http_password` for Flexiva). Or use **Settings** in the UI after first launch.

```powershell
python main.py
```

Open **http://localhost:8090** (default in config) or the port shown in the console.

```powershell
python main.py --port 8090
```

## Pages

| Path | Description |
|------|-------------|
| `/` | Fleet overview (transmitters only) |
| `/wall` | TOC / wall display |
| `/stl` | STL links (HD Link, IP Link, Comrex, BRIC-Link, Inovonics Instream) |
| `/stl/{id}` | One STL link, numeric meter charts |
| `/settings` | Web config editor (transmitters and STL) |
| `/tx/{id}` | Transmitter detail + charts + RF controls (when enabled) |

## Nautel SNMP checklist

1. Enable SNMP (SNMPv2c is enough)
2. Set a read community and match it in `transmitters.yaml`
3. Allow UDP **161** from the machine running this app
4. Confirm Host Watch Dog is ON if AUI/SNMP drops after idle periods
5. Prefer VPN or a secured site LAN — do not expose SNMP to the internet
6. For RF control: transmitter must be in **REMOTE**, and the write community (or read community if it allows SET) must be configured

## STL SNMP checklist (HD Link / IP Link)

Read-only. Do not SNMP SET these links from the dashboard. There are no STL control endpoints.

1. On the unit, open **Network → SNMP** (HD Link) or **Configuration → Networking → SNMP** (IP Link) and confirm the address bar is the host you intend to poll.
2. Enable SNMPv2c. Leave “Use SNMPv3 Only” off if that option exists. If v1, v2, and v3 are all unchecked, check **SNMPv2** only.
3. Set a real **read-only** community. Do not use a read-write community for this dashboard.
4. Allow UDP **161** from the dashboard PC.
5. Confirm with a read-only probe (no SET):

```powershell
python scripts/probe_stl_snmp.py --host 192.0.2.20 --community public --model hdlink
python scripts/walk_stl_snmp.py --host 192.0.2.20 --community public --limit 200
```

`sysObjectID` for these Intraplex units is under enterprise **1.3.6.1.4.1.290**. That is not the Flexiva FM tree `1.3.6.1.4.1.43768`. Vendor MIB files from [intraplex.org](http://intraplex.org/) go in `mibs/`. Curated OIDs live in `nautel_monitor/stl_oids.py`.

Each family needs a working GET of signal or stream meters plus a link or alarm value before those OIDs are polled. HD Link uses radio SNR, receive level, and receiver lock. IP Link uses per-stream bitrate, loss, and connected state. Walk output belongs in `scraped/stl/` (gitignored). Do not commit communities or site addresses; `config/transmitters.yaml` stays gitignored.

## GatesAir Flexiva

Flexiva FAX units expose live datapoints at `http://{host}/json` (same feed as the web GUI). The dashboard polls that endpoint directly for forward/reflected power, VSWR, RF on, temperature, and fault bits. Credentials (`http_username` / `http_password`, e.g. `gates` / `gates`) are stored for GUI login compatibility; read polling does not consume a Flexiva login slot.

RF writes use GUI login + `/wssajax` and are **experimental** — do not test live until ready.

## Config

| Field | Description |
|-------|-------------|
| `id` | Stable ID used in URLs and history |
| `name` | Display name |
| `model` | `vs300`, `vx`, `aat`, `flexiva`, or `crown` |

STL devices use a separate `stl_devices:` list. `model` is `hdlink`, `iplink`, `comrex`, `briclink`, or `instream`. Fields: `id`, `name`, `host`, `snmp_community` (masked in the API like a password), `snmp_port`, `location`, optional `http_password` (Comrex and BRIC-Link web login, also masked), optional `related_tx_id`, optional `alerts.error_rate`. Commented examples in `config/transmitters.example.yaml` use placeholder hosts only.

Comrex ACCESS and BRIC-Link are read with their web socket. The poll sends login, unit status, and the peer list. It does not connect or disconnect a call. An Inovonics Instream (635 SiteStreamer) is read with HTTP `status.json`: tuned frequency, left/right level, and audio, RF, and RDS alarms. That request does not retune the receiver.
| `host` | Transmitter IP |
| `snmp_community` | Nautel / AAT read community |
| `snmp_write_community` | Optional Nautel write community (falls back to read) |
| `snmp_port` | Default `161` |
| `http_port` | Flexiva / Crown HTTP port (default `80`) |
| `http_username` / `http_password` | Flexiva / Crown / AAT GUI credentials |
| `location` | Optional site/call label |
| `controls_enabled` | Optional per-TX override (`true`/`false`) |
| `controls_password` | Optional per-TX controls password override |

Global options: `poll_interval_seconds`, `history_retention_days`, `history_min_interval_seconds`, `http_host`, `http_port`, `alerts`, `controls`.

### RF controls block

```yaml
controls:
  enabled: false   # must be true before any RF On/Off is allowed
  password: ""     # required when enabled
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service health |
| GET | `/api/transmitters` | All TX states + summary |
| GET | `/api/transmitters/{id}` | One TX |
| GET | `/api/transmitters/{id}/history?range=1h\|24h\|7d\|30d` | History points (includes meter extras) |
| GET | `/api/transmitters/{id}/history.csv?range=...` | CSV export for one TX |
| GET | `/api/history.csv?range=...` | CSV export for fleet |
| POST | `/api/poll` | Poll all now |
| POST | `/api/transmitters/{id}/poll` | Poll one now |
| POST | `/api/transmitters/{id}/control` | RF control (`{"action":"rf_on\|rf_off","password":"..."}`) |
| GET | `/api/controls/status` | Control gating + supported actions |
| GET | `/api/history/stats` | SQLite stats |
| GET | `/api/alerts` | Active alert state |
| POST | `/api/alerts/test` | Send a test email (requires SMTP config) |
| POST | `/api/alerts/ack` | Acknowledge alert (`{"key":"..."}`) |
| POST | `/api/alerts/snooze` | Snooze alert (`{"key":"...","minutes":60}`) |
| GET | `/api/config` | Current config (passwords and STL communities masked) |
| PUT | `/api/config` | Save config + live reload (transmitters and STL) |
| GET | `/api/stl` | All STL states |
| GET | `/api/stl/{id}` | One STL link |
| GET | `/api/stl/{id}/history?range=1h\|24h\|7d\|30d` | STL history (numeric meters) |
| POST | `/api/stl/poll` | Poll all STL links |
| POST | `/api/stl/{id}/poll` | Poll one STL link |

## Alerts

Edit the `alerts:` block in `config/transmitters.yaml` or use **Settings**:

- Dashboard banner/toasts work with no SMTP setup
- **Ack** hides an active alert until it clears (then can fire again)
- **Snooze 1h** suppresses an alert until the timer expires
- Set `email_enabled: true` plus SMTP fields to receive email
- Unconfigured hosts (blank `host`) are skipped when `skip_unconfigured: true`
- Defaults: alert after 3 failed polls, RF not ON, active TX alarm bits, VSWR ≥ 1.5, heatsink ≥ 70 °C
- Per-TX overrides: add an `alerts:` map under a transmitter. Explicit `null` disables that threshold for that TX only.

STL alerts use a separate ruleset. Keys start with `stl:` so they do not collide with transmitter keys. Ack and Snooze are the same endpoints. Rules: unreachable after `unreachable_polls`, link down or a partial path, an active STL alarm, and an error-rate threshold only when that device’s override sets `alerts.error_rate` and the OID is actually present. STL alerts do not use forward power, VSWR, or RF-off.

## RF controls

- Default **disabled** (`controls.enabled: false`)
- Enable in **Settings**, set a controls password, then open a TX detail page
- Each command requires browser confirm + password
- **AAT:** web `rfControl` (same path as AAT_Monitor)
- **Nautel VS/VX:** SNMP SET on `RfOnOff` OID; refuses if not REMOTE
- **Flexiva / Crown:** experimental write clients — authorize before live testing

## MIB reference (Nautel)

Vendor MIB text is under `mibs/`:

- `NAUTEL-VS_SW_5.2-MIB.txt` — VS300 controller meters/alarms
- `NAUTEL-VX-7.1.0-MIB.txt` — VX controller meters/alarms (shared tree for VX2 / VX2.5)

Curated OIDs live in `nautel_monitor/oids.py`. Meter integers use Nautel’s Tenths/Hundredths/Thousandths scaling; `-2147483648` is treated as N/A.

## Notes

- Monitoring remains safe by default; RF writes stay off until explicitly enabled
- Uses a stdlib SNMPv2c client for Nautel and stdlib HTTP for Flexiva / AAT control
- Version **1.7.0**
