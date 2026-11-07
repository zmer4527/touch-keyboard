from __future__ import annotations

import fcntl
import os
import struct

from osk.backends.base import DryRunBackend, KeyBackend

EV_SYN = 0
EV_KEY = 1
EV_REP = 20
SYN_REPORT = 0
BUS_USB = 3
KEY_MAX = 255


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


UI_SET_EVBIT = _ioc(1, "U", 100, 4)
UI_SET_KEYBIT = _ioc(1, "U", 101, 4)
UI_DEV_CREATE = _ioc(0, "U", 1, 0)
UI_DEV_DESTROY = _ioc(0, "U", 2, 0)
DEVICE_PATHS = ("/dev/uinput", "/dev/input/uinput")
UDEV_HINT = 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"'

EVENT = struct.Struct("llHHi")
USER_DEV = struct.Struct("80sHHHHI64i64i64i64i")

assert EVENT.size == 24, EVENT.size
assert USER_DEV.size == 1116, USER_DEV.size


def available_path() -> str | None:
    for path in DEVICE_PATHS:
        if os.access(path, os.W_OK):
            return path
    return None


class UinputBackend(KeyBackend):
    name = "uinput"

    def __init__(self):
        self.fd = -1
        self.created = False
        last: Exception | None = None
        for path in DEVICE_PATHS:
            try:
                self.fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
                break
            except OSError as exc:
                last = exc
        if self.fd < 0:
            raise RuntimeError(
                f"cannot open uinput ({last}). Install the udev rule: {UDEV_HINT}"
            )
        try:
            self._create_device()
        except Exception:
            os.close(self.fd)
            self.fd = -1
            raise

    def _ioctl(self, request: int, value: int = 0) -> None:
        fcntl.ioctl(self.fd, request, value)

    def _create_device(self) -> None:
        self._ioctl(UI_SET_EVBIT, EV_KEY)
        self._ioctl(UI_SET_EVBIT, EV_REP)
        for code in range(KEY_MAX + 1):
            self._ioctl(UI_SET_KEYBIT, code)
        name = b"DroidDeck touch keyboard"
        payload = USER_DEV.pack(
            name, BUS_USB, 0x1209, 0x0001, 1, 0, *([0] * 256)
        )
        os.write(self.fd, payload)
        self._ioctl(UI_DEV_CREATE)
        self.created = True

    def _event(self, event_type: int, code: int, value: int) -> None:
        os.write(self.fd, EVENT.pack(0, 0, event_type, code, value))

    def key(self, code: int, value: int) -> None:
        if not 0 <= code <= KEY_MAX:
            raise ValueError(f"evdev code out of range: {code}")
        self._event(EV_KEY, code, value)
        self._event(EV_SYN, SYN_REPORT, 0)

    def close(self) -> None:
        if self.fd < 0:
            return
        try:
            if self.created:
                self._ioctl(UI_DEV_DESTROY)
        except OSError:
            pass
        finally:
            os.close(self.fd)
            self.fd = -1
            self.created = False


def open_backend(force_dry_run: bool = False) -> KeyBackend:
    if force_dry_run:
        return DryRunBackend("forced dry run")
    try:
        return UinputBackend()
    except Exception as exc:
        return DryRunBackend(str(exc))
