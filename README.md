# ASMG TX Dashboard

Local web dashboard for **Nautel VS300 / VX**, **AAT FM**, **GatesAir Flexiva**, and **Crown/Ecreso (Audemat)** transmitters. Polls meters and alarms (SNMPv2c for Nautel/AAT, HTTP `/json` for Flexiva, WebSocket `/wscom` for Crown), stores history in SQLite, and shows a fleet overview plus per-TX detail charts.

## Features

- Fleet cards: online / degraded / offline, RF state, forward/reflected power, VSWR, temp, alarm count
- Per-TX detail: grouped meters, active alarms, history charts (1h / 24h / 7d)
- Alerts: dashboard banner + toast for unreachable, RF off, TX alarms, and optional thresholds
- Optional email alerts via SMTP (`alerts:` section in YAML)
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

Edit `config/transmitters.yaml` — set each transmitter’s `host` (and `snmp_community` for Nautel, or `http_username` / `http_password` for Flexiva).

```powershell
python main.py
```

Open **http://localhost:8080**.

If port 8080 is already in use:

```powershell
python main.py --port 8090
```

## Nautel SNMP checklist

1. Enable SNMP (SNMPv2c is enough)
2. Set a read community and match it in `transmitters.yaml`
3. Allow UDP **161** from the machine running this app
4. Confirm Host Watch Dog is ON if AUI/SNMP drops after idle periods
5. Prefer VPN or a secured site LAN — do not expose SNMP to the internet

## GatesAir Flexiva

Flexiva FAX units expose live datapoints at `http://{host}/json` (same feed as the web GUI). The dashboard polls that endpoint directly for forward/reflected power, VSWR, RF on, temperature, and fault bits. Credentials (`http_username` / `http_password`, e.g. `gates` / `gates`) are stored for GUI login compatibility; read polling does not consume a Flexiva login slot.

## Config

| Field | Description |
|-------|-------------|
| `id` | Stable ID used in URLs and history |
| `name` | Display name |
| `model` | `vs300`, `vx`, `aat`, `flexiva`, or `crown` |
| `host` | Transmitter IP |
| `snmp_community` | Nautel read community |
| `snmp_port` | Default `161` |
| `http_port` | Flexiva HTTP port (default `80`) |
| `http_username` / `http_password` | Flexiva GUI credentials |
| `location` | Optional site/call label |

Global options in the same YAML: `poll_interval_seconds`, `history_retention_days`, `history_min_interval_seconds`, `http_host`, `http_port`.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service health |
| GET | `/api/transmitters` | All TX states + summary |
| GET | `/api/transmitters/{id}` | One TX |
| GET | `/api/transmitters/{id}/history?range=1h\|24h\|7d\|30d` | History points |
| GET | `/api/transmitters/{id}/history.csv?range=...` | CSV export for one TX |
| GET | `/api/history.csv?range=...` | CSV export for fleet |
| POST | `/api/poll` | Poll all now |
| POST | `/api/transmitters/{id}/poll` | Poll one now |
| GET | `/api/history/stats` | SQLite stats |
| GET | `/api/alerts` | Active alert state |
| POST | `/api/alerts/test` | Send a test email (requires SMTP config) |

## Alerts

Edit the `alerts:` block in `config/transmitters.yaml`:

- Dashboard banner/toasts work with no SMTP setup
- Set `email_enabled: true` plus SMTP fields to receive email
- Unconfigured hosts (blank `host`) are skipped when `skip_unconfigured: true`
- Defaults: alert after 3 failed polls, RF not ON, active TX alarm bits, VSWR ≥ 1.5, heatsink ≥ 70 °C
- Per-TX overrides: add an `alerts:` map under a transmitter. Explicit `null` disables that threshold for that TX only.

## MIB reference (Nautel)

Vendor MIB text is under `mibs/`:

- `NAUTEL-VS_SW_5.2-MIB.txt` — VS300 controller meters/alarms
- `NAUTEL-VX-7.1.0-MIB.txt` — VX controller meters/alarms (shared tree for VX2 / VX2.5)

Curated OIDs live in `nautel_monitor/oids.py`. Meter integers use Nautel’s Tenths/Hundredths/Thousandths scaling; `-2147483648` is treated as N/A.

## Notes

- v1 is **read-only** (no RF on/off writes)
- Uses a stdlib SNMPv2c client for Nautel and stdlib HTTP for Flexiva
