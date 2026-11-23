"""FastAPI application for the ASMG TX dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .alerts import AlertEngine
from .config import (
    config_to_dict,
    load_config,
    merge_secrets,
    save_config,
    validate_config_dict,
)
from .controls import (
    ControlError,
    controls_status,
    send_control,
    supported_actions_for,
    tx_controls_enabled,
)
from .history import HistoryStore
from .paths import data_dir, resolve_config_path, static_dir
from .poller import FleetPoller
from .stl_poller import StlPoller


def create_app(config_path: str | Path | None = None) -> FastAPI:
    resolved = resolve_config_path(str(config_path) if config_path else None)
    config = load_config(resolved)
    data = data_dir()
    static = static_dir()
    history = HistoryStore(
        data / "history.sqlite",
        retention_days=config.history_retention_days,
        min_interval=config.history_min_interval_seconds,
    )
    alerts = AlertEngine(config.alerts, data / "alert_state.json")
    poller = FleetPoller(config, history, alerts=alerts)
    stl_poller = StlPoller(config, history, alerts=alerts)

    app = FastAPI(title="ASMG TX Dashboard", version=__version__)
    app.state.poller = poller
    app.state.stl_poller = stl_poller
    app.state.history = history
    app.state.alerts = alerts
    app.state.config = config
    app.state.config_path = resolved

    @app.on_event("startup")
    def _startup() -> None:
        poller.start()
        stl_poller.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        poller.stop()
        stl_poller.stop()

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "version": __version__,
            "transmitters": len(poller.config.transmitters),
            "stl_devices": len(stl_poller.config.stl_devices),
            "poll_interval_seconds": poller.config.poll_interval_seconds,
            "alerts": alerts.status(),
            "controls": controls_status(poller.config),
        }

    @app.get("/api/transmitters")
    def list_transmitters() -> dict:
        readings = poller.get_all()
        return {
            "transmitters": [r.to_dict() for r in readings],
            "summary": _summary(readings),
            "alerts": alerts.status(),
        }

    @app.get("/api/transmitters/{tx_id}")
    def get_transmitter(tx_id: str) -> dict:
        reading = poller.get_one(tx_id)
        if reading is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        return reading.to_dict()

    @app.get("/api/transmitters/{tx_id}/history")
    def transmitter_history(
        tx_id: str,
        range: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    ) -> dict:
        if poller.get_one(tx_id) is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        hours = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}[range]
        points = history.query(tx_id, hours=hours)
        return {"tx_id": tx_id, "range": range, "points": points}

    @app.get("/api/transmitters/{tx_id}/history.csv")
    def transmitter_history_csv(
        tx_id: str,
        range: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    ) -> Response:
        if poller.get_one(tx_id) is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        hours = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}[range]
        csv_text = history.export_csv(tx_id=tx_id, hours=hours)
        filename = f"{tx_id}-history-{range}.csv"
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/history.csv")
    def fleet_history_csv(
        range: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    ) -> Response:
        hours = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}[range]
        csv_text = history.export_csv(tx_id=None, hours=hours)
        filename = f"asmg-fleet-history-{range}.csv"
        return Response(
            content=csv_text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/poll")
    def poll_now() -> dict:
        readings = poller.poll_all()
        return {
            "transmitters": [r.to_dict() for r in readings],
            "summary": _summary(readings),
            "alerts": alerts.status(),
        }

    @app.post("/api/transmitters/{tx_id}/poll")
    def poll_one(tx_id: str) -> dict:
        reading = poller.poll_and_store(tx_id)
        if reading is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        return reading.to_dict()

    @app.get("/api/controls/status")
    def get_controls_status() -> dict:
        return controls_status(poller.config)

    @app.post("/api/transmitters/{tx_id}/control")
    async def control_transmitter(tx_id: str, request: Request) -> dict:
        body = await _json_body(request)
        action = str(body.get("action") or "").strip().lower()
        password = str(body.get("password") or "")
        tx = next((t for t in poller.config.transmitters if t.id == tx_id), None)
        if tx is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        if not tx_controls_enabled(poller.config, tx):
            raise HTTPException(
                status_code=403,
                detail="RF controls are disabled. Enable controls in Settings first.",
            )
        reading = poller.get_one(tx_id)
        try:
            message = send_control(
                poller.config,
                tx,
                action,
                password=password,
                reading=reading,
            )
        except ControlError as error:
            status = 401 if "password" in str(error).lower() else 400
            if "disabled" in str(error).lower():
                status = 403
            raise HTTPException(status_code=status, detail=str(error)) from error

        refreshed = poller.poll_and_store(tx_id)
        return {
            "ok": True,
            "message": message,
            "action": action,
            "tx_id": tx_id,
            "supported_actions": supported_actions_for(tx),
            "reading": refreshed.to_dict() if refreshed else None,
        }

    @app.get("/api/alerts")
    def get_alerts() -> dict:
        return alerts.status()

    @app.post("/api/alerts/test")
    def test_alert() -> dict:
        reading = next((r for r in poller.get_all() if r.host), None)
        try:
            alerts.send_test(reading)
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"ok": True, "alerts": alerts.status()}

    @app.post("/api/alerts/ack")
    async def ack_alert(request: Request) -> dict:
        body = await _json_body(request)
        key = str(body.get("key") or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="Missing alert key")
        try:
            return {"ok": True, "alerts": alerts.acknowledge(key)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/alerts/snooze")
    async def snooze_alert(request: Request) -> dict:
        body = await _json_body(request)
        key = str(body.get("key") or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="Missing alert key")
        minutes = int(body.get("minutes") or 60)
        minutes = max(1, min(minutes, 24 * 60))
        try:
            return {"ok": True, "alerts": alerts.snooze(key, minutes=minutes)}
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/config")
    def get_config() -> dict:
        return config_to_dict(poller.config, mask_secrets=True)

    @app.put("/api/config")
    async def put_config(request: Request) -> dict:
        body = await _json_body(request)
        try:
            incoming = validate_config_dict(body)
            merged = merge_secrets(incoming, poller.config)
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        try:
            save_config(app.state.config_path, merged)
        except OSError as error:
            raise HTTPException(
                status_code=500, detail=f"Could not write config: {error}"
            ) from error

        poller.reload_config(merged)
        stl_poller.reload_config(merged)
        app.state.config = merged
        return {
            "ok": True,
            "config": config_to_dict(merged, mask_secrets=True),
            "summary": _summary(poller.get_all()),
            "stl_summary": _stl_summary(stl_poller.get_all()),
        }

    @app.get("/api/history/stats")
    def history_stats() -> dict:
        return history.stats()

    @app.get("/api/stl")
    def list_stl() -> dict:
        readings = stl_poller.get_all()
        return {
            "devices": [reading.to_dict() for reading in readings],
            "summary": _stl_summary(readings),
            "alerts": alerts.status(),
        }

    @app.get("/api/stl/{stl_id}")
    def get_stl(stl_id: str) -> dict:
        reading = stl_poller.get_one(stl_id)
        if reading is None:
            raise HTTPException(status_code=404, detail="STL device not found")
        return reading.to_dict()

    @app.get("/api/stl/{stl_id}/history")
    def stl_history(
        stl_id: str,
        range: str = Query("24h", pattern="^(1h|24h|7d|30d)$"),
    ) -> dict:
        if stl_poller.get_one(stl_id) is None:
            raise HTTPException(status_code=404, detail="STL device not found")
        hours = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}[range]
        points = history.query_stl(stl_id, hours=hours)
        return {"stl_id": stl_id, "range": range, "points": points}

    @app.post("/api/stl/poll")
    def poll_stl_now() -> dict:
        readings = stl_poller.poll_all()
        return {
            "devices": [reading.to_dict() for reading in readings],
            "summary": _stl_summary(readings),
            "alerts": alerts.status(),
        }

    @app.post("/api/stl/{stl_id}/poll")
    def poll_stl_one(stl_id: str) -> dict:
        reading = stl_poller.poll_and_store(stl_id)
        if reading is None:
            raise HTTPException(status_code=404, detail="STL device not found")
        return reading.to_dict()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/stl")
    def stl_page() -> FileResponse:
        return FileResponse(static / "stl.html")

    @app.get("/stl/{stl_id}")
    def stl_detail_page(stl_id: str) -> FileResponse:
        if stl_poller.get_one(stl_id) is None:
            raise HTTPException(status_code=404, detail="STL device not found")
        return FileResponse(static / "stl.html")

    @app.get("/wall")
    def wall_page() -> FileResponse:
        return FileResponse(static / "wall.html")

    @app.get("/settings")
    def settings_page() -> FileResponse:
        return FileResponse(static / "settings.html")

    @app.get("/tx/{tx_id}")
    def detail_page(tx_id: str) -> FileResponse:
        if poller.get_one(tx_id) is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        return FileResponse(static / "detail.html")

    app.mount("/static", StaticFiles(directory=str(static)), name="static")
    return app


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from error
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    return body


def _stl_summary(readings: list) -> dict:
    counts = {"online": 0, "degraded": 0, "offline": 0}
    alarms = 0
    for reading in readings:
        counts[reading.status] = counts.get(reading.status, 0) + 1
        alarms += reading.active_alarm_count
    return {
        "total": len(readings),
        "online": counts["online"],
        "degraded": counts["degraded"],
        "offline": counts["offline"],
        "active_alarms": alarms,
    }


def _summary(readings: list) -> dict:
    counts = {"online": 0, "degraded": 0, "offline": 0}
    alarms = 0
    for reading in readings:
        counts[reading.status] = counts.get(reading.status, 0) + 1
        alarms += reading.active_alarm_count
    return {
        "total": len(readings),
        "online": counts["online"],
        "degraded": counts["degraded"],
        "offline": counts["offline"],
        "active_alarms": alarms,
    }
