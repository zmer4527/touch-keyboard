#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PREFIX=${PREFIX:-$HOME/.local}
BIN="$PREFIX/bin/linux-touch-keyboard"
DESKTOP="$PREFIX/share/applications/linux-touch-keyboard.desktop"
ICONS="$PREFIX/share/icons/hicolor"
RULE="$ROOT/packaging/udev/60-droiddeck-touch-keyboard.rules"

remove_icons() {
    for size in 16 24 32 48 64 128 256 512; do
        rm -f "$ICONS/${size}x${size}/apps/linux-touch-keyboard.png"
    done
    rm -f "$ICONS/scalable/apps/linux-touch-keyboard.svg"
    rm -f "$ICONS/icon-theme.cache"
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$BIN" "$DESKTOP"
    remove_icons
    echo "Removed $BIN and $DESKTOP"
    exit 0
fi

if [ ! -f "$ROOT/touch_keyboard.py" ] || [ ! -f "$ROOT/layout.json" ]; then
    echo "Run this script from a complete linux-touch-keyboard checkout" >&2
    exit 1
fi

mkdir -p "$PREFIX/bin" "$PREFIX/share/applications"

cat > "$BIN" <<EOS
#!/bin/sh
exec python3 "$ROOT/touch_keyboard.py" "\$@"
EOS
chmod 755 "$BIN"

cat > "$DESKTOP" <<EOS
[Desktop Entry]
Type=Application
Name=Touch Keyboard
Name[zh_CN]=触摸键盘
Comment=On-screen keyboard for X11 and Wayland
Exec="$BIN"
Icon=linux-touch-keyboard
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=false
EOS

for size in 16 24 32 48 64 128 256 512; do
    target="$ICONS/${size}x${size}/apps"
    mkdir -p "$target"
    cp "$ROOT/assets/icon-$size.png" "$target/linux-touch-keyboard.png"
done
mkdir -p "$ICONS/scalable/apps"
cp "$ROOT/assets/icon.svg" "$ICONS/scalable/apps/linux-touch-keyboard.svg"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICONS" >/dev/null 2>&1 || true
fi

echo "Installed $BIN"
echo "Installed $DESKTOP"
echo "Installed icons in $ICONS"
echo
if [ -w /dev/uinput ]; then
    echo "uinput is writable; nothing else to do."
else
    echo "uinput needs permission. Install the rule and reload udev:"
    echo "  sudo install -Dm644 \"$RULE\" /etc/udev/rules.d/60-droiddeck-touch-keyboard.rules"
    echo "  sudo udevadm control --reload-rules && sudo udevadm trigger --name-match=uinput"
fi
