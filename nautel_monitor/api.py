"""FastAPI application for the ASMG TX dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .alerts import AlertEngine
from .config import load_config
from .history import HistoryStore
from .paths import data_dir, resolve_config_path, static_dir
from .poller import FleetPoller


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

    app = FastAPI(title="ASMG TX Dashboard", version="1.3.0")
    app.state.poller = poller
    app.state.history = history
    app.state.alerts = alerts
    app.state.config = config
    app.state.config_path = resolved

    @app.on_event("startup")
    def _startup() -> None:
        poller.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        poller.stop()

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "transmitters": len(config.transmitters),
            "poll_interval_seconds": config.poll_interval_seconds,
            "alerts": alerts.status(),
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

    @app.get("/api/history/stats")
    def history_stats() -> dict:
        return history.stats()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/tx/{tx_id}")
    def detail_page(tx_id: str) -> FileResponse:
        if poller.get_one(tx_id) is None:
            raise HTTPException(status_code=404, detail="Transmitter not found")
        return FileResponse(static / "detail.html")

    app.mount("/static", StaticFiles(directory=str(static)), name="static")
    return app


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
