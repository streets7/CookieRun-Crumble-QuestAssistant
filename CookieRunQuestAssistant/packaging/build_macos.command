#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
PROJECT_DIR="${SCRIPT_DIR:h}"
WORKSPACE_DIR="${PROJECT_DIR:h}"
BUILD_DIR="${CQA_BUILD_DIR:-$WORKSPACE_DIR/보관자료/빌드작업/macos}"
OUTPUT_DIR="$WORKSPACE_DIR/배포/macos"
APP_NAME="CookieRun Crumble Quest Assistant"
export PYINSTALLER_CONFIG_DIR="$BUILD_DIR/pyinstaller-cache"

cd "$PROJECT_DIR"
[[ -f "$PROJECT_DIR/private_config.json" ]] || { echo "private_config.json is required" >&2; exit 1; }
"${CQA_PYTHON:-python3}" -m venv "$BUILD_DIR/venv"
"$BUILD_DIR/venv/bin/python" -m pip install --upgrade pip
"$BUILD_DIR/venv/bin/python" -m pip install -r requirements-build.txt
"$BUILD_DIR/venv/bin/python" -m unittest discover -q
rm -rf "$BUILD_DIR/work" "$BUILD_DIR/spec" "$OUTPUT_DIR"
mkdir -p "$BUILD_DIR/work" "$BUILD_DIR/spec" "$OUTPUT_DIR"

"$BUILD_DIR/venv/bin/pyinstaller" \
  --noconfirm --clean --windowed --onedir \
  --name "$APP_NAME" \
  --osx-bundle-identifier "local.cqa.crumble.questassistant" \
  --paths "$WORKSPACE_DIR" \
  --add-data "$PROJECT_DIR/assets:assets" \
  --add-data "$PROJECT_DIR/vision_ocr:." \
  --add-data "$PROJECT_DIR/private_config.json:." \
  --hidden-import desktop_app \
  --hidden-import release_update \
  --workpath "$BUILD_DIR/work" \
  --specpath "$BUILD_DIR/spec" \
  --distpath "$OUTPUT_DIR" \
  app_entry.py

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString 16.0" "$OUTPUT_DIR/$APP_NAME.app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string 160000" "$OUTPUT_DIR/$APP_NAME.app/Contents/Info.plist"
codesign --force --deep --sign - "$OUTPUT_DIR/$APP_NAME.app"
ditto -c -k --sequesterRsrc --keepParent \
  "$OUTPUT_DIR/$APP_NAME.app" \
  "$OUTPUT_DIR/CookieRun-Crumble-QuestAssistant-macOS-v16.0.zip"
codesign --verify --deep --strict "$OUTPUT_DIR/$APP_NAME.app"
CQA_DATA_DIR="$BUILD_DIR/self-test" "$OUTPUT_DIR/$APP_NAME.app/Contents/MacOS/$APP_NAME" --self-test
STAGE_DIR="$BUILD_DIR/installer"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"
ditto "$OUTPUT_DIR/$APP_NAME.app" "$STAGE_DIR/$APP_NAME.app"
ln -s /Applications "$STAGE_DIR/Applications"
cp "$SCRIPT_DIR/install-macos.txt" "$STAGE_DIR/설치안내.txt"
hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE_DIR" \
  -ov -format UDZO "$OUTPUT_DIR/CookieRun-Crumble-QuestAssistant-macOS-v16.0.dmg"
hdiutil verify "$OUTPUT_DIR/CookieRun-Crumble-QuestAssistant-macOS-v16.0.dmg"
(cd "$OUTPUT_DIR" && shasum -a 256 *.dmg *.zip > SHA256.txt)
echo "Built: $OUTPUT_DIR"
