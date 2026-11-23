"""SQLite-backed historical reading storage."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import TransmitterReading

READING_COLUMNS = (
    "timestamp",
    "tx_id",
    "host",
    "name",
    "model",
    "location",
    "status",
    "fwd_pwr_w",
    "rfl_pwr_w",
    "vswr",
    "heatsink_temp_c",
    "pa_volts_v",
    "pa_current_1_a",
    "ipa_current_a",
    "plus48_v",
    "plus15_v",
    "minus15_v",
    "plus5_v",
    "fan1_rpm",
    "fan2_rpm",
    "rf_state",
    "local_remote",
    "active_alarms",
    "error",
    "meters_json",
)

SCALAR_KEYS = frozenset(
    {
        "fwd_pwr_w",
        "rfl_pwr_w",
        "vswr",
        "heatsink_temp_c",
        "pa_volts_v",
        "pa_current_1_a",
        "ipa_current_a",
        "plus48_v",
        "plus15_v",
        "minus15_v",
        "plus5_v",
        "fan1_rpm",
        "fan2_rpm",
        "rf_state",
        "local_remote",
        "active_alarms",
    }
)


def _meters_payload(reading: TransmitterReading) -> str:
    payload: dict[str, float | int] = {}
    for meter in reading.meters:
        if meter.value is None:
            continue
        if isinstance(meter.value, bool):
            continue
        if isinstance(meter.value, (int, float)):
            payload[meter.key] = meter.value
    return json.dumps(payload, separators=(",", ":"))


def _row_to_point(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    point = dict(row)
    extra_raw = point.pop("meters_json", None) or "{}"
    try:
        extra = json.loads(extra_raw) if isinstance(extra_raw, str) else {}
    except json.JSONDecodeError:
        extra = {}
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key in SCALAR_KEYS and point.get(key) is not None:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                point[key] = value
    return point


class HistoryStore:
    def __init__(
        self,
        db_path: str | Path,
        retention_days: int = 90,
        min_interval: int = 60,
    ) -> None:
        self.db_path = Path(db_path)
        self.retention_days = retention_days
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_save: dict[str, datetime] = {}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    tx_id TEXT NOT NULL,
                    host TEXT,
                    name TEXT,
                    model TEXT,
                    location TEXT,
                    status TEXT,
                    fwd_pwr_w REAL,
                    rfl_pwr_w REAL,
                    vswr REAL,
                    heatsink_temp_c REAL,
                    pa_volts_v REAL,
                    pa_current_1_a REAL,
                    ipa_current_a REAL,
                    plus48_v REAL,
                    plus15_v REAL,
                    minus15_v REAL,
                    plus5_v REAL,
                    fan1_rpm INTEGER,
                    fan2_rpm INTEGER,
                    rf_state INTEGER,
                    local_remote INTEGER,
                    active_alarms INTEGER,
                    error TEXT
                )
                """
            )
            self._ensure_columns(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_tx_ts "
                "ON readings(tx_id, timestamp)"
            )

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row[1] for row in conn.execute("PRAGMA table_info(readings)").fetchall()
        }
        wanted = {
            "pa_volts_v": "REAL",
            "pa_current_1_a": "REAL",
            "ipa_current_a": "REAL",
            "plus48_v": "REAL",
            "plus15_v": "REAL",
            "minus15_v": "REAL",
            "plus5_v": "REAL",
            "fan1_rpm": "INTEGER",
            "fan2_rpm": "INTEGER",
            "meters_json": "TEXT",
        }
        for name, col_type in wanted.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE readings ADD COLUMN {name} {col_type}")

    def maybe_save(self, reading: TransmitterReading) -> bool:
        last = self._last_save.get(reading.tx_id)
        if last is not None:
            elapsed = (reading.timestamp - last).total_seconds()
            if elapsed < self.min_interval:
                return False
        self.save(reading)
        self._last_save[reading.tx_id] = reading.timestamp
        return True

    def save(self, reading: TransmitterReading) -> None:
        row = (
            reading.timestamp.isoformat(),
            reading.tx_id,
            reading.host,
            reading.name,
            reading.model,
            reading.location,
            reading.status,
            reading.fwd_pwr_w,
            reading.rfl_pwr_w,
            reading.vswr,
            reading.heatsink_temp_c,
            reading.pa_volts_v,
            reading.pa_current_1_a,
            reading.ipa_current_a,
            reading.plus48_v,
            reading.plus15_v,
            reading.minus15_v,
            reading.plus5_v,
            reading.fan1_rpm,
            reading.fan2_rpm,
            reading.rf_state,
            reading.local_remote,
            reading.active_alarm_count,
            reading.error,
            _meters_payload(reading),
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO readings ({", ".join(READING_COLUMNS)})
                VALUES ({", ".join("?" for _ in READING_COLUMNS)})
                """,
                row,
            )
            self._purge_old(conn)

    def _purge_old(self, conn: sqlite3.Connection) -> None:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        ).isoformat()
        conn.execute("DELETE FROM readings WHERE timestamp < ?", (cutoff,))

    def query(
        self,
        tx_id: str,
        hours: float = 24,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {", ".join(READING_COLUMNS)}
                FROM readings
                WHERE tx_id = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (tx_id, start.isoformat(), end.isoformat()),
            ).fetchall()

        if len(rows) > limit:
            rows = self._downsample(rows, limit)
        return [_row_to_point(row) for row in rows]

    @staticmethod
    def _downsample(rows: list[sqlite3.Row], limit: int) -> list[sqlite3.Row]:
        if limit <= 0 or len(rows) <= limit:
            return rows
        if limit == 1:
            return [rows[-1]]
        last = len(rows) - 1
        indices = [round(i * last / (limit - 1)) for i in range(limit)]
        return [rows[i] for i in indices]

    def stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            oldest = conn.execute(
                "SELECT MIN(timestamp) FROM readings"
            ).fetchone()[0]
            newest = conn.execute(
                "SELECT MAX(timestamp) FROM readings"
            ).fetchone()[0]
        return {
            "count": count,
            "oldest": oldest,
            "newest": newest,
            "retention_days": self.retention_days,
            "min_interval_seconds": self.min_interval,
        }

    def export_csv(
        self,
        tx_id: str | None = None,
        hours: float = 24,
        limit: int = 50000,
    ) -> str:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=hours)
        with self._lock, self._connect() as conn:
            if tx_id:
                rows = conn.execute(
                    f"""
                    SELECT {", ".join(READING_COLUMNS)} FROM (
                        SELECT {", ".join(READING_COLUMNS)}
                        FROM readings
                        WHERE tx_id = ? AND timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    ) AS newest
                    ORDER BY timestamp ASC
                    """,
                    (tx_id, start.isoformat(), end.isoformat(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT {", ".join(READING_COLUMNS)} FROM (
                        SELECT {", ".join(READING_COLUMNS)}
                        FROM readings
                        WHERE timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    ) AS newest
                    ORDER BY timestamp ASC
                    """,
                    (start.isoformat(), end.isoformat(), limit),
                ).fetchall()

        points = [_row_to_point(row) for row in rows]
        # Flatten meters_json extras into CSV columns (union of keys).
        fieldnames = list(READING_COLUMNS)
        extra_keys: list[str] = []
        for point in points:
            for key in point:
                if key not in fieldnames and key not in extra_keys:
                    extra_keys.append(key)
        fieldnames = [c for c in fieldnames if c != "meters_json"] + sorted(extra_keys)

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for point in points:
            row = {key: point.get(key) for key in fieldnames}
            writer.writerow(row)
        return output.getvalue()
