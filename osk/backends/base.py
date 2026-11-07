from __future__ import annotations


class KeyBackend:
    name = "none"

    def key(self, code: int, value: int) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class DryRunBackend(KeyBackend):
    name = "dry-run"

    def __init__(self, reason: str = ""):
        self.reason = reason
        self.events: list[tuple[int, int]] = []

    def key(self, code: int, value: int) -> None:
        self.events.append((code, value))
