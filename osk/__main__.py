from __future__ import annotations

import argparse
import getpass
import glob
import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QPoint, QProcess, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from osk.config import Config, default_config_path, load_config, save_config
from osk.core.layout import DEFAULT_LAYOUT, Layout, load_layout
from osk.core.state import KeyboardState
from osk.paths import resource_root
from osk.platform.blur import compositor_active, request_blur
from osk.platform.tray import Tray
from osk.ui.icon import app_icon
from osk.ui.qt import KeyboardWindow, default_width

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

ROOT = resource_root()
UDEV_RULE = ROOT / "packaging/udev/60-droiddeck-touch-keyboard.rules"
INSTALLED_RULE = Path("/etc/udev/rules.d/60-droiddeck-touch-keyboard.rules")
IS_WINDOWS = os.name == "nt"


def open_backend(force_dry_run: bool):
    if IS_WINDOWS:
        from osk.backends.windows import open_backend as windows_open

        return windows_open(force_dry_run)
    from osk.backends.uinput import open_backend as linux_open

    return linux_open(force_dry_run)


def uinput_path():
    if IS_WINDOWS:
        return None
    from osk.backends.uinput import available_path

    return available_path()


def monitor_api():
    if IS_WINDOWS:
        from osk.platform.windows_monitor import KeyboardMonitor, readable_keyboards
    else:
        from osk.platform.evdev_monitor import KeyboardMonitor, readable_keyboards
    return KeyboardMonitor, readable_keyboards


def apply_external_config(window, fresh: Config) -> None:
    if fresh.lang in ("en", "zh") and fresh.lang != window.lang:
        window.set_language(fresh.lang)
    if fresh.opacity != window.opacity_percent:
        window.set_opacity(fresh.opacity)
    if fresh.fn_visible != window.fn_visible:
        window.set_fn_visible(fresh.fn_visible)
    if fresh.pin_candidates != window.candidates_requested:
        ok, error = window.set_candidates_enabled(fresh.pin_candidates)
        if not ok:
            print(f"touch-keyboard: {error}", file=sys.stderr)
    if fresh.width > 0 and abs(fresh.width - window.width()) > 2:
        window.set_width_px(fresh.width)
    window.palm_limit = fresh.palm_limit
    if fresh.track_keyboard != window.track_keyboard_enabled:
        window.set_track_keyboard(fresh.track_keyboard)
    if fresh.modifier_mode != window.modifier_mode:
        window.set_modifier_mode(fresh.modifier_mode)


def run_check(layout: Layout) -> int:
    print(f"{layout.name}: {len(layout.rows)} rows, {len(layout.keys)} keys")
    for index, row in enumerate(layout.rows):
        units = sum(key.weight for key in row)
        print(f"  row {index}: {len(row):2d} keys, {units:5.2f} units")
    print("modifier codes:", sorted(layout.modifier_codes))
    return 0


def session_name() -> str:
    if IS_WINDOWS:
        return "windows"
    value = os.environ.get("XDG_SESSION_TYPE")
    if value:
        return value
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def planned_platform(args) -> str | None:
    if IS_WINDOWS:
        return None
    if args.xwayland:
        return "xcb"
    if args.native_wayland or "QT_QPA_PLATFORM" in os.environ:
        return None
    if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
        return "xcb"
    return None


def run_doctor(layout: Layout, config: Config, config_path: Path, args) -> int:
    print("Touch keyboard doctor")
    print(f"  session: {session_name()}")
    if IS_WINDOWS:
        print("  qt platform: windows")
        print("  uinput: not applicable (using SendInput)")
        print("  physical keyboards: polling available")
    else:
        print(f"  wayland display: {os.environ.get('WAYLAND_DISPLAY', '-')}")
        print(f"  x11 display: {os.environ.get('DISPLAY', '-')}")
        platform = planned_platform(args) or os.environ.get("QT_QPA_PLATFORM", "default")
        print(f"  qt platform: {platform}")
        if platform in ("wayland", "default") and session_name() == "wayland":
            print("  note: native Wayland has no layer-shell support; use XWayland for always-on-top")
        device = uinput_path()
        if device:
            print(f"  uinput: {device} writable")
        else:
            print("  uinput: not writable")
            print(f"  udev rule: {UDEV_RULE} ({'installed' if INSTALLED_RULE.is_file() else 'not installed'})")
            print(f"    sudo install -Dm644 {UDEV_RULE} {INSTALLED_RULE}")
            print("    sudo udevadm control --reload-rules && sudo udevadm trigger --name-match=uinput")
        _, readable = monitor_api()
        keyboards = readable(args.keyboard_device)
        print(f"  physical keyboards: {len(keyboards)} readable")
        if not keyboards:
            print("    grant read access to /dev/input/event* (for example the input group) to enable tracking")
    print(f"  layout: {args.layout} ({len(layout.rows)} rows, {len(layout.keys)} keys)")
    print(f"  config: {config_path} ({'present' if config_path.is_file() else 'defaults'})")
    print(
        f"    lang={config.lang} width={config.width or 'auto'} "
        f"fn={config.fn_visible} palm_limit={config.palm_limit:g} "
        f"opacity={config.opacity}%"
    )
    return 0


