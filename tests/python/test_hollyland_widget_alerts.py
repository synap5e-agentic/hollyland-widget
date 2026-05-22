"""Tests for service/hollyland_widget_alerts.py."""

from __future__ import annotations

import json

import hollyland_widget_alerts as hwa


NOW_ISO = "2026-05-22T10:32:11Z"


def _tx(
    battery: int | float | None,
    *,
    tx_id: str = "tx1",
    online: bool = True,
    estimate: dict | None = None,
) -> dict:
    item = {
        "id": tx_id,
        "label": tx_id.upper(),
        "online": online,
        "battery": battery,
    }
    if estimate is not None:
        item["power"] = {"estimate": estimate}
    return item


def _estimate(minutes_remaining: int | float, confidence: str | None = "low") -> dict:
    return {
        "state": "available",
        "confidence": confidence,
        "minutes_remaining": minutes_remaining,
    }


def _write_store(path, states: dict[str, str]) -> None:
    path.write_text(
        json.dumps(
            {
                "v": hwa.ALERT_STORE_VERSION,
                "tx_states": {
                    tx_id: {
                        "level": level,
                        "level_since": NOW_ISO,
                        "last_notified_level": None,
                        "last_notified_at": None,
                    }
                    for tx_id, level in states.items()
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


# ---------- compute_level ----------

def test_threshold_entry_battery_warning():
    assert hwa.compute_level(_tx(6), "none") == "none"
    assert hwa.compute_level(_tx(4), "none") == "warning"


def test_estimate_based_warning():
    tx = _tx(20, estimate=_estimate(10, confidence="low"))
    assert hwa.compute_level(tx, "none") == "warning"


def test_critical_entry():
    assert hwa.compute_level(_tx(0), "warning") == "critical"


def test_critical_hysteresis_clears_at_three_percent():
    assert hwa.compute_level(_tx(2), "critical") == "critical"
    assert hwa.compute_level(_tx(3), "critical") == "warning"


def test_warning_hysteresis_clears_at_seven_percent():
    assert hwa.compute_level(_tx(6), "warning") == "warning"
    assert hwa.compute_level(_tx(7), "warning") == "none"


def test_warning_hysteresis_keeps_estimate_until_eighteen_minutes():
    assert hwa.compute_level(_tx(20, estimate=_estimate(17)), "warning") == "warning"
    assert hwa.compute_level(_tx(20, estimate=_estimate(18)), "warning") == "none"


# ---------- AlertStore ----------

def test_alert_store_roundtrip(tmp_path):
    path = tmp_path / "alerts.json"
    store = hwa.AlertStore(path)

    transition = store.update("tx1", "warning", NOW_ISO)
    store.save()

    assert transition.notify is False  # missing file establishes a baseline without first-run noise

    loaded = hwa.AlertStore(path).load()
    assert loaded["tx1"].level == "warning"
    assert loaded["tx1"].level_since == NOW_ISO


def test_alert_store_corrupt_json_falls_back_to_empty(tmp_path):
    path = tmp_path / "alerts.json"
    path.write_text("not-json\n", encoding="utf-8")
    assert hwa.AlertStore(path).load() == {}


def test_alert_store_existing_none_to_warning_notifies(tmp_path):
    path = tmp_path / "alerts.json"
    _write_store(path, {"tx1": "none"})

    store = hwa.AlertStore(path)
    transition = store.update("tx1", "warning", NOW_ISO)

    assert transition.previous_level == "none"
    assert transition.new_level == "warning"
    assert transition.notify is True


# ---------- apply_alerts ----------

def test_apply_alerts_dispatches_only_ascending_transitions(tmp_path, monkeypatch):
    path = tmp_path / "alerts.json"
    _write_store(path, {"tx1": "none", "tx2": "warning", "tx3": "critical"})
    captured: list[list[hwa.Transition]] = []
    real_dispatch = hwa.dispatch_notifications

    def fake_dispatch(transitions: list[hwa.Transition], dry_run: bool = False) -> None:
        captured.append(transitions)
        real_dispatch(transitions, dry_run=True)

    monkeypatch.setattr(hwa, "dispatch_notifications", fake_dispatch)

    state = {
        "transmitters": [
            _tx(4, tx_id="tx1"),
            _tx(6, tx_id="tx2"),
            _tx(3, tx_id="tx3"),
        ],
        "primary_tx": {"id": "tx1"},
    }

    out = hwa.apply_alerts(state, hwa.AlertStore(path), now_iso=NOW_ISO)

    assert [row["alert_level"] for row in out["transmitters"]] == ["warning", "warning", "warning"]
    assert out["primary_tx"] is out["transmitters"][0]
    assert len(captured) == 1
    assert [(item.tx_id, item.previous_level, item.new_level) for item in captured[0]] == [
        ("tx1", "none", "warning")
    ]


# ---------- dispatch_notifications ----------

def test_notify_send_invoked_with_urgency(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, *, check, timeout):
        calls.append(argv)

    monkeypatch.setattr(hwa.subprocess, "run", fake_run)

    hwa.dispatch_notifications(
        [
            hwa.Transition("tx1", "none", "warning", True, _tx(4)),
            hwa.Transition("tx2", "warning", "critical", True, _tx(0)),
        ]
    )

    assert calls[0][:6] == ["notify-send", "-u", "normal", "-a", "Hollyland", "TX tx1: low battery"]
    assert calls[1][:6] == ["notify-send", "-u", "critical", "-a", "Hollyland", "TX tx2: battery critical"]
    assert "Current battery: 4%" in calls[0][-1]
    assert "Current battery: 0%" in calls[1][-1]


def test_notify_send_failure_does_not_block_persistence(tmp_path, monkeypatch):
    path = tmp_path / "alerts.json"
    _write_store(path, {"tx1": "none"})

    def fake_run(argv, *, check, timeout):
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(hwa.subprocess, "run", fake_run)

    out = hwa.apply_alerts(
        {"transmitters": [_tx(0, estimate=_estimate(5))]},
        hwa.AlertStore(path),
        now_iso=NOW_ISO,
    )

    assert out["transmitters"][0]["alert_level"] == "critical"
    loaded = hwa.AlertStore(path).load()
    assert loaded["tx1"].level == "critical"
    assert loaded["tx1"].last_notified_level == "critical"
