#!/bin/bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILD="$ROOT/build/appimage"
TOOLS="$BUILD/tools"
VERSION=${VERSION:-0.1.0}
ARCH=x86_64
PORTABLE="$ROOT/build/portable/env"
if [ -z "${PYTHON:-}" ] && [ -x "$PORTABLE/bin/python" ]; then
    PYTHON="$PORTABLE/bin/python"
    PYINSTALLER_DIR=${PYINSTALLER_DIR:-$PORTABLE/lib/python3.12/site-packages}
    PRUNE_GLIBC=${PRUNE_GLIBC:-2.34}
    LD_LIBRARY_PATH="$PORTABLE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export LD_LIBRARY_PATH
fi
PYTHON=${PYTHON:-python3}
PYINSTALLER_DIR=${PYINSTALLER_DIR:-}
OUT="$ROOT/dist/TouchKeyboard-$VERSION-$ARCH.AppImage"
TOOL="$TOOLS/appimagetool-$ARCH.AppImage"
TOOL_DIR="$TOOLS/appimagetool-$ARCH"
RUNTIME="$TOOLS/runtime-$ARCH"

mkdir -p "$BUILD" "$TOOLS" "$ROOT/dist"

if ! "$PYTHON" -c "import PySide6" >/dev/null 2>&1; then
    echo "PySide6 is required: $PYTHON -m pip install -r $ROOT/requirements.txt" >&2
    exit 1
fi

if [ -z "$PYINSTALLER_DIR" ]; then
    PYINSTALLER_DIR="$TOOLS/pyinstaller"
    if ! PYTHONPATH="$PYINSTALLER_DIR" "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
        echo "Installing PyInstaller..."
        rm -rf "$PYINSTALLER_DIR"
        "$PYTHON" -m pip install --quiet --target "$PYINSTALLER_DIR" pyinstaller \
            || "$PYTHON" -m pip install --quiet --target "$PYINSTALLER_DIR" --break-system-packages pyinstaller
    fi
fi
if ! PYTHONPATH="$PYINSTALLER_DIR" "$PYTHON" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller is not available in $PYINSTALLER_DIR" >&2
    exit 1
fi

echo "Building application bundle..."
rm -rf "$BUILD/dist" "$BUILD/work"
PYTHONPATH="$PYINSTALLER_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    "$PYTHON" -m PyInstaller --clean --noconfirm \
    --distpath "$BUILD/dist" --workpath "$BUILD/work" \
    "$ROOT/packaging/touch-keyboard.spec"

if [ -n "${PRUNE_GLIBC:-}" ]; then
echo "Pruning bundled libraries that need a newer glibc than $PRUNE_GLIBC..."
"$PYTHON" - "$BUILD/dist/touch-keyboard/_internal" "$PRUNE_GLIBC" <<'PY'
import re
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
target = tuple(int(part) for part in sys.argv[2].split("."))
removed = []
remaining = []

