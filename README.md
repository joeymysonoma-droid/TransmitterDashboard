# ASMG TX Dashboard

Local web dashboard for **Nautel VS300 / VX**, **AAT FM**, **GatesAir Flexiva**, and **Crown/Ecreso (Audemat)** transmitters. Polls meters and alarms (SNMPv2c for Nautel/AAT, HTTP `/json` for Flexiva, WebSocket `/wscom` for Crown), stores history in SQLite, and shows a fleet overview plus per-TX detail charts.

## Features

- Fleet cards: online / degraded / offline, RF state, forward/reflected power, VSWR, temp, alarm count
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
| `/` | Fleet overview |
| `/wall` | TOC / wall display |
| `/settings` | Web config editor |
| `/tx/{id}` | Transmitter detail + charts + RF controls (when enabled) |

## Nautel SNMP checklist

1. Enable SNMP (SNMPv2c is enough)
2. Set a read community and match it in `transmitters.yaml`
3. Allow UDP **161** from the machine running this app
4. Confirm Host Watch Dog is ON if AUI/SNMP drops after idle periods
5. Prefer VPN or a secured site LAN — do not expose SNMP to the internet
6. For RF control: transmitter must be in **REMOTE**, and the write community (or read community if it allows SET) must be configured

## GatesAir Flexiva

Flexiva FAX units expose live datapoints at `http://{host}/json` (same feed as the web GUI). The dashboard polls that endpoint directly for forward/reflected power, VSWR, RF on, temperature, and fault bits. Credentials (`http_username` / `http_password`, e.g. `gates` / `gates`) are stored for GUI login compatibility; read polling does not consume a Flexiva login slot.

RF writes use GUI login + `/wssajax` and are **experimental** — do not test live until ready.

## Config

| Field | Description |
|-------|-------------|
| `id` | Stable ID used in URLs and history |
| `name` | Display name |
| `model` | `vs300`, `vx`, `aat`, `flexiva`, or `crown` |
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
| GET | `/api/config` | Current config (passwords masked) |
| PUT | `/api/config` | Save config + live reload |

## Alerts

Edit the `alerts:` block in `config/transmitters.yaml` or use **Settings**:

- Dashboard banner/toasts work with no SMTP setup
- **Ack** hides an active alert until it clears (then can fire again)
- **Snooze 1h** suppresses an alert until the timer expires
- Set `email_enabled: true` plus SMTP fields to receive email
- Unconfigured hosts (blank `host`) are skipped when `skip_unconfigured: true`
- Defaults: alert after 3 failed polls, RF not ON, active TX alarm bits, VSWR ≥ 1.5, heatsink ≥ 70 °C
- Per-TX overrides: add an `alerts:` map under a transmitter. Explicit `null` disables that threshold for that TX only.

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
- Version **1.5.0**
