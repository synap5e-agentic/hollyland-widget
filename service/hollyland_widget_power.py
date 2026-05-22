"""History persistence and battery power derivation for hollyland-widget-service."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RAW_HISTORY_VERSION = 1
RAW_HISTORY_RETENTION_SECONDS = 48 * 60 * 60
GRAPH_WINDOW_SECONDS = 12 * 60 * 60
GRAPH_MAX_POINTS = 240
ESTIMATE_WINDOW_SECONDS = 2 * 60 * 60
MIN_ESTIMATE_POINTS = 6
MIN_ESTIMATE_SPAN_SECONDS = 30 * 60
POINT_CLUSTER_GAP_SECONDS = 30 * 60
GRAPH_STALE_SECONDS = POINT_CLUSTER_GAP_SECONDS
MAX_ESTIMATE_GAP_SECONDS = POINT_CLUSTER_GAP_SECONDS
SPURIOUS_POINT_GAP_SECONDS = 10 * 60
SPURIOUS_DROP_DELTA = 8
SPURIOUS_NEIGHBOR_DELTA = 2
TREND_RATE_THRESHOLD = 1.0


def current_epoch_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def iso_z_from_epoch_ms(epoch_ms: int) -> str:
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _coerce_epoch_ms(value: Any) -> int | None:
    if _is_int(value):
        return int(value)
    return None


def _history_record_epoch_ms(record: dict[str, Any]) -> int | None:
    return _coerce_epoch_ms(record.get("epoch_ms"))


def _record_timestamp(record: dict[str, Any], epoch_ms: int) -> str:
    ts = record.get("ts")
    if isinstance(ts, str) and ts:
        return ts
    return iso_z_from_epoch_ms(epoch_ms)


def _normalize_transmitter_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    battery = row.get("battery")
    return {
        "online": row.get("online"),
        "battery": int(battery) if _is_int(battery) else None,
        "mute": row.get("mute"),
    }


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load_records(self, *, now_ms: int | None = None) -> list[dict[str, Any]]:
        if now_ms is None:
            now_ms = current_epoch_ms()
        cutoff_ms = now_ms - (RAW_HISTORY_RETENTION_SECONDS * 1000)
        records: list[dict[str, Any]] = []

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(record, dict):
                        continue
                    epoch_ms = _history_record_epoch_ms(record)
                    if epoch_ms is None or epoch_ms < cutoff_ms:
                        continue
                    transmitters = record.get("transmitters")
                    if not isinstance(transmitters, dict):
                        continue
                    records.append(record)
        except OSError:
            return []

        return records

    def append_live_snapshot(
        self,
        summary: dict[str, Any],
        transmitters: list[dict[str, Any]],
        *,
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        if now_ms is None:
            now_ms = current_epoch_ms()

        records = self.load_records(now_ms=now_ms)
        records.append(build_history_record(summary, transmitters, now_ms=now_ms))
        self._write_records(records)
        return records

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
        temp_path.replace(self.path)


def build_history_record(
    summary: dict[str, Any],
    transmitters: list[dict[str, Any]],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    if now_ms is None:
        now_ms = current_epoch_ms()

    tx_map: dict[str, Any] = {}
    for row in transmitters:
        tx_id = row.get("id")
        if isinstance(tx_id, str) and tx_id:
            tx_map[tx_id] = _normalize_transmitter_snapshot(row)

    return {
        "v": RAW_HISTORY_VERSION,
        "ts": iso_z_from_epoch_ms(now_ms),
        "epoch_ms": now_ms,
        "transport": summary.get("transport") or "unknown",
        "transmitters": tx_map,
    }


def enrich_state_with_power(
    state: dict[str, Any],
    history_records: list[dict[str, Any]],
    *,
    now_ms: int | None = None,
) -> dict[str, Any]:
    if now_ms is None:
        now_ms = current_epoch_ms()

    rows = state.get("transmitters") or []
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        item["power"] = build_power_payload(item, history_records, now_ms=now_ms)
        enriched_rows.append(item)

    enriched_state = dict(state)
    enriched_state["transmitters"] = enriched_rows

    primary_tx = state.get("primary_tx")
    if isinstance(primary_tx, dict):
        primary_id = primary_tx.get("id")
        if isinstance(primary_id, str):
            match = next((row for row in enriched_rows if row.get("id") == primary_id), None)
            enriched_state["primary_tx"] = match if match is not None else dict(primary_tx)

    return enriched_state


def build_power_payload(
    transmitter: dict[str, Any],
    history_records: list[dict[str, Any]],
    *,
    now_ms: int,
) -> dict[str, Any]:
    tx_id = transmitter.get("id")
    graph_points = _collect_valid_points(history_records, tx_id, now_ms=now_ms, window_seconds=GRAPH_WINDOW_SECONDS)
    estimate_window_points = _collect_valid_points(
        history_records,
        tx_id,
        now_ms=now_ms,
        window_seconds=ESTIMATE_WINDOW_SECONDS,
    )
    estimate_points = _recent_monotonic_estimate_points(estimate_window_points)
    graph_is_stale = _points_are_stale(
        graph_points,
        now_ms=now_ms,
        stale_seconds=GRAPH_STALE_SECONDS,
    )
    latest_at = graph_points[-1]["ts"] if graph_points else None

    return {
        "trend": _determine_trend(transmitter, estimate_points),
        "latest_at": latest_at,
        "graph": {
            "label": "Battery",
            "value_kind": "percent",
            "max_value": 100,
            "window_seconds": GRAPH_WINDOW_SECONDS,
            "stale": graph_is_stale,
            "points": [] if graph_is_stale else _downsample_graph_points(graph_points),
        },
        "estimate": _build_estimate(transmitter, estimate_points),
    }


def _collect_valid_points(
    history_records: list[dict[str, Any]],
    tx_id: Any,
    *,
    now_ms: int,
    window_seconds: int,
) -> list[dict[str, Any]]:
    if not isinstance(tx_id, str) or not tx_id:
        return []

    cutoff_ms = now_ms - (window_seconds * 1000)
    points: list[dict[str, Any]] = []
    for record in history_records:
        epoch_ms = _history_record_epoch_ms(record)
        if epoch_ms is None or epoch_ms < cutoff_ms:
            continue
        transmitters = record.get("transmitters")
        if not isinstance(transmitters, dict):
            continue
        sample = transmitters.get(tx_id)
        if not isinstance(sample, dict):
            continue
        battery = sample.get("battery")
        if sample.get("online") is not True or not _is_int(battery):
            continue
        points.append(
            {
                "epoch_ms": epoch_ms,
                "ts": _record_timestamp(record, epoch_ms),
                "t": epoch_ms // 1000,
                "value": int(battery),
            }
        )

    points.sort(key=lambda item: item["epoch_ms"])
    return _filter_spurious_points(points)


def _filter_spurious_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(points) < 3:
        return points

    filtered: list[dict[str, Any]] = []
    for index, point in enumerate(points):
        if 0 < index < len(points) - 1:
            previous = points[index - 1]
            current = point
            following = points[index + 1]
            gap_before_seconds = max(0, (current["epoch_ms"] - previous["epoch_ms"]) // 1000)
            gap_after_seconds = max(0, (following["epoch_ms"] - current["epoch_ms"]) // 1000)
            if (
                gap_before_seconds <= SPURIOUS_POINT_GAP_SECONDS
                and gap_after_seconds <= SPURIOUS_POINT_GAP_SECONDS
                and abs(previous["value"] - following["value"]) <= SPURIOUS_NEIGHBOR_DELTA
                and previous["value"] - current["value"] >= SPURIOUS_DROP_DELTA
                and following["value"] - current["value"] >= SPURIOUS_DROP_DELTA
            ):
                continue
        filtered.append(point)
    return filtered


def _downsample_graph_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not points:
        return []

    bucket_width = math.ceil(GRAPH_WINDOW_SECONDS / GRAPH_MAX_POINTS)
    buckets: dict[int, dict[str, Any]] = {}
    for point in points:
        bucket = (point["t"] // bucket_width) * bucket_width
        previous = buckets.get(bucket)
        if previous is None or point["epoch_ms"] >= previous["epoch_ms"]:
            buckets[bucket] = point

    downsampled = sorted(buckets.values(), key=lambda item: item["t"])
    result: list[dict[str, Any]] = []
    previous_epoch_ms: int | None = None
    for point in downsampled:
        item = {"t": point["t"], "value": point["value"]}
        if previous_epoch_ms is not None:
            gap_seconds = max(0, (point["epoch_ms"] - previous_epoch_ms) // 1000)
            if gap_seconds > POINT_CLUSTER_GAP_SECONDS:
                item["break_before"] = True
        result.append(item)
        previous_epoch_ms = point["epoch_ms"]
    return result


def _points_are_stale(
    points: list[dict[str, Any]],
    *,
    now_ms: int,
    stale_seconds: int,
) -> bool:
    if not points:
        return False
    return (now_ms - points[-1]["epoch_ms"]) > (stale_seconds * 1000)


def _recent_monotonic_estimate_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contiguous = _recent_contiguous_points(points, max_gap_seconds=MAX_ESTIMATE_GAP_SECONDS)
    return _recent_monotonic_suffix(contiguous)


def _recent_contiguous_points(points: list[dict[str, Any]], *, max_gap_seconds: int) -> list[dict[str, Any]]:
    if len(points) < 2:
        return points

    start_index = len(points) - 1
    max_gap_ms = max_gap_seconds * 1000
    while start_index > 0:
        gap_ms = points[start_index]["epoch_ms"] - points[start_index - 1]["epoch_ms"]
        if gap_ms > max_gap_ms:
            break
        start_index -= 1
    return points[start_index:]


def _recent_monotonic_suffix(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(points) < 2:
        return points

    start_index = len(points) - 1
    direction = 0
    for index in range(len(points) - 2, -1, -1):
        delta = points[index + 1]["value"] - points[index]["value"]
        step_direction = 0 if delta == 0 else (1 if delta > 0 else -1)
        if step_direction == 0:
            start_index = index
            continue
        if direction == 0:
            direction = step_direction
            start_index = index
            continue
        if step_direction != direction:
            break
        start_index = index
    return points[start_index:]


def _determine_trend(transmitter: dict[str, Any], estimate_points: list[dict[str, Any]]) -> str:
    battery = transmitter.get("battery")
    if transmitter.get("online") is not True or not _is_int(battery):
        return "unknown"
    if len(estimate_points) < 2:
        return "unknown"

    slope = _fit_slope_percent_per_hour(estimate_points)
    if slope is None:
        return "unknown"
    if slope <= -TREND_RATE_THRESHOLD:
        return "discharging"
    if slope >= TREND_RATE_THRESHOLD:
        return "charging"
    return "steady"


def _build_estimate(transmitter: dict[str, Any], estimate_points: list[dict[str, Any]]) -> dict[str, Any]:
    battery = transmitter.get("battery")
    if transmitter.get("online") is not True:
        return _estimate_payload(
            state="unavailable",
            samples_used=len(estimate_points),
            note="transmitter offline",
        )
    if not _is_int(battery):
        return _estimate_payload(
            state="unavailable",
            samples_used=len(estimate_points),
            note="battery unavailable",
        )
    if len(estimate_points) < 2:
        return _estimate_payload(
            state="unavailable",
            samples_used=len(estimate_points),
            note="need more live samples",
        )

    slope = _fit_slope_percent_per_hour(estimate_points)
    if slope is None:
        return _estimate_payload(
            state="learning",
            samples_used=len(estimate_points),
            note="collecting discharge history",
        )

    metrics = _estimate_metrics(estimate_points)
    ready = (
        metrics["samples_used"] >= MIN_ESTIMATE_POINTS
        and metrics["span_seconds"] >= MIN_ESTIMATE_SPAN_SECONDS
        and metrics["max_gap_seconds"] <= MAX_ESTIMATE_GAP_SECONDS
    )

    if not ready:
        return _estimate_payload(
            state="learning",
            samples_used=metrics["samples_used"],
            note=_learning_note(metrics),
        )

    rate = round(abs(slope), 1)
    if slope >= TREND_RATE_THRESHOLD:
        return _estimate_payload(
            state="charging",
            samples_used=metrics["samples_used"],
            rate_percent_per_hour=rate,
            note="battery rising",
        )
    if abs(slope) < TREND_RATE_THRESHOLD:
        return _estimate_payload(
            state="steady",
            samples_used=metrics["samples_used"],
            rate_percent_per_hour=rate,
            note="battery level is steady",
        )

    minutes_remaining = max(0, int(round((int(battery) / -slope) * 60)))
    return _estimate_payload(
        state="available",
        samples_used=metrics["samples_used"],
        minutes_remaining=minutes_remaining,
        rate_percent_per_hour=rate,
        confidence=_estimate_confidence(metrics),
        note=None,
    )


def _estimate_metrics(points: list[dict[str, Any]]) -> dict[str, int]:
    if not points:
        return {
            "samples_used": 0,
            "span_seconds": 0,
            "max_gap_seconds": 0,
        }

    span_seconds = max(0, (points[-1]["epoch_ms"] - points[0]["epoch_ms"]) // 1000)
    max_gap_seconds = 0
    for previous, current in zip(points, points[1:]):
        gap_seconds = max(0, (current["epoch_ms"] - previous["epoch_ms"]) // 1000)
        if gap_seconds > max_gap_seconds:
            max_gap_seconds = gap_seconds

    return {
        "samples_used": len(points),
        "span_seconds": span_seconds,
        "max_gap_seconds": max_gap_seconds,
    }


def _fit_slope_percent_per_hour(points: list[dict[str, Any]]) -> float | None:
    if len(points) < 2:
        return None

    origin = points[0]["epoch_ms"]
    xs = [(point["epoch_ms"] - origin) / 3_600_000 for point in points]
    ys = [point["value"] for point in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 0:
        return 0.0
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return numerator / denominator


def _learning_note(metrics: dict[str, int]) -> str:
    if metrics["samples_used"] < MIN_ESTIMATE_POINTS:
        return "need 6 recent samples"
    if metrics["span_seconds"] < MIN_ESTIMATE_SPAN_SECONDS:
        return "need 30 minutes of recent samples"
    if metrics["max_gap_seconds"] > MAX_ESTIMATE_GAP_SECONDS:
        return "recent samples are too sparse"
    return "collecting discharge history"


def _estimate_confidence(metrics: dict[str, int]) -> str:
    if metrics["span_seconds"] >= 90 * 60 and metrics["samples_used"] >= 12:
        return "medium"
    return "low"


def _estimate_payload(
    *,
    state: str,
    samples_used: int,
    minutes_remaining: int | None = None,
    rate_percent_per_hour: float | None = None,
    confidence: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "minutes_remaining": minutes_remaining,
        "rate_percent_per_hour": rate_percent_per_hour,
        "samples_used": samples_used,
        "window_seconds": ESTIMATE_WINDOW_SECONDS,
        "confidence": confidence if state == "available" else None,
        "note": note,
    }
