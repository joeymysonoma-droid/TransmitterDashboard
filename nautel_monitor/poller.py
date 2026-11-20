"""Fleet poller for Nautel (SNMP) and GatesAir Flexiva (HTTP) transmitters."""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .aat_client import poll_aat
from .alerts import AlertEngine
from .crown_client import poll_crown
from .flexiva_client import poll_flexiva
from .history import HistoryStore
from .models import (
    AlarmState,
    AppConfig,
    MeterReading,
    TransmitterConfig,
    TransmitterReading,
    utc_now,
)
from .oids import profile_for
from .snmp_client import SnmpError, snmp_get

logger = logging.getLogger(__name__)
OID_CHUNK_SIZE = 16


class FleetPoller:
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
        self._latest: dict[str, TransmitterReading] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="asmg-tx-poller", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def get_all(self) -> list[TransmitterReading]:
        with self._lock:
            by_id = {r.tx_id: r for r in self._latest.values()}
        results: list[TransmitterReading] = []
        for tx in self.config.transmitters:
            if tx.id in by_id:
                results.append(by_id[tx.id])
            else:
                results.append(self._placeholder(tx))
        return results

    def get_one(self, tx_id: str) -> TransmitterReading | None:
        with self._lock:
            if tx_id in self._latest:
                return self._latest[tx_id]
        for tx in self.config.transmitters:
            if tx.id == tx_id:
                return self._placeholder(tx)
        return None

    def poll_all(self) -> list[TransmitterReading]:
        readings = [self.poll_one(tx) for tx in self.config.transmitters]
        with self._lock:
            for reading in readings:
                self._latest[reading.tx_id] = reading
        if self.on_update:
            self.on_update()
        return readings

    def poll_and_store(self, tx_id: str) -> TransmitterReading | None:
        tx = next((t for t in self.config.transmitters if t.id == tx_id), None)
        if tx is None:
            return None
        reading = self.poll_one(tx)
        with self._lock:
            self._latest[reading.tx_id] = reading
        return reading

    def poll_one(self, tx: TransmitterConfig) -> TransmitterReading:
        if not tx.configured:
            reading = TransmitterReading(
                tx_id=tx.id,
                timestamp=utc_now(),
                status="offline",
                host=tx.host,
                name=tx.name,
                model=tx.model,
                location=tx.location,
                error="Host IP not configured",
            )
            self.history.maybe_save(reading)
            if self.alerts:
                self.alerts.on_reading(
                    reading, configured=False, overrides=tx.alert_overrides
                )
            return reading

        if tx.is_flexiva:
            reading = poll_flexiva(
                tx, timeout=self.config.snmp_timeout_seconds
            )
            self.history.maybe_save(reading)
            if self.alerts:
                self.alerts.on_reading(
                    reading, configured=True, overrides=tx.alert_overrides
                )
            return reading

        if tx.is_aat:
            reading = poll_aat(tx, timeout=self.config.snmp_timeout_seconds)
            self.history.maybe_save(reading)
            if self.alerts:
                self.alerts.on_reading(
                    reading, configured=True, overrides=tx.alert_overrides
                )
            return reading

        if tx.is_crown:
            reading = poll_crown(tx, timeout=max(8.0, self.config.snmp_timeout_seconds))
            self.history.maybe_save(reading)
            if self.alerts:
                self.alerts.on_reading(
                    reading, configured=True, overrides=tx.alert_overrides
                )
            return reading

        try:
            meters, alarms = profile_for(tx.model)
        except KeyError as error:
            reading = TransmitterReading(
                tx_id=tx.id,
                timestamp=utc_now(),
                status="offline",
                host=tx.host,
                name=tx.name,
                model=tx.model,
                location=tx.location,
                error=str(error),
            )
            self.history.maybe_save(reading)
            if self.alerts:
                self.alerts.on_reading(
                    reading, configured=True, overrides=tx.alert_overrides
                )
            return reading

        oids = [m.oid for m in meters] + [a.oid for a in alarms]
        try:
            raw = self._snmp_get_chunked(tx, oids)
        except SnmpError as error:
            logger.warning("SNMP failed for %s (%s): %s", tx.id, tx.host, error)
            reading = TransmitterReading(
                tx_id=tx.id,
                timestamp=utc_now(),
                status="offline",
                host=tx.host,
                name=tx.name,
                model=tx.model,
                location=tx.location,
                error=str(error),
                oid_total=len(oids),
            )
            self.history.maybe_save(reading)
            if self.alerts:
                self.alerts.on_reading(
                    reading, configured=True, overrides=tx.alert_overrides
                )
            return reading

        values: dict[str, float | int | None] = {}
        meter_readings: list[MeterReading] = []
        oid_ok = 0
        for meter in meters:
            raw_val = raw.get(meter.oid)
            value: float | int | None = None
            if isinstance(raw_val, int):
                try:
                    value = meter.convert(raw_val)
                    oid_ok += 1
                except Exception:
                    value = None
            elif raw_val is not None:
                # Device answered (e.g. VX "Resource does not exist") — not a poll failure.
                oid_ok += 1
            values[meter.key] = value
            meter_readings.append(
                MeterReading(
                    key=meter.key,
                    label=meter.label,
                    value=value,
                    unit=meter.unit,
                    category=meter.category,
                )
            )

        alarm_states: list[AlarmState] = []
        for alarm in alarms:
            raw_val = raw.get(alarm.oid)
            active = isinstance(raw_val, int) and raw_val == 1
            if isinstance(raw_val, int):
                oid_ok += 1
            elif raw_val is not None:
                oid_ok += 1
            alarm_states.append(
                AlarmState(key=alarm.key, label=alarm.label, active=active)
            )

        oid_total = len(oids)
        if oid_ok == 0:
            status = "offline"
        elif oid_ok < oid_total:
            status = "degraded"
        else:
            status = "online"

        reading = TransmitterReading(
            tx_id=tx.id,
            timestamp=utc_now(),
            status=status,
            host=tx.host,
            name=tx.name,
            model=tx.model,
            location=tx.location,
            fwd_pwr_w=_as_float(values.get("fwd_pwr_w")),
            rfl_pwr_w=_as_float(values.get("rfl_pwr_w")),
            vswr=_as_float(values.get("vswr")),
            heatsink_temp_c=_as_float(values.get("heatsink_temp_c")),
            pa_volts_v=_as_float(values.get("pa_volts_v")),
            pa_current_1_a=_as_float(values.get("pa_current_1_a")),
            ipa_current_a=_as_float(values.get("ipa_current_a")),
            plus48_v=_as_float(values.get("plus48_v")),
            plus15_v=_as_float(values.get("plus15_v")),
            minus15_v=_as_float(values.get("minus15_v")),
            plus5_v=_as_float(values.get("plus5_v")),
            fan1_rpm=_as_int(values.get("fan1_rpm")),
            fan2_rpm=_as_int(values.get("fan2_rpm")),
            rf_state=_as_int(values.get("rf_state")),
            local_remote=_as_int(values.get("local_remote")),
            meters=meter_readings,
            alarms=alarm_states,
            oid_ok=oid_ok,
            oid_total=oid_total,
        )
        self.history.maybe_save(reading)
        if self.alerts:
            self.alerts.on_reading(
                reading, configured=True, overrides=tx.alert_overrides
            )
        return reading

    def _snmp_get_chunked(
        self, tx: TransmitterConfig, oids: list[str]
    ) -> dict[str, int | str | None]:
        merged: dict[str, int | str | None] = {}
        for start in range(0, len(oids), OID_CHUNK_SIZE):
            chunk = oids[start : start + OID_CHUNK_SIZE]
            merged.update(
                snmp_get(
                    host=tx.host,
                    community=tx.snmp_community,
                    oids=chunk,
                    port=tx.snmp_port,
                    timeout=self.config.snmp_timeout_seconds,
                    retries=self.config.snmp_retries,
                )
            )
        return merged

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.poll_all()
            except Exception:
                logger.exception("Poll cycle failed")
            elapsed = time.monotonic() - started
            wait = max(1.0, self.config.poll_interval_seconds - elapsed)
            self._stop.wait(wait)

    @staticmethod
    def _placeholder(tx: TransmitterConfig) -> TransmitterReading:
        return TransmitterReading(
            tx_id=tx.id,
            timestamp=utc_now(),
            status="offline",
            host=tx.host,
            name=tx.name,
            model=tx.model,
            location=tx.location,
            error="Waiting for first poll" if tx.configured else "Host IP not configured",
        )


def _as_float(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _as_int(value: float | int | None) -> int | None:
    if value is None:
        return None
    return int(value)
