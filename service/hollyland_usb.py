"""USB discovery and usbfs control-transfer transport for Hollyland receivers."""

from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hollyland_models import UsbDevice
from hollyland_models import UsbPermission
from hollyland_protocol import Exchange
from hollyland_protocol import ExchangeResult
from hollyland_protocol import FEATURE_LEN


DEFAULT_VENDOR_ID = 0x3547
DEFAULT_PRODUCT_ID = 0x0407
USB_TRANSPORT_NAME = "usb_control"


@dataclass(frozen=True)
class UsbLayout:
    vendor_id: int
    product_id: int
    usb_devices: list[UsbDevice]
    usb_permissions: list[UsbPermission]

    @property
    def access_ready(self) -> bool:
        return bool(self.usb_permissions) and all(
            entry.exists and entry.readable and entry.writable for entry in self.usb_permissions
        )

    @property
    def suggested_chmod(self) -> str | None:
        targets = [
            entry.path
            for entry in self.usb_permissions
            if entry.exists and not (entry.readable and entry.writable)
        ]
        if not targets:
            return None
        return f"sudo chmod 666 {' '.join(targets)}"


class UsbTransport(Protocol):
    def exchange(self, exchanges: Sequence[Exchange]) -> list[ExchangeResult]:
        """Run one or more V2 frame exchanges and return raw response bytes."""


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def discover_usb_devices(vendor_id: int = DEFAULT_VENDOR_ID, product_id: int = DEFAULT_PRODUCT_ID) -> list[UsbDevice]:
    devices: list[UsbDevice] = []
    root = Path("/sys/bus/usb/devices")
    for device_dir in sorted(root.glob("*")):
        id_vendor = read_text(device_dir / "idVendor")
        id_product = read_text(device_dir / "idProduct")
        if id_vendor is None or id_product is None:
            continue
        if int(id_vendor, 16) != vendor_id or int(id_product, 16) != product_id:
            continue
        busnum = read_text(device_dir / "busnum")
        devnum = read_text(device_dir / "devnum")
        if busnum is None or devnum is None:
            continue

        bus = int(busnum)
        dev = int(devnum)
        usb_dev = f"/dev/bus/usb/{bus:03d}/{dev:03d}"
        iface0 = device_dir.parent / f"{device_dir.name}:1.0"
        driver_link = iface0 / "driver"
        driver = driver_link.resolve().name if driver_link.exists() else None
        devices.append(
            UsbDevice(
                sysfs_name=device_dir.name,
                bus=bus,
                dev=dev,
                usb_dev=usb_dev,
                manufacturer=read_text(device_dir / "manufacturer"),
                product=read_text(device_dir / "product"),
                serial=read_text(device_dir / "serial"),
                interface0_driver=driver,
            )
        )
    return devices


def node_permissions(path: str) -> UsbPermission:
    device_path = Path(path)
    mode = None
    if device_path.exists():
        try:
            mode = oct(device_path.stat().st_mode & 0o777)
        except OSError:
            mode = None
    return UsbPermission(
        path=path,
        exists=device_path.exists(),
        readable=os.access(path, os.R_OK),
        writable=os.access(path, os.W_OK),
        mode=mode,
    )


def discover_layout(vendor_id: int = DEFAULT_VENDOR_ID, product_id: int = DEFAULT_PRODUCT_ID) -> UsbLayout:
    devices = discover_usb_devices(vendor_id, product_id)
    permissions = [node_permissions(device.usb_dev) for device in devices]
    return UsbLayout(
        vendor_id=vendor_id,
        product_id=product_id,
        usb_devices=devices,
        usb_permissions=permissions,
    )


@dataclass(frozen=True)
class Ioctl:
    nr: int
    direction: int
    type_char: str

    ioc_nrbits = 8
    ioc_typebits = 8
    ioc_sizebits = 14
    ioc_nrshift = 0
    ioc_typeshift = ioc_nrshift + ioc_nrbits
    ioc_sizeshift = ioc_typeshift + ioc_typebits
    ioc_dirshift = ioc_sizeshift + ioc_sizebits
    ioc_write = 1
    ioc_read = 2

    def code(self, size: int) -> int:
        return (
            (self.direction << self.ioc_dirshift)
            | (ord(self.type_char) << self.ioc_typeshift)
            | (self.nr << self.ioc_nrshift)
            | (size << self.ioc_sizeshift)
        )


class UsbDevfsCtrlTransfer(ctypes.Structure):
    _fields_ = [
        ("bRequestType", ctypes.c_uint8),
        ("bRequest", ctypes.c_uint8),
        ("wValue", ctypes.c_uint16),
        ("wIndex", ctypes.c_uint16),
        ("wLength", ctypes.c_uint16),
        ("timeout", ctypes.c_uint32),
        ("data", ctypes.c_void_p),
    ]