def print_udev_rule() -> int:
    if IS_WINDOWS:
        print("udev rules are only used on Linux")
        return 0
    print(f"# install to {INSTALLED_RULE}")
    print(UDEV_RULE.read_text(encoding="utf-8").rstrip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DroidDeck PC layout touch keyboard for Linux and Windows"
    )
    parser.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT)
    parser.add_argument("--lang", choices=["en", "zh"])
    parser.add_argument("--check", action="store_true", help="validate the layout and exit")
    parser.add_argument("--doctor", action="store_true", help="report session, uinput and config status")
    parser.add_argument("--print-udev-rule", action="store_true", help="print the uinput udev rule")
    parser.add_argument("--config", type=Path, help="config file path")
    parser.add_argument("--reset-config", action="store_true", help="ignore the saved config")
    parser.add_argument("--screenshot", type=Path, help="render one frame to PNG and exit")
    parser.add_argument("--dry-run", action="store_true", help="do not create a uinput device")
    parser.add_argument("--xwayland", action="store_true", help="force XWayland on Wayland sessions")
    parser.add_argument("--native-wayland", action="store_true", help="keep the native Wayland platform")
    parser.add_argument("--palm-limit", type=float, help="ignore touch points larger than this many pixels")
    parser.add_argument("--opacity", type=int, help="background opacity percent (20-100)")
    parser.add_argument("--no-fn", action="store_true", help="start with the F1-12 row hidden")
    parser.add_argument("--width", type=int, help="window width in pixels")
    parser.add_argument("--exit-after", type=int, default=0, help="close after this many milliseconds")
    parser.add_argument("--no-instance", action="store_true", help="start a separate window instead of toggling a running one")
    parser.add_argument("--quit", action="store_true", help="ask a running window to quit")
    parser.add_argument("--no-tray", action="store_true", help="do not add a system tray icon")
    parser.add_argument("--no-track-keyboard", action="store_true", help="do not highlight physical keyboard input")
    parser.add_argument("--pin-candidates", action="store_true", help="pin Fcitx candidates above the keyboard")
    parser.add_argument("--restore-fcitx", action="store_true", help="re-enable Fcitx classic UI and exit")
    parser.add_argument("--keyboard-device", action="append", help="only monitor this /dev/input/event* device")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    layout = load_layout(args.layout)
    if args.check:
        return run_check(layout)
    if args.print_udev_rule:
        return print_udev_rule()
    if args.restore_fcitx:
        from osk.platform.kimpanel import restore_classicui

        if restore_classicui():
            print("Fcitx classic UI restored")
            return 0
        print("Could not restore Fcitx classic UI", file=sys.stderr)
        return 1

    config_path = args.config or default_config_path()
    config = Config() if args.reset_config else load_config(config_path)
    if args.doctor:
        return run_doctor(layout, config, config_path, args)

    platform = planned_platform(args)
    if platform:
        os.environ["QT_QPA_PLATFORM"] = platform

    app = QApplication([sys.argv[0]])
    app.setFont(QFont("Segoe UI", 10) if IS_WINDOWS else QFont("DejaVu Sans", 10))
    app.setWindowIcon(app_icon())

    session_id = os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY") or "default"
    safe_session = "".join(ch if ch.isalnum() else "_" for ch in session_id)
    user_id = getattr(os, "getuid", lambda: os.environ.get("USERNAME", "user"))()
    instance = f"linux-touch-keyboard-{user_id}-{safe_session}"
    interactive = not (args.screenshot or args.exit_after or args.no_instance)
    if interactive:
        probe = QLocalSocket()
        probe.connectToServer(instance)
        if probe.waitForConnected(200):
            probe.write(b"quit\n" if args.quit else b"toggle\n")
            probe.flush()
            probe.waitForBytesWritten(200)
            probe.disconnectFromServer()
            return 0
        if args.quit:
            print("touch-keyboard: no running window", file=sys.stderr)
            return 1

    backend = open_backend(args.dry_run)
    reason = getattr(backend, "reason", "")
    if reason:
        print(f"touch-keyboard: {backend.name}: {reason}", file=sys.stderr)

    if QApplication.platformName() == "wayland":
        print(
            "touch-keyboard: native Wayland has no layer-shell support; "
            "always-on-top may not work (try --xwayland)",
            file=sys.stderr,
        )

    lang = args.lang or config.lang
    palm_limit = args.palm_limit if args.palm_limit is not None else config.palm_limit
    fn_visible = config.fn_visible and not args.no_fn
    opacity = args.opacity if args.opacity is not None else config.opacity
    notice = "input backend unavailable" if backend.name == "dry-run" and not args.dry_run else ""
    state = KeyboardState(layout.modifier_codes, backend.key, mode=config.modifier_mode)
    window = KeyboardWindow(layout, state, backend, lang, palm_limit, fn_visible, notice, opacity)

    flags = (
        Qt.Tool
        | Qt.FramelessWindowHint
        | Qt.WindowStaysOnTopHint
        | Qt.WindowDoesNotAcceptFocus
    )
    if QApplication.platformName() in ("xcb", "x11"):
        flags |= Qt.X11BypassWindowManagerHint
    window.setWindowFlags(flags)

    screens = app.screens()
    saved = config.x is not None and config.y is not None
    target = app.primaryScreen()
    if saved:
        for screen in screens:
            if screen.availableGeometry().contains(QPoint(config.x, config.y)):
                target = screen
                break
        else:
            saved = False

    if target is not None:
        area = target.availableGeometry()
        width = args.width or config.width or default_width(area)
        width = max(640, min(width, area.width() - 16))
        height = max(300, min(620, int(width * 0.38)))
        height = min(height, area.height() - 16)
        window.resize(width, height)
        if saved:
            x = max(area.left(), min(config.x, area.right() - width))
            y = max(area.top(), min(config.y, area.bottom() - height))
        else:
            x = area.x() + (area.width() - width) // 2
            y = area.y() + area.height() - height - 24
        window.move(x, y)

    monitor = None

    def start_monitor() -> None:
        nonlocal monitor
        if monitor is not None:
            return
        Monitor, _readable = monitor_api()
        device = Monitor(args.keyboard_device)
        device.key.connect(window.external_key)
        device.caps.connect(window.set_external_caps)
        device.status.connect(lambda message: print(f"touch-keyboard: {message}", file=sys.stderr))
        device.start()
        monitor = device

    def stop_monitor() -> None:
        nonlocal monitor
        if monitor is not None:
            monitor.stop()
            monitor = None
        window.clear_external_input()

    def set_tracking(enabled: bool) -> None:
        window.track_keyboard_enabled = bool(enabled)
        if enabled:
            if needs_input_access():
                request_input_access()
            start_monitor()
        else:
            stop_monitor()

    auth_process = None

    def needs_input_access() -> bool:
        if os.name == "nt":
            return False
        if not shutil.which("pkexec") or not glob.glob("/dev/input/event*"):
            return False
        _Monitor, readable = monitor_api()
        return not readable(args.keyboard_device)

    def input_access_finished(code: int, _status) -> None:
        if code == 0:
            print("touch-keyboard: input access granted", file=sys.stderr)
        else:
            print(
                "touch-keyboard: administrator authentication was cancelled or failed",
                file=sys.stderr,
            )

    def request_input_access() -> None:
        nonlocal auth_process
        if auth_process is not None and auth_process.state() != QProcess.ProcessState.NotRunning:
            return
        script = resource_root() / "assets" / "input-access-helper.sh"
        if not script.is_file() or not shutil.which("pkexec"):
            print("touch-keyboard: cannot request input access", file=sys.stderr)
            return
        process = QProcess(app)
        process.setStandardOutputFile(QProcess.nullDevice())
        process.setStandardErrorFile(QProcess.nullDevice())
        process.finished.connect(input_access_finished)
        process.start(
            "pkexec", ["/bin/sh", str(script), getpass.getuser()]
        )
        auth_process = process

    window.on_track_keyboard = set_tracking
    window.track_keyboard_enabled = bool(config.track_keyboard and not args.no_track_keyboard)
    if window.track_keyboard_enabled:
        start_monitor()
        if needs_input_access():
            request_input_access()

    cleaned = False

    def cleanup() -> None:
        nonlocal cleaned
        if cleaned:
            return
        cleaned = True
        stop_monitor()
        if auth_process is not None and auth_process.state() != QProcess.ProcessState.NotRunning:
            auth_process.terminate()
        if tray is not None:
            tray.hide()
        if server is not None:
            server.close()
        pin_candidates = window.candidates_requested
        window.stop_candidates()
        state.release_all()
        backend.close()
        if not args.screenshot:
            config.lang = window.lang
            config.width = window.width()
            config.fn_visible = window.fn_visible
            config.palm_limit = window.palm_limit
            config.opacity = window.opacity_percent
            config.track_keyboard = window.track_keyboard_enabled
            config.modifier_mode = window.modifier_mode
            config.pin_candidates = pin_candidates
            if QApplication.platformName() in ("xcb", "x11", "windows"):
                config.x, config.y = window.x(), window.y()
            else:
                config.x = config.y = None
            try:
                save_config(config, config_path)
            except OSError as exc:
                print(f"touch-keyboard: cannot save config: {exc}", file=sys.stderr)

    def toggle_window() -> None:
        if window.isVisible():
            window.hide()
            state.release_all()
        else:
            window.show()
            window.raise_()

    server: QLocalServer | None = None
    if interactive:
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(instance)

        def on_new_connection() -> None:
            connection = server.nextPendingConnection()
            connection.setParent(server)

            def on_ready() -> None:
                for command in bytes(connection.readAll()).decode(errors="ignore").splitlines():
                    if command == "toggle":
                        toggle_window()
                    elif command == "quit":
                        app.quit()

            connection.readyRead.connect(on_ready)
            connection.disconnected.connect(connection.deleteLater)

        server.newConnection.connect(on_new_connection)
        if not server.listen(instance):
            print(f"touch-keyboard: single instance unavailable: {server.errorString()}", file=sys.stderr)
            server = None

    tray = None
    if not args.no_tray:
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = Tray(window, app)
        else:
            print("touch-keyboard: system tray unavailable", file=sys.stderr)
    window.tray_available = tray is not None

    config_path.parent.mkdir(parents=True, exist_ok=True)
    settings_watcher = QFileSystemWatcher(app)
    settings_watcher.addPath(str(config_path.parent))
    settings_timer = QTimer(app)
    settings_timer.setSingleShot(True)
    settings_timer.setInterval(180)

    def reload_external_config() -> None:
        nonlocal config
        fresh = load_config(config_path)
        apply_external_config(window, fresh)
        config.lang = fresh.lang
        config.width = window.width()
        config.opacity = window.opacity_percent
        config.fn_visible = window.fn_visible
        config.pin_candidates = window.candidates_requested
        config.palm_limit = fresh.palm_limit
        config.modifier_mode = window.modifier_mode
        config.x, config.y = fresh.x, fresh.y

    def settings_changed(_path: str) -> None:
        settings_timer.start()

    settings_timer.timeout.connect(reload_external_config)
    settings_watcher.directoryChanged.connect(settings_changed)

    if args.pin_candidates or config.pin_candidates:
        ok, error = window.set_candidates_enabled(True)
        if not ok:
            print(f"touch-keyboard: {error}", file=sys.stderr)

    app.aboutToQuit.connect(cleanup)
    window.show()

    def apply_appearance() -> None:
        if IS_WINDOWS:
            request_blur(window)
            return
        if session_name() == "x11" and not compositor_active():
            if window.opacity_percent < 100:
                print("touch-keyboard: no X compositor; using an opaque window", file=sys.stderr)
            window.set_opacity(100)
            return
        request_blur(window)

    QTimer.singleShot(0, apply_appearance)

    if args.exit_after > 0:
        def finish() -> None:
            window.close()
            app.quit()

        QTimer.singleShot(args.exit_after, finish)

    if args.screenshot:
        def capture() -> None:
            window.grab().save(str(args.screenshot))
            window.close()
            app.quit()

        QTimer.singleShot(250, capture)

    result = app.exec()
    cleanup()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
