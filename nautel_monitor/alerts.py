"""Alert engine for offline / RF-off / TX alarms / thresholds."""

from __future__ import annotations

import json
import logging
import smtplib
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from .models import AlertConfig, TransmitterReading

logger = logging.getLogger(__name__)

_BOOL_OVERRIDE_KEYS = (
    "on_unreachable",
    "on_rf_off",
    "on_tx_alarms",
    "skip_unconfigured",
)
_FLOAT_OVERRIDE_KEYS = ("vswr", "reflected_w", "heatsink_c", "forward_min_w")
_INT_OVERRIDE_KEYS = ("unreachable_polls", "cooldown_minutes")


def merge_alert_config(
    base: AlertConfig, overrides: dict[str, Any] | None
) -> AlertConfig:
    """Apply per-TX overrides. Keys present in overrides win (including null)."""
    if not overrides:
        return base
    updates: dict[str, Any] = {}
    for key in _BOOL_OVERRIDE_KEYS:
        if key in overrides:
            updates[key] = bool(overrides[key])
    for key in _INT_OVERRIDE_KEYS:
        if key in overrides and overrides[key] is not None:
            updates[key] = int(overrides[key])
    for key in _FLOAT_OVERRIDE_KEYS:
        if key in overrides:
            value = overrides[key]
            updates[key] = None if value is None or value == "" else float(value)
    return replace(base, **updates) if updates else base


def email_ready(config: AlertConfig) -> tuple[bool, str]:
    if not config.email_enabled:
        return False, "Email alerts are off. Set alerts.email_enabled in transmitters.yaml."
    if not config.smtp_host.strip():
        return False, "Set alerts.smtp_host before email alerts can send."
    if not config.email_to:
        return False, "Set alerts.email_to before email alerts can send."
    if not (config.email_from.strip() or config.smtp_username.strip()):
        return False, "Set alerts.email_from or alerts.smtp_username."
    return True, ""


