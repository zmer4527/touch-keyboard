from __future__ import annotations

import fcntl
import glob
import os
import select
import struct
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

EV_KEY = 1
KEY_A = 30
KEY_SPACE = 57
KEY_MAX = 0x2FF
KEY_BYTES = (KEY_MAX + 8) // 8
LED_CAPSL = 0x02
INPUT_EVENT = struct.Struct("llHHi")
DEFAULT_EXCLUDES = ("DroidDeck",)


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


EVIOCGNAME = _ioc(2, "E", 0x06, 256)
EVIOCGBIT_KEY = _ioc(2, "E", 0x20 + EV_KEY, KEY_BYTES)
EVIOCGLED = _ioc(2, "E", 0x19, 8)


def parse_events(buffer: bytearray) -> list[tuple[int, int, int]]:
    events = []
    offset = 0
    while len(buffer) - offset >= INPUT_EVENT.size:
        _sec, _usec, event_type, code, value = INPUT_EVENT.unpack_from(buffer, offset)
        events.append((event_type, code, value))
        offset += INPUT_EVENT.size
    if offset:
        del buffer[:offset]
    return events


def _device_name(fd: int) -> str:
    buffer = bytearray(256)
    fcntl.ioctl(fd, EVIOCGNAME, buffer, True)
    return bytes(buffer).split(b"\0", 1)[0].decode(errors="replace")


def _has_key(fd: int, code: int) -> bool:
    buffer = bytearray(KEY_BYTES)
    fcntl.ioctl(fd, EVIOCGBIT_KEY, buffer, True)
    return bool(buffer[code // 8] & (1 << (code % 8)))


def _is_keyboard(fd: int) -> bool:
    return _has_key(fd, KEY_A) and _has_key(fd, KEY_SPACE)


def _caps_led(fd: int) -> bool:
    buffer = bytearray(8)
    fcntl.ioctl(fd, EVIOCGLED, buffer, True)
    return bool(buffer[0] & LED_CAPSL)


def readable_keyboards(paths: list[str] | None = None) -> list[tuple[str, str]]:
    targets = sorted(glob.glob("/dev/input/event*")) if paths is None else paths
    found = []
    for path in targets:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            name = _device_name(fd)
            if _is_keyboard(fd):
                found.append((path, name))
        except OSError:
            continue
        finally:
            os.close(fd)
    return found


class KeyboardMonitor(QObject):
    key = Signal(int, int)
    caps = Signal(bool)
    status = Signal(str)

    def __init__(
        self,
        devices: list[str] | None = None,
        excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
    ):
        super().__init__()
        self.devices = [str(Path(path)) for path in devices] if devices else None
        self.excludes = excludes
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._open: dict[int, tuple[str, bytearray]] = {}
        self._down: dict[str, set[int]] = {}
        self._counts: dict[int, int] = {}
        self._reported = -1

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="osk-evdev", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._scan()
                if not self._open:
                    self._stop.wait(1.0)
                    continue
                try:
                    ready, _, _ = select.select(list(self._open), [], [], 0.5)
                except (OSError, ValueError):
                    ready = []
                for fd in ready:
                    self._read(fd)
        finally:
            for fd in list(self._open):
                self._drop(fd)

    def _scan(self) -> None:
        targets = self.devices or sorted(glob.glob("/dev/input/event*"))
        open_paths = {entry[0] for entry in self._open.values()}
        for path in targets:
            if path in open_paths or self._stop.is_set():
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            try:
                name = _device_name(fd)
                keyboard = _is_keyboard(fd)
            except OSError:
                os.close(fd)
                continue
            if any(name.startswith(prefix) for prefix in self.excludes) or not keyboard:
                os.close(fd)
                continue
            self._open[fd] = (path, bytearray())
            self._down.setdefault(path, set())
            try:
                if _caps_led(fd):
                    self.caps.emit(True)
            except OSError:
                pass
        self._report()

    def _report(self) -> None:
        count = len(self._open)
        if count == self._reported:
            return
        self._reported = count
        if count:
            self.status.emit(f"tracking {count} physical keyboard device(s)")
        else:
            self.status.emit(
                "physical keyboard tracking unavailable (no readable /dev/input/event*)"
            )

    def _read(self, fd: int) -> None:
        entry = self._open.get(fd)
        if entry is None:
            return
        path, buffer = entry
        try:
            data = os.read(fd, INPUT_EVENT.size * 64)
        except OSError:
            self._drop(fd)
            return
        if not data:
            self._drop(fd)
            return
        buffer.extend(data)
        for event_type, code, value in parse_events(buffer):
            if event_type == EV_KEY:
                self._key(path, code, value)

    def _key(self, path: str, code: int, value: int) -> None:
        if value == 2:
            return
        down = self._down.setdefault(path, set())
        if value == 1:
            if code in down:
                return
            down.add(code)
            count = self._counts.get(code, 0) + 1
            self._counts[code] = count
            if count == 1:
                self.key.emit(code, 1)
        elif value == 0 and code in down:
            down.remove(code)
            self._release(code)

    def _release(self, code: int) -> None:
        count = self._counts.get(code, 0) - 1
        if count > 0:
            self._counts[code] = count
            return
        self._counts.pop(code, None)
        self.key.emit(code, 0)

    def _drop(self, fd: int) -> None:
        entry = self._open.pop(fd, None)
        if entry is None:
            return
        path, _buffer = entry
        try:
            os.close(fd)
        except OSError:
            pass
        for code in list(self._down.pop(path, set())):
            self._release(code)
