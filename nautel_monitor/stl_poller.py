"""Background poller for STL links. Separate from the transmitter fleet."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .alerts import AlertEngine
from .history import HistoryStore
from .models import AppConfig, StlDeviceConfig, StlReading, utc_now
from .stl_client import poll_stl

logger = logging.getLogger(__name__)


class StlPoller:
    def __init__(
        self,
        config: AppConfig,
        history: HistoryStore,
        alerts: AlertEngine | None = None,
        on_update: Callable[[], None] | None = None,
    ) -> None:
        self.config = config
        self.history = history
        self.alerts = alerts
        self.on_update = on_update
        self._lock = threading.Lock()
        self._latest: dict[str, StlReading] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.alerts is not None:
            self.alerts.prune_stl({device.id for device in self.config.stl_devices})
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="asmg-stl-poller", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def reload_config(self, new_config: AppConfig) -> None:
        keep_ids = {device.id for device in new_config.stl_devices}
        with self._lock:
            self.config = new_config
            stale = [stl_id for stl_id in self._latest if stl_id not in keep_ids]
            for stl_id in stale:
                self._latest.pop(stl_id, None)
            by_id = {device.id: device for device in new_config.stl_devices}
            for stl_id, reading in list(self._latest.items()):
                device = by_id.get(stl_id)
                if device is None:
                    continue
                if reading.host != device.host:
                    self._latest.pop(stl_id, None)
                    continue
                reading.name = device.name
                reading.location = device.location
                reading.model = device.model
                reading.related_tx_id = device.related_tx_id
        if self.alerts is not None:
            self.alerts.config = new_config.alerts
            self.alerts.prune_stl(keep_ids)
        self.history.retention_days = new_config.history_retention_days
        self.history.min_interval = new_config.history_min_interval_seconds

    def get_all(self) -> list[StlReading]:
        with self._lock:
            by_id = dict(self._latest)
            devices = list(self.config.stl_devices)
        results: list[StlReading] = []
        for device in devices:
            if device.id in by_id:
                results.append(by_id[device.id])
            else:
                results.append(self._placeholder(device))
        return results

    def get_one(self, stl_id: str) -> StlReading | None:
        with self._lock:
            if stl_id in self._latest:
                return self._latest[stl_id]
            devices = list(self.config.stl_devices)
        for device in devices:
            if device.id == stl_id:
                return self._placeholder(device)
        return None

    def poll_all(self) -> list[StlReading]:
        devices = list(self.config.stl_devices)
        readings = [self.poll_one(device) for device in devices]
        with self._lock:
            for reading in readings:
                self._latest[reading.stl_id] = reading
        if self.on_update:
            self.on_update()
        return readings

    def poll_and_store(self, stl_id: str) -> StlReading | None:
        device = next((item for item in self.config.stl_devices if item.id == stl_id), None)
        if device is None:
            return None
        reading = self.poll_one(device)
        with self._lock:
            self._latest[reading.stl_id] = reading
        return reading

    def poll_one(self, device: StlDeviceConfig) -> StlReading:
        reading = poll_stl(
            device,
            timeout=self.config.snmp_timeout_seconds,
            retries=self.config.snmp_retries,
        )
        self.history.maybe_save_stl(reading)
        if self.alerts is not None:
            self.alerts.on_stl_reading(
                reading,
                configured=device.configured,
                overrides=device.alert_overrides,
            )
        return reading

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.poll_all()
            except Exception:
                logger.exception("STL poll cycle failed")
            elapsed = time.monotonic() - started
            wait = max(1.0, self.config.poll_interval_seconds - elapsed)
            self._stop.wait(wait)

    @staticmethod
    def _placeholder(device: StlDeviceConfig) -> StlReading:
        return StlReading(
            stl_id=device.id,
            timestamp=utc_now(),
            reachable=False,
            status="offline",
            host=device.host,
            name=device.name,
            model=device.model,
            location=device.location,
            link_state="unknown",
            link_label="Waiting for first poll" if device.configured else "Not configured",
            error="Waiting for first poll" if device.configured else "Host IP not configured",
            related_tx_id=device.related_tx_id,
        )
