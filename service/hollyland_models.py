"""Pydantic models for the Hollyland widget API boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UsbDevice(ApiModel):
    sysfs_name: str
    bus: int
    dev: int
    usb_dev: str
    manufacturer: str | None = None
    product: str | None = None
    serial: str | None = None
    interface0_driver: str | None = None


class UsbPermission(ApiModel):
    path: str
    exists: bool
    readable: bool
    writable: bool
    mode: str | None = None


class HeartInfo(ApiModel):
    tx1_status: bool | None = None
    tx1_battery: int | None = None
    tx1_mute: bool | None = None
    tx2_status: bool | None = None
    tx2_battery: int | None = None
    tx2_mute: bool | None = None
    tx3_status: bool | None = None
    tx3_battery: int | None = None
    tx3_mute: bool | None = None
    tx4_status: bool | None = None
    tx4_battery: int | None = None
    tx4_mute: bool | None = None
    noise_enabled: bool | None = None
    noise_level: int | None = None
    voice_level: int | None = None
    voice_mode: int | None = None
    voice_mode_name: str | None = None
    signal_mode: int | None = None
    signal_mode_name: str | None = None
    eq_level: int | None = None
    eq_level_name: str | None = None
    shutdown_time: int | None = None
    shutdown_time_name: str | None = None
    light_enabled: bool | None = None
    tx_identify_enabled: bool | None = None
    reverb_enabled: bool | None = None
    reverb_level: int | None = None


class Summary(ApiModel):
    vendor_id: str
    product_id: str
    usb: list[UsbDevice]
    permissions_ok: bool
    suggested_chmod: str | None = None
    probe_ok: bool
    probe_error: str | None = None
    transport: Literal["usb_control"] | None = None
    rx_sn: str | None = None
    rx_version: str | None = None
    rx_mac: str | None = None
    performance_mode: int | None = None
    heart_info: HeartInfo | None = None


class SetResult(ApiModel):
    ok: bool
    action: str
    transport: Literal["usb_control"] = "usb_control"
    ack_ok: bool | None = None
    status_byte: int | None = None
    heart_info: HeartInfo | None = None
