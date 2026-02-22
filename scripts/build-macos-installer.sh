#!/usr/bin/env bash
# Build macOS .dmg installer for Crew Bus
# Creates an .app bundle that opens Terminal and runs install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$REPO_ROOT/.build/macos-installer"
APP_NAME="Install Crew Bus"
DMG_NAME="Install-Crew-Bus"
OUTPUT_DIR="$REPO_ROOT/public/downloads"

echo ""
echo "  Building macOS .dmg installer"
echo "  =============================="
echo ""

# ── Clean previous build ──
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$APP_NAME.app/Contents/MacOS"
mkdir -p "$BUILD_DIR/$APP_NAME.app/Contents/Resources"

# ── Copy install.sh into app bundle ──
cp "$REPO_ROOT/install.sh" "$BUILD_DIR/$APP_NAME.app/Contents/Resources/install.sh"
chmod +x "$BUILD_DIR/$APP_NAME.app/Contents/Resources/install.sh"

# ── Create Info.plist ──
cat > "$BUILD_DIR/$APP_NAME.app/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Install Crew Bus</string>
    <key>CFBundleDisplayName</key>
    <string>Install Crew Bus</string>
    <key>CFBundleIdentifier</key>
    <string>com.crewbus.installer</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHumanReadableCopyright</key>
    <string>MIT License — Crew Bus</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# ── Create launcher script ──
# Uses osascript to open Terminal and run install.sh
cat > "$BUILD_DIR/$APP_NAME.app/Contents/MacOS/launcher" << 'LAUNCHER'
#!/usr/bin/env bash
# Crew Bus .app launcher — opens Terminal and runs install.sh
DIR="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_SCRIPT="$DIR/Resources/install.sh"

osascript -e "
tell application \"Terminal\"
    activate
    do script \"bash '${INSTALL_SCRIPT}'\"
end tell
"
LAUNCHER
chmod +x "$BUILD_DIR/$APP_NAME.app/Contents/MacOS/launcher"

# ── Build .dmg ──
mkdir -p "$OUTPUT_DIR"
DMG_PATH="$OUTPUT_DIR/$DMG_NAME.dmg"
rm -f "$DMG_PATH"

echo "  Creating .dmg..."
hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$BUILD_DIR/$APP_NAME.app" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# ── Clean up build dir ──
rm -rf "$BUILD_DIR"

echo ""
echo "  Done! .dmg is at:"
echo "  $DMG_PATH"
echo "  Size: $(du -h "$DMG_PATH" | cut -f1)"
echo ""
