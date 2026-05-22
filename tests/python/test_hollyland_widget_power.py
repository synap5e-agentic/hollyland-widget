"""Tests for service/hollyland_widget_power.py."""

from __future__ import annotations

import json

import pytest

import hollyland_widget_power as hwp


NOW_MS = 1_700_000_000_000  # fixed anchor for all tests


def _point(epoch_ms: int, value: int) -> dict:
    return {
        "epoch_ms": epoch_ms,
        "ts": hwp.iso_z_from_epoch_ms(epoch_ms),
        "t": epoch_ms // 1000,
        "value": value,
    }


def _history_record(epoch_ms: int, transmitters: dict) -> dict:
    return {
        "v": 1,
        "ts": hwp.iso_z_from_epoch_ms(epoch_ms),
        "epoch_ms": epoch_ms,
        "transport": "usb",
        "transmitters": transmitters,
    }


# ---------- HistoryStore ----------

def test_history_store_roundtrip(tmp_path):
    store = hwp.HistoryStore(tmp_path / "hist.jsonl")
    summary = {"transport": "usb"}
    transmitters = [{"id": "TX1", "online": True, "battery": 80, "mute": False}]
    store.append_live_snapshot(summary, transmitters, now_ms=NOW_MS)
    store.append_live_snapshot(summary, transmitters, now_ms=NOW_MS + 1000)

    records = store.load_records(now_ms=NOW_MS + 1000)
    assert len(records) == 2
    assert records[0]["transmitters"]["TX1"]["battery"] == 80
    assert records[0]["transport"] == "usb"


def test_history_store_retention_drops_old(tmp_path):
    path = tmp_path / "hist.jsonl"
    store = hwp.HistoryStore(path)
    old_ms = NOW_MS - (hwp.RAW_HISTORY_RETENTION_SECONDS + 60) * 1000
    new_ms = NOW_MS - 60_000
    path.write_text(
        json.dumps(_history_record(old_ms, {"TX1": {"online": True, "battery": 50}})) + "\n"
        + json.dumps(_history_record(new_ms, {"TX1": {"online": True, "battery": 60}})) + "\n"
    )
    records = store.load_records(now_ms=NOW_MS)
    assert len(records) == 1
    assert records[0]["epoch_ms"] == new_ms


def test_history_store_skips_malformed(tmp_path):
    path = tmp_path / "hist.jsonl"
    store = hwp.HistoryStore(path)
    good = _history_record(NOW_MS - 1000, {"TX1": {"online": True, "battery": 70}})
    path.write_text(
        "not-json\n"
        + "\n"
        + json.dumps([1, 2, 3]) + "\n"  # not a dict
        + json.dumps({"no_epoch": True, "transmitters": {}}) + "\n"
        + json.dumps({"epoch_ms": NOW_MS - 500, "transmitters": "nope"}) + "\n"
        + json.dumps(good) + "\n"
    )
    records = store.load_records(now_ms=NOW_MS)
    assert len(records) == 1
    assert records[0]["transmitters"]["TX1"]["battery"] == 70


def test_history_store_missing_file_returns_empty(tmp_path):
    store = hwp.HistoryStore(tmp_path / "does-not-exist.jsonl")
    assert store.load_records(now_ms=NOW_MS) == []


# ---------- build_history_record ----------

def test_build_history_record_shape():
    rec = hwp.build_history_record(
        {"transport": "ble"},
        [
            {"id": "TX1", "online": True, "battery": 75, "mute": False},
            {"id": "", "online": True, "battery": 10},  # skipped: empty id
            {"id": "TX2", "online": False, "battery": None, "mute": True},
        ],
        now_ms=NOW_MS,
    )
    assert rec["v"] == hwp.RAW_HISTORY_VERSION
    assert rec["epoch_ms"] == NOW_MS
    assert rec["transport"] == "ble"
    assert set(rec["transmitters"]) == {"TX1", "TX2"}
    assert rec["transmitters"]["TX1"] == {"online": True, "battery": 75, "mute": False}
    assert rec["transmitters"]["TX2"]["battery"] is None


def test_build_history_record_default_transport():
    rec = hwp.build_history_record({}, [], now_ms=NOW_MS)
    assert rec["transport"] == "unknown"


# ---------- _filter_spurious_points ----------

def test_filter_spurious_drops_single_dip():
    base = NOW_MS
    pts = [
        _point(base + 0, 80),
        _point(base + 60_000, 70),  # dip
        _point(base + 120_000, 81),
    ]
    out = hwp._filter_spurious_points(pts)
    assert [p["value"] for p in out] == [80, 81]


def test_filter_spurious_preserves_when_neighbors_diverge():
    base = NOW_MS
    pts = [
        _point(base + 0, 80),
        _point(base + 60_000, 70),
        _point(base + 120_000, 60),  # big drop overall, not a dip
    ]
    out = hwp._filter_spurious_points(pts)
    assert [p["value"] for p in out] == [80, 70, 60]


