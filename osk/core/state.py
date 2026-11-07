from __future__ import annotations

import time
from collections.abc import Callable

MOD_OFF = 0
MOD_PRESSED = 1
MOD_ONCE = 2
MOD_LOCKED = 3

CAPS_CODE = 58
SUPER_CODE = 125
REPEAT_VALUE = 2
MODIFIER_MODES = ("hybrid", "hold", "sticky")


class KeyboardState:
    TAP_MS = 200
    REPEAT_DELAY_MS = 400
    REPEAT_INTERVAL_MS = 40

    def __init__(
        self,
        modifier_codes: set[int] | frozenset[int],
        sink: Callable[[int, int], None],
        now: Callable[[], float] = time.monotonic,
        mode: str = "hybrid",
    ):
        self.modifier_codes = set(modifier_codes)
        self.sink = sink
        self.now = now
        self.mode = mode if mode in MODIFIER_MODES else "hybrid"
        self.mods: dict[int, int] = {}
        self.caps = False
        self.down_keys: set[int] = set()
        self.repeat_due: dict[int, float] = {}
        self.press_at: dict[int, float] = {}
        self.super_release_at: float | None = None
        self.last_event: tuple[int, int] | None = None

    def _emit(self, code: int, value: int) -> None:
        self.last_event = (code, value)
        self.sink(code, value)

    def mod_state(self, code: int) -> int:
        return self.mods.get(code, MOD_OFF)

    def lit(self, code: int) -> bool:
        if code == CAPS_CODE:
            return self.caps
        return self.mod_state(code) != MOD_OFF

    def locked(self, code: int) -> bool:
        if code == CAPS_CODE:
            return self.caps
        return self.mod_state(code) == MOD_LOCKED

    def shifted(self) -> bool:
        return any(state != MOD_OFF for code, state in self.mods.items() if code in (42, 54))

    def set_mode(self, mode: str) -> None:
        if mode not in MODIFIER_MODES or mode == self.mode:
            return
        for code, state in list(self.mods.items()):
            if state != MOD_OFF:
                self._emit(code, 0)
        self.mods.clear()
        self.press_at.clear()
        self.super_release_at = None
        self.mode = mode

    def key_down(self, code: int) -> None:
        stamp = self.now()
        if code in self.modifier_codes:
            state = self.mod_state(code)
            if self.mode == "hold":
                if state == MOD_OFF:
                    self._emit(code, 1)
                    self.mods[code] = MOD_PRESSED
                    self.press_at[code] = stamp
                return
            if self.mode == "sticky":
                if state in (MOD_ONCE, MOD_LOCKED):
                    self._emit(code, 0)
                    self.mods[code] = MOD_OFF
                    self.super_release_at = None
                elif state == MOD_OFF:
                    self._emit(code, 1)
                    self.mods[code] = MOD_ONCE
                    self.press_at[code] = stamp
                return
            if code == SUPER_CODE:
                if state == MOD_OFF:
                    self._emit(code, 1)
                    self.mods[code] = MOD_PRESSED
                    self.press_at[code] = stamp
                elif state == MOD_ONCE:
                    self.mods[code] = MOD_LOCKED
                    self.super_release_at = None
                elif state == MOD_LOCKED:
                    self._emit(code, 0)
                    self.mods[code] = MOD_OFF
                    self.super_release_at = None
                return
            if state == MOD_OFF:
                self._emit(code, 1)
                self.mods[code] = MOD_PRESSED
                self.press_at[code] = stamp
            elif state == MOD_ONCE:
                self.mods[code] = MOD_LOCKED
            elif state == MOD_LOCKED:
                self._emit(code, 0)
                self.mods[code] = MOD_OFF
            return

        if code == CAPS_CODE:
            return
        if self.mods.get(SUPER_CODE) == MOD_ONCE:
            self.super_release_at = None
        if code in self.down_keys:
            return

        self._emit(code, 1)
        self.down_keys.add(code)
        self.press_at[code] = stamp
        self.repeat_due[code] = stamp + self.REPEAT_DELAY_MS / 1000.0

    def key_up(self, code: int) -> None:
        stamp = self.now()
        if code in self.modifier_codes:
            state = self.mod_state(code)
            if self.mode == "hold":
                if state != MOD_OFF:
                    self._emit(code, 0)
                    self.mods[code] = MOD_OFF
                self.press_at.pop(code, None)
                self.super_release_at = None
                return
            if self.mode == "sticky":
                if state == MOD_ONCE and code == SUPER_CODE:
                    self.super_release_at = stamp + 0.5
                return
            if state == MOD_PRESSED:
                held_ms = (stamp - self.press_at.pop(code, stamp)) * 1000.0
                if held_ms < self.TAP_MS:
                    self.mods[code] = MOD_ONCE
                    if code == SUPER_CODE:
                        self.super_release_at = stamp + 0.5
                else:
                    self._emit(code, 0)
                    self.mods[code] = MOD_OFF
            return

        if code == CAPS_CODE:
            self.caps = not self.caps
            self.release_once_modifiers()
            return
        if code not in self.down_keys:
            return

        self._emit(code, 0)
        self.down_keys.discard(code)
        self.press_at.pop(code, None)
        self.repeat_due.pop(code, None)
        self.release_once_modifiers()

    def release_once_modifiers(self) -> None:
        for code, state in list(self.mods.items()):
            if state == MOD_ONCE:
                self._emit(code, 0)
                self.mods[code] = MOD_OFF
                if code == SUPER_CODE:
                    self.super_release_at = None

    def tick(self, stamp: float | None = None) -> None:
        stamp = self.now() if stamp is None else stamp
        if self.super_release_at is not None and stamp >= self.super_release_at:
            if self.mods.get(SUPER_CODE) == MOD_ONCE:
                self._emit(SUPER_CODE, 0)
                self.mods[SUPER_CODE] = MOD_OFF
            self.super_release_at = None
        for code in list(self.down_keys):
            due = self.repeat_due.get(code)
            if due is None or stamp < due:
                continue
            self._emit(code, REPEAT_VALUE)
            interval = self.REPEAT_INTERVAL_MS / 1000.0
            while due <= stamp:
                due += interval
            self.repeat_due[code] = due

    def release_all(self) -> None:
        for code in sorted(self.down_keys):
            self._emit(code, 0)
        for code, state in list(self.mods.items()):
            if state != MOD_OFF:
                self._emit(code, 0)
        self.down_keys.clear()
        self.repeat_due.clear()
        self.press_at.clear()
        self.mods.clear()
        self.super_release_at = None
