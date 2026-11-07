from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from osk.paths import resource_root

DEFAULT_LAYOUT = resource_root() / "layout.json"


@dataclass(frozen=True)
class Key:
    label: str
    evdev: int
    weight: float = 1.0
    label_id: str | None = None
    label_zh: str | None = None
    shifted: str | None = None


@dataclass(frozen=True)
class Layout:
    name: str
    name_zh: str
    hide: str
    hide_zh: str
    modifier_codes: frozenset[int]
    rows: tuple[tuple[Key, ...], ...]

    @property
    def keys(self) -> tuple[Key, ...]:
        return tuple(key for row in self.rows for key in row)

    def title(self, lang: str = "en") -> str:
        return self.name_zh if lang == "zh" else self.name

    def hide_text(self, lang: str = "en") -> str:
        return self.hide_zh if lang == "zh" else self.hide

    def label(self, key: Key, lang: str = "en", shift: bool = False, caps: bool = False) -> str:
        text = key.label_zh if lang == "zh" and key.label_zh else key.label
        if shift and key.shifted:
            return key.shifted
        if len(text) == 1 and text.isalpha():
            return text.upper() if (shift ^ caps) else text.lower()
        return text


def load_layout(path: Path | str = DEFAULT_LAYOUT) -> Layout:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)

    rows: list[tuple[Key, ...]] = []
    for index, row in enumerate(raw.get("rows", [])):
        if not row:
            raise ValueError(f"row {index} is empty")
        keys = []
        for item in row:
            code = item.get("evdev")
            if not isinstance(code, int):
                raise ValueError(f"bad evdev code: {item}")
            weight = float(item.get("weight", 1))
            if weight <= 0:
                raise ValueError(f"bad weight: {item}")
            keys.append(
                Key(
                    label=item["label"],
                    evdev=code,
                    weight=weight,
                    label_id=item.get("label_id"),
                    label_zh=item.get("label_zh"),
                    shifted=item.get("shifted"),
                )
            )
        rows.append(tuple(keys))
    if not rows:
        raise ValueError("layout has no rows")

    return Layout(
        name=raw.get("name", "keyboard"),
        name_zh=raw.get("name_zh", "键盘"),
        hide=raw.get("hide", "Hide"),
        hide_zh=raw.get("hide_zh", "隐藏"),
        modifier_codes=frozenset(raw.get("modifier_codes", [])),
        rows=tuple(rows),
    )