def test_filter_spurious_preserves_when_gap_too_large():
    base = NOW_MS
    big_gap_ms = (hwp.SPURIOUS_POINT_GAP_SECONDS + 60) * 1000
    pts = [
        _point(base + 0, 80),
        _point(base + big_gap_ms, 70),
        _point(base + 2 * big_gap_ms, 81),
    ]
    out = hwp._filter_spurious_points(pts)
    assert [p["value"] for p in out] == [80, 70, 81]


# ---------- _downsample_graph_points ----------

def test_downsample_collapses_into_buckets():
    bucket = (hwp.GRAPH_WINDOW_SECONDS + hwp.GRAPH_MAX_POINTS - 1) // hwp.GRAPH_MAX_POINTS
    # Many points inside a single bucket → last one wins
    pts = [_point(NOW_MS + i * 1000, 50 + i) for i in range(5)]
    out = hwp._downsample_graph_points(pts)
    assert len(out) == 1
    assert out[0]["value"] == 54
    # Spread across two buckets → two points, no break_before (gap below cluster gap)
    pts2 = [
        _point(NOW_MS, 50),
        _point(NOW_MS + bucket * 1000, 51),
    ]
    out2 = hwp._downsample_graph_points(pts2)
    assert len(out2) == 2
    assert "break_before" not in out2[1]


