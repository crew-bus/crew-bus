#!/usr/bin/env bash
# Build, sign, package, and notarize the CrewBus SwiftUI app
# Produces a signed+notarized CrewBus-1.0.0.dmg ready for distribution
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
MACOS_DIR="$REPO_ROOT/macos"
BUILD_DIR="$MACOS_DIR/build"
PRODUCT_DIR="$BUILD_DIR/Build/Products/Release"
APP_PATH="$PRODUCT_DIR/CrewBus.app"
DMG_NAME="CrewBus-1.0.0"
DMG_PATH="$REPO_ROOT/public/downloads/$DMG_NAME.dmg"

SIGN_IDENTITY="Developer ID Application: Ryan Johnson (KGG7W48LZG)"
TEAM_ID="KGG7W48LZG"
ENTITLEMENTS="$MACOS_DIR/CrewBus/Resources/CrewBus.entitlements"
KEYCHAIN_PROFILE="CrewBus"

echo ""
echo "  CrewBus macOS App — Build & Notarize"
echo "  ======================================"
echo ""

# ── Step 1: Build with xcodebuild ──
echo "  [1/5] Building Release..."
xcodebuild \
    -project "$MACOS_DIR/CrewBus.xcodeproj" \
    -scheme CrewBus \
    -configuration Release \
    -derivedDataPath "$BUILD_DIR" \
    CODE_SIGN_STYLE=Manual \
    DEVELOPMENT_TEAM="$TEAM_ID" \
    CODE_SIGN_IDENTITY="$SIGN_IDENTITY" \
    CODE_SIGN_INJECT_BASE_ENTITLEMENTS=NO \
    ENABLE_HARDENED_RUNTIME=YES \
    OTHER_CODE_SIGN_FLAGS="--timestamp" \
    clean build 2>&1 | tail -5

if [ ! -d "$APP_PATH" ]; then
    echo "  ERROR: Build failed — $APP_PATH not found"
    exit 1
fi
echo "  Build OK"

# ── Step 2: Deep-sign Sparkle binaries ──
# Sparkle ships with ad-hoc signatures. Apple requires Developer ID + timestamp.
echo ""
echo "  [2/5] Deep-signing Sparkle framework..."

SPARKLE_DIR="$APP_PATH/Contents/Frameworks/Sparkle.framework"

if [ -d "$SPARKLE_DIR" ]; then
    # Sign innermost binaries first, then work outward
    SPARKLE_BINS=(
        "$SPARKLE_DIR/Versions/B/XPCServices/Downloader.xpc"
        "$SPARKLE_DIR/Versions/B/XPCServices/Installer.xpc"
        "$SPARKLE_DIR/Versions/B/Updater.app"
        "$SPARKLE_DIR/Versions/B/Autoupdate"
        "$SPARKLE_DIR"
    )

    for bin in "${SPARKLE_BINS[@]}"; do
        if [ -e "$bin" ]; then
            echo "    Signing $(basename "$bin")..."
            codesign --force --deep --timestamp \
                --options runtime \
                --sign "$SIGN_IDENTITY" \
                "$bin"
        fi
    done
    echo "  Sparkle signing OK"
else
    echo "  No Sparkle.framework found, skipping"
fi

# ── Step 3: Re-sign the main app (picks up Sparkle changes) ──
echo ""
echo "  [3/5] Signing CrewBus.app..."
codesign --force --deep --timestamp \
    --options runtime \
    --entitlements "$ENTITLEMENTS" \
    --sign "$SIGN_IDENTITY" \
    "$APP_PATH"

# Verify
echo "  Verifying signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH" 2>&1 | tail -3
spctl --assess --type execute --verbose "$APP_PATH" 2>&1 || true
echo "  Signing OK"

# ── Step 4: Create DMG ──
echo ""
echo "  [4/5] Creating DMG..."
mkdir -p "$(dirname "$DMG_PATH")"
rm -f "$DMG_PATH"

hdiutil create \
    -volname "Crew Bus" \
    -srcfolder "$APP_PATH" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# Sign the DMG itself
codesign --force --timestamp \
    --sign "$SIGN_IDENTITY" \
    "$DMG_PATH"

echo "  DMG created: $DMG_PATH"
echo "  Size: $(du -h "$DMG_PATH" | cut -f1)"

# ── Step 5: Notarize ──
echo ""
echo "  [5/5] Submitting for notarization..."
xcrun notarytool submit "$DMG_PATH" \
    --keychain-profile "$KEYCHAIN_PROFILE" \
    --wait 2>&1 | tee /tmp/crewbus-notarize.log

# Check result
if grep -q "status: Accepted" /tmp/crewbus-notarize.log; then
    echo ""
    echo "  Notarization ACCEPTED — stapling ticket..."
    xcrun stapler staple "$DMG_PATH"
    echo ""
    echo "  Done! Ready for distribution:"
    echo "  $DMG_PATH"
else
    echo ""
    echo "  Notarization did not pass. Check log:"
    # Extract submission ID and fetch detailed log
    SUB_ID=$(grep -o 'id: [a-f0-9-]*' /tmp/crewbus-notarize.log | head -1 | cut -d' ' -f2)
    if [ -n "$SUB_ID" ]; then
        echo "  Fetching detailed log for $SUB_ID..."
        xcrun notarytool log "$SUB_ID" --keychain-profile "$KEYCHAIN_PROFILE" 2>&1
    fi
    exit 1
fi

echo ""
