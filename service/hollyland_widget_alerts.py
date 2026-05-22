"""Low-battery alert state and notification helpers for hollyland-widget-service."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


AlertLevel = Literal["none", "warning", "critical"]

ALERT_STORE_VERSION = 1
DEFAULT_ALERTS_PATH = Path.home() / ".cache" / "hollyland-widget" / "alerts.json"
ALERT_SEVERITY: dict[AlertLevel, int] = {"none": 0, "warning": 1, "critical": 2}
VALID_ALERT_LEVELS = frozenset(ALERT_SEVERITY)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertState:
    level: AlertLevel = "none"
    level_since: str | None = None
    last_notified_level: AlertLevel | None = None
    last_notified_at: str | None = None


@dataclass(frozen=True)
class Transition:
    tx_id: str
    previous_level: AlertLevel
    new_level: AlertLevel
    notify: bool
    transmitter: dict[str, Any] | None = None


def utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compute_level(transmitter: dict[str, Any], previous_level: AlertLevel) -> AlertLevel:
    """Compute the current alert level from a transmitter row and previous level."""
    if transmitter.get("online") is not True:
        return "none"

    battery = _battery_percent(transmitter)
    critical_by_battery = battery is not None and battery < 1
    warning_by_battery = battery is not None and battery < 5
    warning_by_estimate = _estimate_warning_active(transmitter)

    if previous_level == "critical":
        if critical_by_battery or battery is None or battery < 3:
            return "critical"
        return "warning"

    if critical_by_battery:
        return "critical"

    if previous_level == "warning":
        if warning_by_battery or warning_by_estimate:
            return "warning"
        if battery is not None and battery >= 7 and _estimate_warning_clear(transmitter):
            return "none"
        return "warning"

    if warning_by_battery or warning_by_estimate:
        return "warning"
    return "none"


def apply_alerts(
    state: dict[str, Any],
    store: AlertStore,
    *,
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Apply alert state to transmitter rows, persist state, and dispatch notifications."""
    if now_iso is None:
        now_iso = utc_now_iso_z()

    previous_states = store.load()
    transitions: list[Transition] = []
    rows = state.get("transmitters") or []
    enriched_rows: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        item = dict(row)
        tx_id = item.get("id")
        previous_level: AlertLevel = "none"
        if isinstance(tx_id, str) and tx_id:
            previous_level = previous_states.get(tx_id, AlertState()).level

        new_level = compute_level(item, previous_level)
        item["alert_level"] = new_level
        item["alert_reason"] = _alert_reason(item, new_level)

        if isinstance(tx_id, str) and tx_id:
            transition = store.update(tx_id, new_level, now_iso)
            if transition.notify:
                transitions.append(
                    Transition(
                        tx_id=tx_id,
                        previous_level=transition.previous_level,
                        new_level=new_level,
                        notify=True,
                        transmitter=dict(item),
                    )
                )
        enriched_rows.append(item)

    enriched_state = dict(state)
    enriched_state["transmitters"] = enriched_rows

    primary_tx = state.get("primary_tx")
    if isinstance(primary_tx, dict):
        primary_id = primary_tx.get("id")
        if isinstance(primary_id, str):
            match = next((row for row in enriched_rows if row.get("id") == primary_id), None)
            enriched_state["primary_tx"] = match if match is not None else dict(primary_tx)

    store.save()
    dispatch_notifications(transitions)
    return enriched_state