def test_downsample_marks_break_before_on_big_gap():
    bucket = (hwp.GRAPH_WINDOW_SECONDS + hwp.GRAPH_MAX_POINTS - 1) // hwp.GRAPH_MAX_POINTS
    pts = [
        _point(NOW_MS, 50),
        _point(NOW_MS + (hwp.POINT_CLUSTER_GAP_SECONDS + 60) * 1000, 51),
    ]
    # Ensure they fall in different buckets
    assert (pts[1]["t"] // bucket) != (pts[0]["t"] // bucket)
    out = hwp._downsample_graph_points(pts)
    assert out[1].get("break_before") is True


# ---------- _recent_monotonic_estimate_points ----------

def test_recent_monotonic_picks_suffix():
    base = NOW_MS
    pts = [
        _point(base + 0, 60),
        _point(base + 60_000, 65),  # rising — different direction
        _point(base + 120_000, 64),
        _point(base + 180_000, 63),
        _point(base + 240_000, 62),  # monotonic descending suffix
    ]
    out = hwp._recent_monotonic_estimate_points(pts)
    assert [p["value"] for p in out] == [65, 64, 63, 62]


def test_recent_monotonic_respects_gap_break():
    base = NOW_MS
    big = (hwp.MAX_ESTIMATE_GAP_SECONDS + 60) * 1000
    pts = [
        _point(base + 0, 80),
        _point(base + 60_000, 79),
        _point(base + 60_000 + big, 78),
        _point(base + 120_000 + big, 77),
    ]
    out = hwp._recent_monotonic_estimate_points(pts)
    # Gap break drops the first two; remainder is monotonic
    assert [p["value"] for p in out] == [78, 77]


# ---------- _fit_slope_percent_per_hour ----------

def test_fit_slope_known_line():
    base = NOW_MS
    # value drops 10 every hour
    pts = [_point(base + i * 3_600_000, 100 - 10 * i) for i in range(4)]
    slope = hwp._fit_slope_percent_per_hour(pts)
    assert slope == pytest.approx(-10.0)


def test_fit_slope_flat_returns_zero():
    base = NOW_MS
    pts = [_point(base, 50), _point(base, 50)]  # zero variance in x
    assert hwp._fit_slope_percent_per_hour(pts) == 0.0


# ---------- _determine_trend ----------

def _discharge_points(slope_per_hour: float, samples: int = 6, step_s: int = 360):
    base = NOW_MS - samples * step_s * 1000
    return [
        _point(base + i * step_s * 1000, int(round(80 + slope_per_hour * (i * step_s / 3600))))
        for i in range(samples)
    ]


def test_trend_unknown_when_offline():
    assert hwp._determine_trend({"online": False, "battery": 50}, []) == "unknown"


def test_trend_unknown_when_no_battery():
    assert hwp._determine_trend({"online": True, "battery": None}, [_point(NOW_MS, 50)] * 2) == "unknown"


def test_trend_charging():
    pts = _discharge_points(+5.0)
    tx = {"online": True, "battery": pts[-1]["value"]}
    assert hwp._determine_trend(tx, pts) == "charging"


def test_trend_discharging():
    pts = _discharge_points(-5.0)
    tx = {"online": True, "battery": pts[-1]["value"]}
    assert hwp._determine_trend(tx, pts) == "discharging"


def test_trend_steady():
    base = NOW_MS - 6 * 360 * 1000
    pts = [_point(base + i * 360_000, 70) for i in range(6)]
    tx = {"online": True, "battery": 70}
    assert hwp._determine_trend(tx, pts) == "steady"


# ---------- _build_estimate ----------

def test_estimate_unavailable_offline():
    out = hwp._build_estimate({"online": False, "battery": 50}, [])
    assert out["state"] == "unavailable"
    assert out["note"] == "transmitter offline"


def test_estimate_unavailable_missing_battery():
    out = hwp._build_estimate({"online": True, "battery": None}, [])
    assert out["state"] == "unavailable"
    assert out["note"] == "battery unavailable"


def test_estimate_unavailable_too_few_samples():
    pts = [_point(NOW_MS, 50)]
    out = hwp._build_estimate({"online": True, "battery": 50}, pts)
    assert out["state"] == "unavailable"
    assert out["note"] == "need more live samples"


def test_estimate_learning_too_few_samples():
    base = NOW_MS - 30 * 60 * 1000
    # 3 samples spanning 30 min → samples < MIN_ESTIMATE_POINTS=6
    pts = [_point(base + i * 15 * 60_000, 80 - i) for i in range(3)]
    out = hwp._build_estimate({"online": True, "battery": 78}, pts)
    assert out["state"] == "learning"
    assert out["note"] == "need 6 recent samples"


def test_estimate_learning_short_span():
    # 6 samples but spanning only 5 min total
    base = NOW_MS - 5 * 60 * 1000
    pts = [_point(base + i * 60_000, 80 - i) for i in range(6)]
    out = hwp._build_estimate({"online": True, "battery": 75}, pts)
    assert out["state"] == "learning"
    assert out["note"] == "need 30 minutes of recent samples"


def test_estimate_learning_gap_too_large():
    # 6 samples, span >= 30 min, but one gap > MAX_ESTIMATE_GAP_SECONDS.
    base = NOW_MS - 90 * 60 * 1000
    huge_gap = (hwp.MAX_ESTIMATE_GAP_SECONDS + 600) * 1000
    times = [
        base + 0,
        base + 60_000,
        base + 120_000,
        base + 180_000,
        base + 180_000 + huge_gap,
        base + 240_000 + huge_gap,
    ]
    pts = [_point(t, 80 - i) for i, t in enumerate(times)]
    out = hwp._build_estimate({"online": True, "battery": 75}, pts)
    assert out["state"] == "learning"
    assert out["note"] == "recent samples are too sparse"


def _qualifying_points(slope_per_hour: float, end_value: int):
    # 6 samples at 6-minute intervals → span exactly 30 min, max gap 6 min.
    base = NOW_MS - 30 * 60 * 1000
    return [
        _point(
            base + i * 6 * 60_000,
            int(round(end_value - slope_per_hour * ((5 - i) * 6 / 60))),
        )
        for i in range(6)
    ]


def test_estimate_charging():
    pts = _qualifying_points(slope_per_hour=+10.0, end_value=60)
    out = hwp._build_estimate({"online": True, "battery": 60}, pts)
    assert out["state"] == "charging"
    assert out["rate_percent_per_hour"] == pytest.approx(10.0)


def test_estimate_steady():
    base = NOW_MS - 30 * 60 * 1000
    pts = [_point(base + i * 6 * 60_000, 60) for i in range(6)]
    out = hwp._build_estimate({"online": True, "battery": 60}, pts)
    assert out["state"] == "steady"


def test_estimate_available_minutes_remaining():
    # 50% battery, discharging 10%/hour → ~300 minutes.
    pts = _qualifying_points(slope_per_hour=-10.0, end_value=50)
    out = hwp._build_estimate({"online": True, "battery": 50}, pts)
    assert out["state"] == "available"
    assert out["minutes_remaining"] == pytest.approx(300, abs=2)
    assert out["rate_percent_per_hour"] == pytest.approx(10.0)
    assert out["confidence"] in {"low", "medium"}


# ---------- enrich_state_with_power ----------

def test_enrich_state_end_to_end():
    base = NOW_MS - 30 * 60 * 1000
    history = []
    for i in range(6):
        epoch = base + i * 6 * 60_000
        history.append(_history_record(epoch, {
            "TX1": {"online": True, "battery": 60 - i},
            "TX2": {"online": True, "battery": 90},
        }))

    state = {
        "transmitters": [
            {"id": "TX1", "online": True, "battery": 55},
            {"id": "TX2", "online": True, "battery": 90},
        ],
        "primary_tx": {"id": "TX1", "online": True, "battery": 55},
    }

    enriched = hwp.enrich_state_with_power(state, history, now_ms=NOW_MS)
    rows = enriched["transmitters"]
    assert len(rows) == 2
    assert all("power" in row for row in rows)
    assert rows[0]["power"]["trend"] in {"discharging", "steady", "charging", "unknown"}

    # primary_tx mirrors the enriched TX1 row.
    assert enriched["primary_tx"] is rows[0]


def test_enrich_state_primary_no_match():
    state = {
        "transmitters": [{"id": "TX1", "online": True, "battery": 80}],
        "primary_tx": {"id": "OTHER", "online": True, "battery": 50},
    }
    enriched = hwp.enrich_state_with_power(state, [], now_ms=NOW_MS)
    # No id match → primary_tx is a copy of the original dict (not the enriched row).
    assert enriched["primary_tx"]["id"] == "OTHER"
    assert "power" not in enriched["primary_tx"]
