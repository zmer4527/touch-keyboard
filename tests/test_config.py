import json

from osk.config import Config, load_config, save_config


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config = Config(lang="zh", width=1234, x=-20, y=48, fn_visible=False, palm_limit=75, opacity=60, pin_candidates=True, track_keyboard=False, modifier_mode="sticky")
    save_config(config, path)
    assert load_config(path) == config


def test_missing_and_broken_files_use_defaults(tmp_path):
    path = tmp_path / "config.json"
    assert load_config(path) == Config()
    path.write_text("{not json", encoding="utf-8")
    assert load_config(path) == Config()


def test_invalid_values_are_clamped(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "lang": "de",
                "width": 100,
                "x": "left",
                "fn_visible": "yes",
                "palm_limit": -1,
                "opacity": 5,
            }
        ),
        encoding="utf-8",
    )
    assert load_config(path) == Config()


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"lang": "zh", "extra": True}), encoding="utf-8")
    assert load_config(path).lang == "zh"


def test_windows_config_path(tmp_path, monkeypatch):
    from osk.config import default_config_path

    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_config_path("nt") == tmp_path / "linux-touch-keyboard" / "config.json"


def test_track_keyboard_defaults_on():
    from osk.config import Config

    assert Config().track_keyboard is True