class AlertEngine:
    def __init__(
        self,
        config: AlertConfig,
        state_path: str | Path,
        *,
        async_send: bool = True,
    ) -> None:
        self.config = config
        self.state_path = Path(state_path)
        self.async_send = async_send
        self._lock = threading.Lock()
        self._active: dict[str, str] = {}
        self._acked: set[str] = set()
        self._snoozed_until: dict[str, str] = {}
        self._last_sent: dict[str, str] = {}
        self._unreachable_streak: dict[str, int] = {}
        self._last_error = ""
        self._last_sent_at: str | None = None
        self._recent_events: list[dict[str, str]] = []
        self._load()

    def status(self) -> dict[str, object]:
        ready, reason = email_ready(self.config)
        now = datetime.now(timezone.utc)
        with self._lock:
            self._prune_snoozes_locked(now)
            active = []
            for key, message in sorted(self._active.items()):
                snooze_until = self._snoozed_until.get(key)
                snoozed = bool(snooze_until and _parse_time(snooze_until) and _parse_time(snooze_until) > now)
                acked = key in self._acked
                if acked or snoozed:
                    continue
                active.append(
                    {
                        "key": key,
                        "message": message,
                        "acked": False,
                        "snoozed": False,
                        "snoozed_until": None,
                    }
                )
            hidden = []
            for key, message in sorted(self._active.items()):
                snooze_until = self._snoozed_until.get(key)
                snooze_dt = _parse_time(snooze_until)
                snoozed = bool(snooze_dt and snooze_dt > now)
                acked = key in self._acked
                if not (acked or snoozed):
                    continue
                hidden.append(
                    {
                        "key": key,
                        "message": message,
                        "acked": acked,
                        "snoozed": snoozed,
                        "snoozed_until": snooze_until if snoozed else None,
                    }
                )
            return {
                "email_enabled": self.config.email_enabled,
                "email_ready": ready,
                "email_reason": "" if ready else reason,
                "active": active,
                "active_count": len(active),
                "suppressed": hidden,
                "acked": sorted(self._acked),
                "snoozed_until": dict(self._snoozed_until),
                "last_error": self._last_error,
                "last_sent_at": self._last_sent_at,
                "recent_events": list(self._recent_events[-20:]),
            }

    def acknowledge(self, key: str) -> dict[str, object]:
        with self._lock:
            if key not in self._active:
                raise KeyError(f"Alert not active: {key}")
            self._acked.add(key)
            self._push_event_locked("acked", self._active.get(key, key))
            self._save_locked()
        return self.status()

    def snooze(self, key: str, minutes: int = 60) -> dict[str, object]:
        minutes = max(1, int(minutes))
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        with self._lock:
            if key not in self._active:
                raise KeyError(f"Alert not active: {key}")
            self._snoozed_until[key] = until.isoformat()
            self._push_event_locked(
                "snoozed",
                f"{self._active.get(key, key)} (until {until.isoformat()})",
            )
            self._save_locked()
        return self.status()

    def on_reading(
        self,
        reading: TransmitterReading,
        *,
        configured: bool,
        overrides: dict[str, Any] | None = None,
    ) -> None:
        cfg = merge_alert_config(self.config, overrides)
        if cfg.skip_unconfigured and not configured:
            self._clear_tx(reading.tx_id)
            return

        conditions = self._conditions(reading, configured=configured, cfg=cfg)
        self._apply(reading.tx_id, conditions, reading)

    def send_test(self, reading: TransmitterReading | None = None) -> None:
        ready, reason = email_ready(self.config)
        if not ready:
            raise RuntimeError(reason)
        name = reading.name if reading else "ASMG fleet"
        host = reading.host if reading else ""
        body = [
            f"This is a test message from ASMG TX Dashboard for {name}.",
            f"Host: {host or 'n/a'}",
            "",
        ]
        if reading is not None:
            body.extend(reading.summary_lines())
        self._deliver(
            subject=f"[ASMG] Test email — {name}",
            body="\n".join(body),
            keys=(),
            sync=True,
        )

    def _conditions(
        self,
        reading: TransmitterReading,
        *,
        configured: bool,
        cfg: AlertConfig | None = None,
    ) -> dict[str, str]:
        cfg = cfg or self.config
        active: dict[str, str] = {}
        prefix = reading.tx_id

        if configured and reading.status == "offline":
            streak = self._unreachable_streak.get(reading.tx_id, 0) + 1
            self._unreachable_streak[reading.tx_id] = streak
            if cfg.on_unreachable and streak >= max(1, cfg.unreachable_polls):
                detail = reading.error or "SNMP unreachable"
                active[f"{prefix}:unreachable"] = (
                    f"{reading.name} unreachable for {streak} polls ({detail})"
                )
        else:
            self._unreachable_streak[reading.tx_id] = 0

        if reading.status == "offline":
            return active

        if cfg.on_rf_off and reading.rf_state is not None and reading.rf_state != 1:
            active[f"{prefix}:rf_off"] = (
                f"{reading.name} RF is {reading.rf_state_label}"
            )

        if cfg.on_tx_alarms:
            for alarm in reading.alarms:
                if alarm.active:
                    active[f"{prefix}:alarm:{alarm.key}"] = (
                        f"{reading.name}: {alarm.label}"
                    )

        if cfg.vswr is not None and reading.vswr is not None and reading.vswr >= cfg.vswr:
            active[f"{prefix}:vswr"] = (
                f"{reading.name} VSWR {reading.vswr:.3f} >= {cfg.vswr:.3f}"
            )

        if (
            cfg.reflected_w is not None
            and reading.rfl_pwr_w is not None
            and reading.rfl_pwr_w >= cfg.reflected_w
        ):
            active[f"{prefix}:reflected"] = (
                f"{reading.name} reflected {reading.rfl_pwr_w:.1f} W "
                f">= {cfg.reflected_w:.1f} W"
            )

        if (
            cfg.heatsink_c is not None
            and reading.heatsink_temp_c is not None
            and reading.heatsink_temp_c >= cfg.heatsink_c
        ):
            active[f"{prefix}:heatsink"] = (
                f"{reading.name} heatsink {reading.heatsink_temp_c:.1f} C "
                f">= {cfg.heatsink_c:.1f} C"
            )

        if (
            cfg.forward_min_w is not None
            and reading.rf_state == 1
            and reading.fwd_pwr_w is not None
            and reading.fwd_pwr_w < cfg.forward_min_w
        ):
            active[f"{prefix}:forward_low"] = (
                f"{reading.name} forward {reading.fwd_pwr_w:.1f} W "
                f"< {cfg.forward_min_w:.1f} W"
            )

        return active

    def _clear_tx(self, tx_id: str) -> None:
        prefix = f"{tx_id}:"
        with self._lock:
            stale = [key for key in self._active if key.startswith(prefix)]
            for key in stale:
                self._active.pop(key, None)
                self._last_sent.pop(key, None)
                self._acked.discard(key)
                self._snoozed_until.pop(key, None)
            self._unreachable_streak.pop(tx_id, None)
            if stale:
                self._save_locked()

    def _is_suppressed_locked(self, key: str, now: datetime) -> bool:
        if key in self._acked:
            return True
        until = _parse_time(self._snoozed_until.get(key))
        return bool(until and until > now)

    def _apply(
        self,
        tx_id: str,
        updates: dict[str, str],
        reading: TransmitterReading,
    ) -> None:
        ready, _reason = email_ready(self.config)
        now = datetime.now(timezone.utc)
        cooldown = timedelta(minutes=max(1, self.config.cooldown_minutes))
        prefix = f"{tx_id}:"
        new_alarms: list[tuple[str, str]] = []
        reminders: list[tuple[str, str]] = []
        recovered: list[str] = []

        with self._lock:
            self._prune_snoozes_locked(now)
            existing = [key for key in self._active if key.startswith(prefix)]
            for key in existing:
                if key not in updates:
                    self._active.pop(key, None)
                    self._last_sent.pop(key, None)
                    self._acked.discard(key)
                    self._snoozed_until.pop(key, None)
                    recovered.append(key)

            for key, message in updates.items():
                was_active = key in self._active
                self._active[key] = message
                suppressed = self._is_suppressed_locked(key, now)
                last = _parse_time(self._last_sent.get(key))
                if not was_active:
                    if not suppressed:
                        new_alarms.append((key, message))
                    self._push_event_locked("alert", message)
                elif not suppressed and (last is None or now - last >= cooldown):
                    reminders.append((key, message))

            for key in recovered:
                self._push_event_locked("recovered", key)
            self._save_locked()

        if new_alarms and ready:
            self._send_group("ALERT", reading, new_alarms)
        if reminders and ready:
            self._send_group("STILL IN ALARM", reading, reminders)
        if recovered and ready:
            self._send_recovery(reading, recovered)

    def _send_group(
        self,
        kind: str,
        reading: TransmitterReading,
        items: list[tuple[str, str]],
    ) -> None:
        titles = "; ".join(message for _key, message in items)
        subject = f"[ASMG] {kind}: {titles}"
        if len(subject) > 180:
            subject = subject[:177] + "..."
        lines = [
            titles,
            f"Transmitter: {reading.name}",
            f"Host: {reading.host}",
            "",
            *reading.summary_lines(),
        ]
        self._deliver(subject, "\n".join(lines), tuple(key for key, _ in items))

    def _send_recovery(
        self, reading: TransmitterReading, keys: list[str]
    ) -> None:
        label = ", ".join(keys)
        lines = [
            f"Cleared: {label}",
            f"Transmitter: {reading.name}",
            f"Host: {reading.host}",
            "",
            *reading.summary_lines(),
        ]
        self._deliver(
            f"[ASMG] RECOVERED: {reading.name}",
            "\n".join(lines),
            (),
        )

    def _deliver(
        self,
        subject: str,
        body: str,
        keys: tuple[str, ...],
        *,
        sync: bool = False,
    ) -> None:
        def _run() -> None:
            try:
                _send_email(self.config, subject, body)
            except Exception as error:
                logger.error("Email send failed: %s", error)
                with self._lock:
                    self._last_error = str(error)
                    self._save_locked()
                if sync or not self.async_send:
                    raise
                return
            with self._lock:
                self._last_error = ""
                sent_at = datetime.now(timezone.utc).isoformat()
                self._last_sent_at = sent_at
                for key in keys:
                    self._last_sent[key] = sent_at
                self._save_locked()
            logger.info("Sent email: %s", subject)

        if self.async_send and not sync:
            threading.Thread(target=_run, name="asmg-email", daemon=True).start()
            return
        _run()

    def _push_event_locked(self, kind: str, message: str) -> None:
        self._recent_events.append(
            {
                "kind": kind,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._recent_events = self._recent_events[-50:]

    def _prune_snoozes_locked(self, now: datetime) -> None:
        expired = [
            key
            for key, until in self._snoozed_until.items()
            if not (_parse_time(until) and _parse_time(until) > now)
        ]
        for key in expired:
            self._snoozed_until.pop(key, None)

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Could not read alert state: %s", error)
            return
        self._active = {str(k): str(v) for k, v in dict(data.get("active") or {}).items()}
        self._acked = {str(k) for k in (data.get("acked") or [])}
        self._snoozed_until = {
            str(k): str(v) for k, v in dict(data.get("snoozed_until") or {}).items()
        }
        self._last_sent = {
            str(k): str(v) for k, v in dict(data.get("last_sent") or {}).items()
        }
        self._unreachable_streak = {
            str(k): int(v)
            for k, v in dict(data.get("unreachable_streak") or {}).items()
        }
        self._last_error = str(data.get("last_error") or "")
        last = data.get("last_sent_at")
        self._last_sent_at = str(last) if last else None
        events = data.get("recent_events") or []
        if isinstance(events, list):
            self._recent_events = [
                {
                    "kind": str(item.get("kind") or ""),
                    "message": str(item.get("message") or ""),
                    "timestamp": str(item.get("timestamp") or ""),
                }
                for item in events
                if isinstance(item, dict)
            ][-50:]

    def _save_locked(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "active": self._active,
            "acked": sorted(self._acked),
            "snoozed_until": self._snoozed_until,
            "last_sent": self._last_sent,
            "unreachable_streak": self._unreachable_streak,
            "last_error": self._last_error,
            "last_sent_at": self._last_sent_at,
            "recent_events": self._recent_events[-20:],
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _send_email(config: AlertConfig, subject: str, body: str) -> None:
    from_addr = config.email_from.strip() or config.smtp_username.strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(config.email_to)
    msg.set_content(body)

    if config.smtp_tls:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            if config.smtp_username:
                smtp.login(config.smtp_username, config.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
            if config.smtp_username:
                smtp.login(config.smtp_username, config.smtp_password)
            smtp.send_message(msg)
