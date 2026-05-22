"""Hollyland receiver V2 frame encoding and decoding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FEATURE_LEN = 64

DEVICE_TYPES = {
    "rx": 0,
    "tx1": 1,
    "tx2": 2,
    "tx3": 3,
    "tx4": 4,
    "box": 5,
    "ows-ear": 6,
}
TX_DEVICE_TYPES = {
    "tx1": 0,
    "tx2": 1,
    "tx3": 2,
    "tx4": 3,
}
VOICE_MODE_VALUES = {
    "mono": 0,
    "stereo": 1,
}
SIGNAL_MODE_VALUES = {
    "normal": 0,
    "enhance": 1,
}
EQ_VALUES = {
    "overcast": 1,
    "bright": 2,
    "balance": 3,
}
SHUTDOWN_VALUES = {
    "quarter": 0,
    "never": 1,
}

VOICE_MODE_NAMES = {
    0: "mono",
    1: "stereo",
}
SIGNAL_MODE_NAMES = {
    0: "normal",
    1: "enhance",
}
EQ_MODE_NAMES = {
    1: "overcast",
    2: "bright",
    3: "balance",
}
SHUTDOWN_MODE_NAMES = {
    0: "quarter-hour",
    1: "never",
}
COMMAND_NAMES = {
    1: "HID_SET_VOICE_MODE",
    2: "HID_GET_VOICE_MODE",
    3: "HID_SET_VOICE_LEVEL",
    4: "HID_GET_VOICE_LEVEL",
    7: "HID_SET_EQ",
    8: "HID_GET_EQ",
    13: "HID_GET_DEVICE_VERSION",
    18: "HID_GET_DEVICE_SN",
    19: "HID_SET_NOISE",
    20: "HID_GET_NOISE",
    22: "HID_SET_TX_MUTE",
    31: "HID_GET_HEART_INFO",
    33: "HID_SET_LIGHT",
    35: "HID_SET_TX_IDENTIFY",
    39: "HID_SET_SHUTDOWN_TIME",
    48: "HID_GET_DEVICE_MAC_RX",
    49: "HID_GET_DEVICE_MAC_TX",
    63: "HID_SET_SIGNAL_MODE",
    64: "HID_GET_SIGNAL_MODE",
    69: "HID_SET_PERFORMANCE_MODE",
    70: "HID_GET_PERFORMANCE_MODE",
}
ACK_COMMANDS = {1, 3, 7, 19, 22, 33, 35, 39, 63, 69}


@dataclass(frozen=True)
class Exchange:
    label: str
    request_name: str
    request_frame: bytes
    read_count: int = 1


@dataclass(frozen=True)
class ExchangeResult:
    exchange: Exchange
    responses: tuple[bytes, ...]


@dataclass(frozen=True)
class ParsedResponse:
    command: int | None
    command_name: str | None
    payload: bytes
    payload_hex: str
    decoded: dict[str, Any]
    raw_hex: str


def clean_ascii(data: bytes) -> str:
    filtered = bytes(byte for byte in data if byte not in (0x00, 0xFF))
    if not filtered:
        return ""
    return filtered.decode("utf-8", errors="replace")


def build_v2_frame(command: int, payload: bytes = b"", feature_len: int = FEATURE_LEN) -> bytes:
    payload_len = len(payload)
    frame_len = 7 + payload_len + 1
    if frame_len > feature_len:
        raise ValueError(f"payload too long for feature_len={feature_len}: need {frame_len} bytes")

    frame = bytearray(feature_len)
    frame[0] = 0x05
    frame[1] = 0x03
    frame[2] = 0xAA
    frame[3] = 0xDD
    frame[4] = command & 0xFF
    frame[5:7] = payload_len.to_bytes(2, "big")
    frame[7 : 7 + payload_len] = payload
    frame[7 + payload_len] = 0xEF
    return bytes(frame)


def parse_v2_response(data: bytes) -> ParsedResponse:
    if len(data) < 7:
        return ParsedResponse(
            command=None,
            command_name=None,
            payload=b"",
            payload_hex="",
            decoded={},
            raw_hex=data.hex(),
        )

    command = data[4]
    payload_len = int.from_bytes(data[5:7], "big")
    payload_end = 7 + payload_len
    payload = data[7:payload_end] if payload_end <= len(data) else b""
    return ParsedResponse(
        command=command,
        command_name=COMMAND_NAMES.get(command, f"UNKNOWN_{command}"),
        payload=payload,
        payload_hex=payload.hex(),
        decoded=decode_payload(command, payload),
        raw_hex=data.hex(),
    )


def decode_payload(command: int, payload: bytes) -> dict[str, Any]:
    if command == 31:
        return parse_heart_info(payload)
    if command == 13:
        return parse_version(payload)
    if command in {18, 48, 49}:
        return {"ascii": clean_ascii(payload), "bytes": [f"0x{byte:02x}" for byte in payload]}
    if command == 70:
        return parse_named_byte(payload, "performance_mode")
    if command in ACK_COMMANDS:
        return parse_ack(payload)
    return {"bytes": [f"0x{byte:02x}" for byte in payload]} if payload else {}


def parse_ack(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {"ok": None, "status_byte": None}
    status = payload[0]
    return {"ok": status == 0, "status_byte": status}


def parse_named_byte(payload: bytes, key: str) -> dict[str, Any]:
    return {key: payload[0] if payload else None}


def parse_version(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {}
    device_index = payload[0]
    version_parts = [str(byte) for byte in payload[1:]]
    return {
        "device_index": device_index,
        "device_type": next(
            (name for name, index in DEVICE_TYPES.items() if index == device_index),
            f"unknown_{device_index}",
        ),
        "version": ".".join(version_parts),
    }


def parse_heart_info(payload: bytes) -> dict[str, Any]:
    def byte_at(index: int) -> int | None:
        return payload[index] if index < len(payload) else None

    def bool_eq(index: int, value: int) -> bool | None:
        byte = byte_at(index)
        if byte is None:
            return None
        return byte == value

    fields: dict[str, Any] = {
        "tx1_status": bool_eq(0, 1),
        "tx2_status": bool_eq(1, 1),
        "tx1_battery": byte_at(2),
        "tx2_battery": byte_at(3),
        "tx1_mute": bool_eq(4, 1),
        "tx2_mute": bool_eq(5, 1),
        "noise_enabled": bool_eq(6, 1),
        "noise_level": byte_at(7),
        "voice_level": byte_at(8),
        "voice_mode": byte_at(9),
        "shutdown_time": byte_at(10),
        "light_enabled": _decode_light_enabled(byte_at(11)),
        "eq_level": byte_at(12),
        "reverb_enabled": bool_eq(13, 1),
        "reverb_level": byte_at(14),
        "tx_identify_enabled": bool_eq(15, 1),
        "signal_mode": byte_at(16),
        "tx3_status": bool_eq(17, 1),
        "tx4_status": bool_eq(18, 1),
        "tx3_battery": byte_at(19),
        "tx4_battery": byte_at(20),
        "tx3_mute": bool_eq(21, 1),
        "tx4_mute": bool_eq(22, 1),
    }
    if fields["voice_mode"] in VOICE_MODE_NAMES:
        fields["voice_mode_name"] = VOICE_MODE_NAMES[fields["voice_mode"]]
    if fields["shutdown_time"] in SHUTDOWN_MODE_NAMES:
        fields["shutdown_time_name"] = SHUTDOWN_MODE_NAMES[fields["shutdown_time"]]
    if fields["eq_level"] in EQ_MODE_NAMES:
        fields["eq_level_name"] = EQ_MODE_NAMES[fields["eq_level"]]
    if fields["signal_mode"] in SIGNAL_MODE_NAMES:
        fields["signal_mode_name"] = SIGNAL_MODE_NAMES[fields["signal_mode"]]
    return fields


def _decode_light_enabled(value: int | None) -> bool | None:
    if value is None:
        return None
    return value == 0


def format_mac_payload(payload: bytes) -> str | None:
    if not payload:
        return None
    payload_hex = payload.hex()
    if len(payload_hex) != 12:
        return payload_hex
    return ":".join(payload_hex[index : index + 2] for index in range(0, 12, 2))


def get_heart_info_exchange(feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label="heart-info poll #1",
        request_name="get-heart-info",
        request_frame=build_v2_frame(31, feature_len=feature_len),
    )


def summary_exchanges(feature_len: int = FEATURE_LEN) -> list[Exchange]:
    return [
        Exchange("get-sn rx", "get-sn", build_v2_frame(18, bytes([DEVICE_TYPES["rx"]]), feature_len)),
        Exchange("get-version rx", "get-version", build_v2_frame(13, bytes([DEVICE_TYPES["rx"]]), feature_len)),
        Exchange("get-mac rx", "get-mac-rx", build_v2_frame(48, feature_len=feature_len)),
        Exchange("get-performance after rx mac", "get-performance", build_v2_frame(70, feature_len=feature_len)),
        get_heart_info_exchange(feature_len),
    ]


def set_noise_exchange(on: bool, level: int, feature_len: int = FEATURE_LEN) -> Exchange:
    payload = bytes([1 if on else 0, level & 0xFF])
    return Exchange(
        label=f"set-noise {'on' if on else 'off'} level={level}",
        request_name="set-noise",
        request_frame=build_v2_frame(19, payload, feature_len),
    )


def set_performance_exchange(on: bool, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-performance {'on' if on else 'off'}",
        request_name="set-performance",
        request_frame=build_v2_frame(69, bytes([1 if on else 0]), feature_len),
    )


def set_light_exchange(on: bool, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-light {'on' if on else 'off'}",
        request_name="set-light",
        request_frame=build_v2_frame(33, bytes([0 if on else 1]), feature_len),
    )


def set_tx_identify_exchange(on: bool, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-tx-identify {'on' if on else 'off'}",
        request_name="set-tx-identify",
        request_frame=build_v2_frame(35, bytes([1 if on else 0]), feature_len),
    )


def set_tx_mute_exchange(tx: str, on: bool, feature_len: int = FEATURE_LEN) -> Exchange:
    payload = bytes([TX_DEVICE_TYPES[tx], 1 if on else 0])
    return Exchange(
        label=f"set-tx-mute {tx} {'on' if on else 'off'}",
        request_name="set-tx-mute",
        request_frame=build_v2_frame(22, payload, feature_len),
    )


def set_voice_mode_exchange(mode: str, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-voice-mode {mode}",
        request_name="set-voice-mode",
        request_frame=build_v2_frame(1, bytes([VOICE_MODE_VALUES[mode]]), feature_len),
    )


def set_signal_mode_exchange(mode: str, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-signal-mode {mode}",
        request_name="set-signal-mode",
        request_frame=build_v2_frame(63, bytes([SIGNAL_MODE_VALUES[mode]]), feature_len),
    )


def set_eq_exchange(preset: str, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-eq {preset}",
        request_name="set-eq",
        request_frame=build_v2_frame(7, bytes([EQ_VALUES[preset]]), feature_len),
    )


def set_shutdown_time_exchange(mode: str, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-shutdown-time {mode}",
        request_name="set-shutdown-time",
        request_frame=build_v2_frame(39, bytes([SHUTDOWN_VALUES[mode]]), feature_len),
    )


def set_voice_level_exchange(value: int, feature_len: int = FEATURE_LEN) -> Exchange:
    return Exchange(
        label=f"set-voice-level {value}",
        request_name="set-voice-level",
        request_frame=build_v2_frame(3, bytes([value & 0xFF]), feature_len),
    )
