#!/usr/bin/env python3
"""In-tree Python API for the Hollyland receiver.

The command ids and V2 frame layout are ported from the legacy out-of-tree APK
reverse-engineering probes. This module owns the runtime surface used by the
widget; the research package is not imported.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Literal

from hollyland_models import HeartInfo
from hollyland_models import SetResult
from hollyland_models import Summary
from hollyland_protocol import EQ_VALUES
from hollyland_protocol import FEATURE_LEN
from hollyland_protocol import SIGNAL_MODE_VALUES
from hollyland_protocol import SHUTDOWN_VALUES
from hollyland_protocol import TX_DEVICE_TYPES
from hollyland_protocol import VOICE_MODE_VALUES
from hollyland_protocol import Exchange
from hollyland_protocol import ExchangeResult
from hollyland_protocol import format_mac_payload
from hollyland_protocol import get_heart_info_exchange
from hollyland_protocol import parse_v2_response
from hollyland_protocol import set_eq_exchange
from hollyland_protocol import set_light_exchange
from hollyland_protocol import set_noise_exchange
from hollyland_protocol import set_performance_exchange
from hollyland_protocol import set_shutdown_time_exchange
from hollyland_protocol import set_signal_mode_exchange
from hollyland_protocol import set_tx_identify_exchange
from hollyland_protocol import set_tx_mute_exchange
from hollyland_protocol import set_voice_level_exchange
from hollyland_protocol import set_voice_mode_exchange
from hollyland_protocol import summary_exchanges
from hollyland_usb import DEFAULT_PRODUCT_ID
from hollyland_usb import DEFAULT_VENDOR_ID
from hollyland_usb import USB_TRANSPORT_NAME
from hollyland_usb import UsbLayout
from hollyland_usb import UsbTransport
from hollyland_usb import default_transport_for_layout
from hollyland_usb import discover_layout


TxId = Literal["tx1", "tx2", "tx3", "tx4"]
VoiceMode = Literal["mono", "stereo"]
SignalMode = Literal["normal", "enhance"]
EqPreset = Literal["overcast", "bright", "balance"]
ShutdownMode = Literal["quarter", "never"]


class HollylandClient:
    def __init__(
        self,
        *,
        transport: UsbTransport | None = None,
        layout_provider: Callable[[], UsbLayout] | None = None,
        feature_len: int = FEATURE_LEN,
    ) -> None:
        self._transport = transport
        self._layout_provider = layout_provider or discover_layout
        self._feature_len = feature_len

    def summary(self) -> Summary:
        layout = self._layout_provider()
        if self._transport is None and not layout.usb_devices:
            return _empty_summary(layout, probe_error="no Hollyland USB device found")

        try:
            results = self._transport_for_layout(layout).exchange(summary_exchanges(self._feature_len))
        except OSError as exc:
            return _empty_summary(layout, probe_error=str(exc))

        return _summary_from_results(layout, results)

    def set_noise(self, on: bool, level: int) -> SetResult:
        _validate_bool(on, "on")
        _validate_byte(level, "level")
        return self._run_setter("set-noise", set_noise_exchange(on, level, self._feature_len))

    def set_performance(self, on: bool) -> SetResult:
        _validate_bool(on, "on")
        return self._run_setter("set-performance", set_performance_exchange(on, self._feature_len))

    def set_light(self, on: bool) -> SetResult:
        _validate_bool(on, "on")
        return self._run_setter("set-light", set_light_exchange(on, self._feature_len))

    def set_tx_identify(self, on: bool) -> SetResult:
        _validate_bool(on, "on")
        return self._run_setter("set-tx-identify", set_tx_identify_exchange(on, self._feature_len))

    def set_tx_mute(self, tx: TxId, on: bool) -> SetResult:
        _validate_choice(tx, TX_DEVICE_TYPES, "tx")
        _validate_bool(on, "on")
        return self._run_setter("set-tx-mute", set_tx_mute_exchange(tx, on, self._feature_len))

    def set_voice_mode(self, mode: VoiceMode) -> SetResult:
        _validate_choice(mode, VOICE_MODE_VALUES, "mode")
        return self._run_setter("set-voice-mode", set_voice_mode_exchange(mode, self._feature_len))

    def set_signal_mode(self, mode: SignalMode) -> SetResult:
        _validate_choice(mode, SIGNAL_MODE_VALUES, "mode")
        return self._run_setter("set-signal-mode", set_signal_mode_exchange(mode, self._feature_len))

    def set_eq(self, preset: EqPreset) -> SetResult:
        _validate_choice(preset, EQ_VALUES, "preset")
        return self._run_setter("set-eq", set_eq_exchange(preset, self._feature_len))

    def set_shutdown_time(self, mode: ShutdownMode) -> SetResult:
        _validate_choice(mode, SHUTDOWN_VALUES, "mode")
        return self._run_setter("set-shutdown-time", set_shutdown_time_exchange(mode, self._feature_len))

    def set_voice_level(self, value: int) -> SetResult:
        if not isinstance(value, int) or isinstance(value, bool) or value not in range(0, 6):
            raise ValueError("voice level must be between 0 and 5")
        return self._run_setter("set-voice-level", set_voice_level_exchange(value, self._feature_len))

    def _run_setter(self, action: str, exchange: Exchange) -> SetResult:
        layout = self._layout_provider()
        results = self._transport_for_layout(layout).exchange(
            [exchange, get_heart_info_exchange(self._feature_len)]
        )
        ack = _first_parsed_response(results[0]) if results else None
        heart = _first_parsed_response(results[1]) if len(results) > 1 else None
        heart_info = HeartInfo.model_validate(heart.decoded) if heart and heart.command == 31 else None
        ack_ok = None if ack is None else ack.decoded.get("ok")
        status_byte = None if ack is None else ack.decoded.get("status_byte")
        return SetResult(
            ok=ack_ok is not False,
            action=action,
            ack_ok=ack_ok if isinstance(ack_ok, bool) else None,
            status_byte=status_byte if isinstance(status_byte, int) else None,
            heart_info=heart_info,
        )

    def _transport_for_layout(self, layout: UsbLayout) -> UsbTransport:
        if self._transport is not None:
            return self._transport
        return default_transport_for_layout(layout)


def _summary_from_results(layout: UsbLayout, results: list[ExchangeResult]) -> Summary:
    rx_sn: str | None = None
    rx_version: str | None = None
    rx_mac: str | None = None
    performance_mode: int | None = None
    heart_info: HeartInfo | None = None

    for result in results:
        parsed = _first_parsed_response(result)
        if parsed is None:
            continue
        if parsed.command == 18:
            ascii_value = parsed.decoded.get("ascii")
            rx_sn = ascii_value if isinstance(ascii_value, str) else None
        elif parsed.command == 13:
            version = parsed.decoded.get("version")
            rx_version = version if isinstance(version, str) else None
        elif parsed.command == 48:
            rx_mac = format_mac_payload(parsed.payload)
        elif parsed.command == 70:
            value = parsed.decoded.get("performance_mode")
            performance_mode = value if isinstance(value, int) else None
        elif parsed.command == 31:
            heart_info = HeartInfo.model_validate(parsed.decoded)

    return Summary(
        vendor_id=f"0x{layout.vendor_id:04x}",
        product_id=f"0x{layout.product_id:04x}",
        usb=layout.usb_devices,
        permissions_ok=layout.access_ready,
        suggested_chmod=layout.suggested_chmod,
        probe_ok=True,
        probe_error=None,
        transport=USB_TRANSPORT_NAME,
        rx_sn=rx_sn,
        rx_version=rx_version,
        rx_mac=rx_mac,
        performance_mode=performance_mode,
        heart_info=heart_info,
    )


def _empty_summary(layout: UsbLayout, *, probe_error: str) -> Summary:
    return Summary(
        vendor_id=f"0x{layout.vendor_id:04x}",
        product_id=f"0x{layout.product_id:04x}",
        usb=layout.usb_devices,
        permissions_ok=layout.access_ready,
        suggested_chmod=layout.suggested_chmod,
        probe_ok=False,
        probe_error=probe_error,
    )


def _first_parsed_response(result: ExchangeResult):
    if not result.responses:
        return None
    return parse_v2_response(result.responses[0])


def _validate_bool(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")


def _validate_byte(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value not in range(0, 256):
        raise ValueError(f"{name} must be between 0 and 255")


def _validate_choice(value: str, choices: dict[str, int], name: str) -> None:
    if value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {allowed}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug the Hollyland receiver API directly")
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("summary", help="read receiver summary")

    p = sub.add_parser("set-noise")
    _add_on_off(p)
    p.add_argument("--level", type=int, default=2)

    for command in ("set-performance", "set-light", "set-tx-identify"):
        _add_on_off(sub.add_parser(command))

    p = sub.add_parser("set-tx-mute")
    p.add_argument("--tx", choices=sorted(TX_DEVICE_TYPES), required=True)
    _add_on_off(p)

    p = sub.add_parser("set-voice-mode")
    p.add_argument("--mode", choices=sorted(VOICE_MODE_VALUES), required=True)

    p = sub.add_parser("set-signal-mode")
    p.add_argument("--mode", choices=sorted(SIGNAL_MODE_VALUES), required=True)

    p = sub.add_parser("set-eq")
    p.add_argument("--preset", choices=sorted(EQ_VALUES), required=True)

    p = sub.add_parser("set-shutdown-time")
    p.add_argument("--mode", choices=sorted(SHUTDOWN_VALUES), required=True)

    p = sub.add_parser("set-voice-level")
    p.add_argument("--value", type=int, choices=list(range(0, 6)), required=True)

    return parser


def _add_on_off(parser: argparse.ArgumentParser) -> None:
    toggle = parser.add_mutually_exclusive_group(required=True)
    toggle.add_argument("--on", action="store_true")
    toggle.add_argument("--off", action="store_true")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(["summary"] if argv == [] else argv)
    client = HollylandClient()
    command = args.command or "summary"
    if command == "summary":
        result = client.summary()
    elif command == "set-noise":
        result = client.set_noise(args.on, args.level)
    elif command == "set-performance":
        result = client.set_performance(args.on)
    elif command == "set-light":
        result = client.set_light(args.on)
    elif command == "set-tx-identify":
        result = client.set_tx_identify(args.on)
    elif command == "set-tx-mute":
        result = client.set_tx_mute(args.tx, args.on)
    elif command == "set-voice-mode":
        result = client.set_voice_mode(args.mode)
    elif command == "set-signal-mode":
        result = client.set_signal_mode(args.mode)
    elif command == "set-eq":
        result = client.set_eq(args.preset)
    elif command == "set-shutdown-time":
        result = client.set_shutdown_time(args.mode)
    elif command == "set-voice-level":
        result = client.set_voice_level(args.value)
    else:
        raise ValueError(f"unsupported command: {command}")

    print(json.dumps(result.model_dump(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
