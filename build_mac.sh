#!/usr/bin/env bash
# بناء نسخة macOS (.app ثم .dmg) لبرنامج موسم الحج.
# شغّله على جهاز ماك:   bash build_mac.sh   (أو  chmod +x build_mac.sh && ./build_mac.sh)
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "   HajjApp - macOS build (.app + .dmg)"
echo "============================================"

# 1) بيئة بايثون + المكتبات
if [ ! -d ".venv" ]; then
  echo "[1/5] Creating virtual environment..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "[2/5] Installing dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt pyinstaller

# 2) أيقونة التطبيق (.icns) من logo.png
ICON_PNG="hajj_app/assets/logo.png"
ICON_ICNS="hajj_app/assets/logo.icns"
if [ -f "$ICON_PNG" ] && [ ! -f "$ICON_ICNS" ] && command -v iconutil >/dev/null; then
  echo "[3/5] Generating app icon (.icns)..."
  WORK="$(mktemp -d)"
  ICONSET="$WORK/icon.iconset"
  mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z "$s" "$s" "$ICON_PNG" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z "$d" "$d" "$ICON_PNG" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$ICON_ICNS" && echo "  -> $ICON_ICNS"
else
  echo "[3/5] Skipping icon generation (already present or iconutil missing)."
fi

# 3) بناء الحزمة .app
echo "[4/5] Building HajjApp.app (PyInstaller)..."
python -m PyInstaller --noconfirm --clean HajjApp-mac.spec

# 4) تغليف .dmg (بسحب التطبيق إلى Applications)
echo "[5/5] Packaging DMG..."
mkdir -p Output
DMG="Output/HajjApp-mac.dmg"
rm -f "$DMG"
STAGE="$(mktemp -d)/dmg"
mkdir -p "$STAGE"
cp -R "dist/HajjApp.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "HajjApp" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

echo ""
echo "============================================"
echo "   Done."
echo "   App:  dist/HajjApp.app"
echo "   DMG:  $DMG"
echo "   افتح الـDMG واسحب HajjApp إلى Applications."
echo "============================================"