for path in sorted(root.rglob("*")):
    if not path.is_file() or path.is_symlink():
        continue
    try:
        with open(path, "rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
    except OSError:
        continue
    result = subprocess.run(["objdump", "-T", str(path)], capture_output=True, text=True)
    versions = re.findall(r"GLIBC_([0-9.]+)", result.stdout)
    if not versions:
        continue
    top = max(tuple(int(part) for part in value.split(".")) for value in versions)
    if top <= target:
        remaining.append((top, path))
        continue
    if path.name == "touch-keyboard" or path.name.startswith("libpython"):
        print(f"refusing to remove {path} with glibc {'.'.join(map(str, top))}", file=sys.stderr)
        raise SystemExit(1)
    removed.append((top, path))

for top, path in removed:
    path.unlink()
for path in sorted(root.rglob("*")):
    if path.is_symlink() and not path.exists():
        path.unlink()
for top, path in remaining:
    if not path.exists():
        continue
print(f"Removed {len(removed)} libraries newer than glibc {sys.argv[2]}")
for top, path in removed[:12]:
    print(f"  {'.'.join(map(str, top))} {path.relative_to(root)}")
worst = max((top for top, path in remaining if path.exists()), default=(0,))
print("Highest remaining bundled glibc:", ".".join(map(str, worst)))
PY
fi

APPDIR="$BUILD/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -a "$BUILD/dist/touch-keyboard" "$APPDIR/usr/lib/touch-keyboard"

if [ "${BUNDLE_XCB:-1}" = "1" ]; then
QT_LIB="$APPDIR/usr/lib/touch-keyboard/_internal/PySide6/Qt/lib"
PLATFORMS="$APPDIR/usr/lib/touch-keyboard/_internal/PySide6/Qt/plugins/platforms"
"$PYTHON" - "$QT_LIB" "$PLATFORMS" <<'PY'
import shutil
import subprocess
import sys
from pathlib import Path

destination = Path(sys.argv[1])
platforms = Path(sys.argv[2])
skip = {"libxcb.so.1"}
copied = set()
for plugin in sorted(platforms.glob("libq*.so")):
    result = subprocess.run(["ldd", str(plugin)], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if "=>" not in line:
            continue
        name, rest = line.split("=>", 1)
        path = rest.strip().split(" ")[0]
        name = name.strip()
        if not path.startswith("/"):
            continue
        if not (name.startswith("libxcb") or name.startswith("libxkbcommon")):
            continue
        if name in skip or (destination / name).exists():
            continue
        shutil.copy2(path, destination / name)
        copied.add(name)
print(f"Bundled {len(copied)} X11/xkb helper libraries")
PY
else
echo "Skipping host X11/xkb helper libraries"
fi

cat > "$APPDIR/usr/bin/touch-keyboard" <<'EOS'
#!/bin/sh
SELF=$(readlink -f "$0")
exec "$(dirname "$SELF")/../lib/touch-keyboard/touch-keyboard" "$@"
EOS
chmod 755 "$APPDIR/usr/bin/touch-keyboard"

cat > "$APPDIR/AppRun" <<'EOS'
#!/bin/sh
HERE=$(dirname "$(readlink -f "$0")")
export LD_LIBRARY_PATH="$HERE/usr/lib/touch-keyboard/_internal/PySide6/Qt/lib:${LD_LIBRARY_PATH:-}"
exec "$HERE/usr/bin/touch-keyboard" "$@"
EOS
chmod 755 "$APPDIR/AppRun"

cat > "$APPDIR/linux-touch-keyboard.desktop" <<EOS
[Desktop Entry]
Type=Application
Name=Touch Keyboard
Name[zh_CN]=触摸键盘
Comment=On-screen keyboard for X11 and Wayland
Exec=touch-keyboard
Icon=linux-touch-keyboard
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=false
X-AppImage-Version=$VERSION
EOS
cp "$APPDIR/linux-touch-keyboard.desktop" "$APPDIR/usr/share/applications/"

cp "$ROOT/assets/icon-256.png" "$APPDIR/linux-touch-keyboard.png"
cp "$ROOT/assets/icon.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/linux-touch-keyboard.svg"
for size in 16 24 32 48 64 128 256 512; do
    target="$APPDIR/usr/share/icons/hicolor/${size}x${size}/apps"
    mkdir -p "$target"
    cp "$ROOT/assets/icon-$size.png" "$target/linux-touch-keyboard.png"
done

if [ ! -x "$TOOL" ]; then
    echo "Downloading appimagetool..."
    curl -L --fail --silent --show-error --output "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod 755 "$TOOL"
fi

if [ ! -x "$TOOL_DIR/AppRun" ]; then
    echo "Extracting appimagetool..."
    rm -rf "$TOOLS/squashfs-root"
    (cd "$TOOLS" && "$TOOL" --appimage-extract >/dev/null)
    mv "$TOOLS/squashfs-root" "$TOOL_DIR"
fi

if [ ! -s "$RUNTIME" ]; then
    for candidate in "$BUILD/TouchKeyboard-$VERSION-$ARCH.AppImage" "$BUILD"/TouchKeyboard-*.AppImage; do
        [ -f "$candidate" ] || continue
        size=$("$PYTHON" - "$candidate" <<'PY'
import struct
import sys

with open(sys.argv[1], "rb") as stream:
    header = stream.read(64)
if header[:4] != b"\x7fELF":
    raise SystemExit(1)
endian = "<" if header[5] == 1 else ">"
if header[4] == 2:
    shoff = struct.unpack_from(endian + "Q", header, 0x28)[0]
    shentsize = struct.unpack_from(endian + "H", header, 0x3A)[0]
    shnum = struct.unpack_from(endian + "H", header, 0x3C)[0]
else:
    shoff = struct.unpack_from(endian + "I", header, 0x20)[0]
    shentsize = struct.unpack_from(endian + "H", header, 0x2E)[0]
    shnum = struct.unpack_from(endian + "H", header, 0x30)[0]
print(shoff + shentsize * shnum)
PY
) || continue
        if [ -n "$size" ] && [ "$size" -gt 0 ]; then
            head -c "$size" "$candidate" > "$RUNTIME"
            chmod 755 "$RUNTIME"
            break
        fi
    done
fi
if [ ! -s "$RUNTIME" ]; then
    echo "Downloading AppImage runtime..."
    curl -L --fail --silent --show-error --retry 2 --max-time 120 \
        -o "$RUNTIME" "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-$ARCH" \
        || rm -f "$RUNTIME"
fi
if [ ! -s "$RUNTIME" ]; then
    echo "Could not obtain runtime-$ARCH" >&2
    exit 1
fi

echo "Creating AppImage..."
rm -f "$OUT"
STAGE=$(mktemp -d /tmp/touch-keyboard-appimage.XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
ln -s "$APPDIR" "$STAGE/AppDir"
ln -s "$RUNTIME" "$STAGE/runtime"
ARCH="$ARCH" "$TOOL_DIR/AppRun" --no-appstream \
    --runtime-file "$STAGE/runtime" "$STAGE/AppDir" "$STAGE/out.AppImage"
mv "$STAGE/out.AppImage" "$OUT"
rm -rf "$STAGE"
trap - EXIT
chmod 755 "$OUT"
sha256sum "$OUT" > "$OUT.sha256"

echo "Smoke testing the AppImage..."
APPIMAGE_EXTRACT_AND_RUN=1 QT_QPA_PLATFORM=offscreen "$OUT" --check >/dev/null
APPIMAGE_EXTRACT_AND_RUN=1 QT_QPA_PLATFORM=offscreen "$OUT" --dry-run \
    --screenshot "$BUILD/smoke.png" >/dev/null 2>&1

echo "Built: $OUT"
echo "Checksum: $OUT.sha256"
du -h "$OUT"
