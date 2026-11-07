from __future__ import annotations

from osk.core.state import KeyboardState


class TouchRouter:
    def __init__(self, state: KeyboardState):
        self.state = state
        self.owner_by_touch: dict[int, int] = {}
        self.touch_by_key: dict[int, int] = {}

    def move(self, touch_id: int, code: int | None) -> None:
        current = self.owner_by_touch.get(touch_id)
        if current == code:
            return
        if current is not None:
            self.release(touch_id)
        if code is None or code in self.touch_by_key:
            return
        self.owner_by_touch[touch_id] = code
        self.touch_by_key[code] = touch_id
        self.state.key_down(code)

    def release(self, touch_id: int) -> None:
        code = self.owner_by_touch.pop(touch_id, None)
        if code is None:
            return
        self.touch_by_key.pop(code, None)
        self.state.key_up(code)

    def cancel_all(self) -> None:
        for touch_id in list(self.owner_by_touch):
            self.release(touch_id)
        self.state.release_all()
