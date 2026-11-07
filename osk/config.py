from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_ENV = "LINUX_TOUCH_KEYBOARD_CONFIG"


def default_config_path(platform: str | None = None) -> Path:
    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    if (platform or os.name) == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "linux-touch-keyboard" / "config.json"


@dataclass
class Config:
    lang: str = "en"
    width: int = 0
    x: int | None = None
    y: int | None = None
    fn_visible: bool = True
    palm_limit: float = 0.0
    opacity: int = 70
    pin_candidates: bool = False
    track_keyboard: bool = True
    modifier_mode: str = "hybrid"


def _coerce(raw: dict) -> Config:
    config = Config()
    lang = raw.get("lang")
    if lang in ("en", "zh"):
        config.lang = lang
    width = raw.get("width")
    if isinstance(width, int) and 640 <= width <= 5000:
        config.width = width
    for axis in ("x", "y"):
        value = raw.get(axis)
        if isinstance(value, int) and -100000 < value < 100000:
            setattr(config, axis, value)
    if isinstance(raw.get("fn_visible"), bool):
        config.fn_visible = raw["fn_visible"]
    palm = raw.get("palm_limit")
    if isinstance(palm, (int, float)) and 0 <= palm <= 500:
        config.palm_limit = float(palm)
    opacity = raw.get("opacity")
    if isinstance(opacity, int) and 20 <= opacity <= 100:
        config.opacity = opacity
    if isinstance(raw.get("pin_candidates"), bool):
        config.pin_candidates = raw["pin_candidates"]
    if isinstance(raw.get("track_keyboard"), bool):
        config.track_keyboard = raw["track_keyboard"]
    if raw.get("modifier_mode") in ("hybrid", "hold", "sticky"):
        config.modifier_mode = raw["modifier_mode"]
    return config


def load_config(path: Path | str | None = None) -> Config:
    target = Path(path) if path else default_config_path()
    try:
        with open(target, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return Config()
    return _coerce(raw) if isinstance(raw, dict) else Config()


def save_config(config: Config, path: Path | str | None = None) -> None:
    target = Path(path) if path else default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(config), ensure_ascii=False, indent=2) + "\n"
    handle, temporary = tempfile.mkstemp(prefix=".config-", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