def dispatch_notifications(transitions: list[Transition], dry_run: bool = False) -> None:
    for transition in transitions:
        if not transition.notify or transition.new_level == "none":
            continue

        urgency = "critical" if transition.new_level == "critical" else "normal"
        title = (
            f"TX {transition.tx_id}: battery critical"
            if transition.new_level == "critical"
            else f"TX {transition.tx_id}: low battery"
        )
        argv = ["notify-send", "-u", urgency, "-a", "Hollyland", title, _notification_body(transition)]
        if dry_run:
            continue

        try:
            subprocess.run(argv, check=False, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            LOGGER.warning("failed to send Hollyland battery notification for %s: %s", transition.tx_id, exc)


class AlertStore:
    def __init__(self, path: Path = DEFAULT_ALERTS_PATH) -> None:
        self.path = path
        self._states: dict[str, AlertState] = {}
        self._loaded = False

    def load(self) -> dict[str, AlertState]:
        if self._loaded:
            return dict(self._states)

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            self._states = {}
            self._loaded = True
            return {}
        except json.JSONDecodeError:
            self._states = {}
            self._loaded = True
            return {}

        self._states = _parse_store_payload(raw)
        self._loaded = True
        return dict(self._states)

    def update(self, tx_id: str, new_level: AlertLevel, now_iso: str) -> Transition:
        if not self._loaded:
            self.load()

        previous = self._states.get(tx_id, AlertState())
        is_missing_tx = tx_id not in self._states
        notify = ALERT_SEVERITY[new_level] > ALERT_SEVERITY[previous.level] and not is_missing_tx

        if new_level == previous.level:
            next_state = previous
        else:
            next_state = AlertState(
                level=new_level,
                level_since=now_iso,
                last_notified_level=new_level if notify else previous.last_notified_level,
                last_notified_at=now_iso if notify else previous.last_notified_at,
            )
        self._states[tx_id] = next_state
        return Transition(tx_id=tx_id, previous_level=previous.level, new_level=new_level, notify=notify)

    def save(self) -> None:
        payload = {
            "v": ALERT_STORE_VERSION,
            "tx_states": {
                tx_id: {
                    "level": state.level,
                    "level_since": state.level_since,
                    "last_notified_level": state.last_notified_level,
                    "last_notified_at": state.last_notified_at,
                }
                for tx_id, state in sorted(self._states.items())
            },
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.path)
        except OSError as exc:
            LOGGER.warning("failed to persist Hollyland battery alert state to %s: %s", self.path, exc)


def _parse_store_payload(raw: Any) -> dict[str, AlertState]:
    if not isinstance(raw, dict) or raw.get("v") != ALERT_STORE_VERSION:
        return {}
    tx_states = raw.get("tx_states")
    if not isinstance(tx_states, dict):
        return {}

    states: dict[str, AlertState] = {}
    for tx_id, item in tx_states.items():
        if not isinstance(tx_id, str) or not tx_id or not isinstance(item, dict):
            continue
        level = _coerce_level(item.get("level"))
        if level is None:
            continue
        states[tx_id] = AlertState(
            level=level,
            level_since=_coerce_str(item.get("level_since")),
            last_notified_level=_coerce_level(item.get("last_notified_level")),
            last_notified_at=_coerce_str(item.get("last_notified_at")),
        )
    return states


def _coerce_level(value: Any) -> AlertLevel | None:
    if value in VALID_ALERT_LEVELS:
        return value
    return None


def _coerce_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _battery_percent(transmitter: dict[str, Any]) -> float | None:
    battery = transmitter.get("battery")
    if isinstance(battery, bool) or not isinstance(battery, (int, float)):
        return None
    return float(battery)


def _estimate_payload(transmitter: dict[str, Any]) -> dict[str, Any]:
    power = transmitter.get("power")
    if not isinstance(power, dict):
        return {}
    estimate = power.get("estimate")
    return estimate if isinstance(estimate, dict) else {}


def _estimate_minutes(estimate: dict[str, Any]) -> float | None:
    minutes = estimate.get("minutes_remaining")
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)):
        return None
    return float(minutes)


def _estimate_warning_active(transmitter: dict[str, Any]) -> bool:
    estimate = _estimate_payload(transmitter)
    minutes = _estimate_minutes(estimate)
    return (
        estimate.get("state") == "available"
        and estimate.get("confidence") is not None
        and minutes is not None
        and minutes < 15
    )


def _estimate_warning_clear(transmitter: dict[str, Any]) -> bool:
    estimate = _estimate_payload(transmitter)
    if estimate.get("state") != "available" or estimate.get("confidence") is None:
        return True
    minutes = _estimate_minutes(estimate)
    return minutes is None or minutes >= 18


def _alert_reason(transmitter: dict[str, Any], level: AlertLevel) -> str:
    if level == "none":
        return "none"
    battery = _battery_percent(transmitter)
    if level == "critical":
        return "battery_below_1_percent" if battery is not None and battery < 1 else "critical_hysteresis"
    if battery is not None and battery < 5:
        return "battery_below_5_percent"
    if _estimate_warning_active(transmitter):
        return "estimate_below_15_minutes"
    return "warning_hysteresis"


def _notification_body(transition: Transition) -> str:
    transmitter = transition.transmitter or {}
    parts: list[str] = []
    battery = _battery_percent(transmitter)
    if battery is not None:
        parts.append(f"Current battery: {battery:g}%")
    minutes = _estimate_minutes(_estimate_payload(transmitter))
    if minutes is not None:
        parts.append(f"Estimated remaining: {minutes:g} minutes")
    if not parts:
        parts.append("Battery is low.")
    return "\n".join(parts)
