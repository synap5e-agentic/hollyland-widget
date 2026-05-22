"""Tests for the in-tree Hollyland API client."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from hollyland_api import HollylandClient
from hollyland_models import UsbDevice
from hollyland_models import UsbPermission
from hollyland_protocol import Exchange
from hollyland_protocol import ExchangeResult
from hollyland_protocol import FEATURE_LEN
from hollyland_usb import DEFAULT_PRODUCT_ID
from hollyland_usb import DEFAULT_VENDOR_ID
from hollyland_usb import UsbLayout


def _frame(command: int, payload: bytes = b"") -> bytes:
    body = bytes([0x05, 0x03, 0xAA, 0xDD, command]) + len(payload).to_bytes(2, "big") + payload + b"\xEF"
    return body + bytes(FEATURE_LEN - len(body))


HEART_PAYLOAD = bytes(
    [
        1,  # tx1 online
        0,  # tx2 offline
        87,
        66,
        0,  # tx1 unmuted
        1,  # tx2 muted
        1,  # noise enabled
        2,
        4,
        1,  # stereo
        1,  # never
        0,  # light enabled
        3,  # balance
        1,  # reverb enabled
        5,
        0,  # tx identify off
        1,  # signal enhance
        1,  # tx3 online
        0,  # tx4 offline
        55,
        44,
        0,  # tx3 unmuted
        1,  # tx4 muted
    ]
)


class FakeTransport:
    def __init__(self, responses: dict[str, bytes] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[Exchange] = []

    def exchange(self, exchanges: Sequence[Exchange]) -> list[ExchangeResult]:
        self.calls.extend(exchanges)
        results: list[ExchangeResult] = []
        for exchange in exchanges:
            response = self.responses.get(exchange.request_name, _frame(_request_command(exchange), b"\x00"))
            results.append(ExchangeResult(exchange=exchange, responses=(response,)))
        return results


def _request_command(exchange: Exchange) -> int:
    return exchange.request_frame[4]


def _layout() -> UsbLayout:
    return UsbLayout(
        vendor_id=DEFAULT_VENDOR_ID,
        product_id=DEFAULT_PRODUCT_ID,
        usb_devices=[
            UsbDevice(
                sysfs_name="1-2",
                bus=1,
                dev=9,
                usb_dev="/dev/bus/usb/001/009",
                manufacturer="Hollyland",
                product="LARK MAX RX",
                serial="usb-serial",
                interface0_driver="usbhid",
            )
        ],
        usb_permissions=[
            UsbPermission(
                path="/dev/bus/usb/001/009",
                exists=True,
                readable=True,
                writable=True,
                mode="0o666",
            )
        ],
    )


def _client(transport: FakeTransport) -> HollylandClient:
    return HollylandClient(transport=transport, layout_provider=_layout)


def test_summary_parses_known_responses() -> None:
    transport = FakeTransport(
        {
            "get-sn": _frame(18, b"RX123456"),
            "get-version": _frame(13, bytes([0, 1, 2, 3])),
            "get-mac-rx": _frame(48, bytes.fromhex("aabbccddeeff")),
            "get-performance": _frame(70, b"\x01"),
            "get-heart-info": _frame(31, HEART_PAYLOAD),
        }
    )

    summary = _client(transport).summary()

    assert summary.probe_ok is True
    assert summary.permissions_ok is True
    assert summary.usb[0].usb_dev == "/dev/bus/usb/001/009"
    assert summary.rx_sn == "RX123456"
    assert summary.rx_version == "1.2.3"
    assert summary.rx_mac == "aa:bb:cc:dd:ee:ff"
    assert summary.performance_mode == 1
    assert summary.heart_info is not None
    assert summary.heart_info.tx1_status is True
    assert summary.heart_info.tx2_status is False
    assert summary.heart_info.tx1_battery == 87
    assert summary.heart_info.tx2_mute is True
    assert summary.heart_info.tx3_status is True
    assert summary.heart_info.tx4_mute is True
    assert summary.heart_info.noise_enabled is True
    assert summary.heart_info.noise_level == 2
    assert summary.heart_info.voice_level == 4
    assert summary.heart_info.voice_mode == 1
    assert summary.heart_info.voice_mode_name == "stereo"
    assert summary.heart_info.signal_mode == 1
    assert summary.heart_info.signal_mode_name == "enhance"
    assert summary.heart_info.eq_level == 3
    assert summary.heart_info.eq_level_name == "balance"
    assert summary.heart_info.shutdown_time == 1
    assert summary.heart_info.shutdown_time_name == "never"
    assert summary.heart_info.light_enabled is True
    assert summary.heart_info.tx_identify_enabled is False
    assert summary.heart_info.reverb_enabled is True
    assert summary.heart_info.reverb_level == 5


@pytest.mark.parametrize(
    ("method_name", "args", "command", "payload"),
    [
        ("set_noise", (True, 2), 19, b"\x01\x02"),
        ("set_performance", (False,), 69, b"\x00"),
        ("set_light", (True,), 33, b"\x00"),
        ("set_tx_identify", (True,), 35, b"\x01"),
        ("set_tx_mute", ("tx3", True), 22, b"\x02\x01"),
        ("set_voice_mode", ("stereo",), 1, b"\x01"),
        ("set_signal_mode", ("enhance",), 63, b"\x01"),
        ("set_eq", ("bright",), 7, b"\x02"),
        ("set_shutdown_time", ("never",), 39, b"\x01"),
        ("set_voice_level", (5,), 3, b"\x05"),
    ],
)
def test_setters_encode_expected_control_frames(
    method_name: str,
    args: tuple[object, ...],
    command: int,
    payload: bytes,
) -> None:
    transport = FakeTransport({"get-heart-info": _frame(31, HEART_PAYLOAD)})
    client = _client(transport)

    getattr(client, method_name)(*args)

    assert len(transport.calls) == 2
    assert transport.calls[0].request_frame == _frame(command, payload)
    assert transport.calls[1].request_name == "get-heart-info"
    assert transport.calls[1].request_frame == _frame(31)


def test_set_voice_level_rejects_out_of_range_before_usb_io() -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="voice level"):
        _client(transport).set_voice_level(99)
    assert transport.calls == []


def test_set_eq_rejects_bad_preset_before_usb_io() -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="preset"):
        _client(transport).set_eq("nonsense")
    assert transport.calls == []


def test_set_tx_mute_rejects_bad_tx_before_usb_io() -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="tx"):
        _client(transport).set_tx_mute("bad", True)
    assert transport.calls == []