class UsbDevfsDisconnectClaim(ctypes.Structure):
    _fields_ = [
        ("interface", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("driver", ctypes.c_char * 256),
    ]


USBDEVFS_CONTROL = Ioctl(0, Ioctl.ioc_write | Ioctl.ioc_read, "U").code(ctypes.sizeof(UsbDevfsCtrlTransfer))
USBDEVFS_CLAIMINTERFACE = Ioctl(15, Ioctl.ioc_read, "U").code(ctypes.sizeof(ctypes.c_uint))
USBDEVFS_RELEASEINTERFACE = Ioctl(16, Ioctl.ioc_read, "U").code(ctypes.sizeof(ctypes.c_uint))
USBDEVFS_CONNECT = Ioctl(23, 0, "U").code(0)
USBDEVFS_DISCONNECT_CLAIM = Ioctl(27, Ioctl.ioc_read, "U").code(ctypes.sizeof(UsbDevfsDisconnectClaim))
USBDEVFS_DISCONNECT_CLAIM_IF_DRIVER = 0x01

LIBC = ctypes.CDLL(None, use_errno=True)


class UsbfsTransport:
    def __init__(
        self,
        usb_dev: str,
        *,
        claim_driver: str,
        feature_len: int = FEATURE_LEN,
        w_value: int = 0x0305,
        w_index: int = 0,
        interface: int = 0,
        timeout_ms: int = 1000,
        delay: float = 0.05,
        no_disconnect_claim: bool = False,
        reconnect: bool = True,
    ) -> None:
        self.usb_dev = usb_dev
        self.claim_driver = claim_driver
        self.feature_len = feature_len
        self.w_value = w_value
        self.w_index = w_index
        self.interface = interface
        self.timeout_ms = timeout_ms
        self.delay = delay
        self.no_disconnect_claim = no_disconnect_claim
        self.reconnect = reconnect

    def exchange(self, exchanges: Sequence[Exchange]) -> list[ExchangeResult]:
        fd = os.open(self.usb_dev, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        claimed = False
        try:
            if self.no_disconnect_claim:
                _claim_interface(fd, self.interface)
            else:
                _disconnect_claim_interface(fd, self.interface, self.claim_driver)
            claimed = True
            return [self._execute_exchange(fd, exchange) for exchange in exchanges]
        finally:
            if claimed:
                _release_interface_quietly(fd, self.interface)
                if self.reconnect:
                    _reconnect_kernel_driver_quietly(fd)
            os.close(fd)

    def _execute_exchange(self, fd: int, exchange: Exchange) -> ExchangeResult:
        _usb_control_transfer(
            fd=fd,
            request_type=0x21,
            request=0x09,
            value=self.w_value,
            index=self.w_index,
            data=exchange.request_frame,
            timeout_ms=self.timeout_ms,
        )
        if self.delay > 0:
            time.sleep(self.delay)

        responses: list[bytes] = []
        for read_index in range(max(exchange.read_count, 1)):
            responses.append(
                _usb_control_transfer(
                    fd=fd,
                    request_type=0xA1,
                    request=0x01,
                    value=self.w_value,
                    index=self.w_index,
                    data=b"",
                    timeout_ms=self.timeout_ms,
                    read_len=self.feature_len,
                )
            )
            if self.delay > 0 and read_index + 1 < exchange.read_count:
                time.sleep(self.delay)
        return ExchangeResult(exchange=exchange, responses=tuple(responses))


def default_transport_for_layout(layout: UsbLayout) -> UsbfsTransport:
    if not layout.usb_devices:
        raise FileNotFoundError("no Hollyland USB device found")
    device = layout.usb_devices[0]
    return UsbfsTransport(
        usb_dev=device.usb_dev,
        claim_driver=device.interface0_driver or "usbhid",
    )


def _usb_control_transfer(
    *,
    fd: int,
    request_type: int,
    request: int,
    value: int,
    index: int,
    data: bytes,
    timeout_ms: int,
    read_len: int = 0,
) -> bytes:
    if read_len > 0:
        buffer = ctypes.create_string_buffer(read_len)
        w_length = read_len
    else:
        buffer = ctypes.create_string_buffer(data, len(data))
        w_length = len(data)

    ctrl = UsbDevfsCtrlTransfer(
        bRequestType=request_type,
        bRequest=request,
        wValue=value,
        wIndex=index,
        wLength=w_length,
        timeout=timeout_ms,
        data=ctypes.cast(buffer, ctypes.c_void_p),
    )
    rc = LIBC.ioctl(fd, USBDEVFS_CONTROL, ctypes.byref(ctrl))
    if rc < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    if read_len > 0:
        return bytes(buffer.raw[:rc])
    return b""


def _disconnect_claim_interface(fd: int, interface: int, driver: str) -> None:
    claim = UsbDevfsDisconnectClaim(
        interface=interface,
        flags=USBDEVFS_DISCONNECT_CLAIM_IF_DRIVER,
        driver=driver.encode("ascii"),
    )
    rc = LIBC.ioctl(fd, USBDEVFS_DISCONNECT_CLAIM, ctypes.byref(claim))
    if rc < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _claim_interface(fd: int, interface: int) -> None:
    value = ctypes.c_uint(interface)
    rc = LIBC.ioctl(fd, USBDEVFS_CLAIMINTERFACE, ctypes.byref(value))
    if rc < 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))


def _release_interface_quietly(fd: int, interface: int) -> None:
    value = ctypes.c_uint(interface)
    LIBC.ioctl(fd, USBDEVFS_RELEASEINTERFACE, ctypes.byref(value))


def _reconnect_kernel_driver_quietly(fd: int) -> None:
    LIBC.ioctl(fd, USBDEVFS_CONNECT, 0)
