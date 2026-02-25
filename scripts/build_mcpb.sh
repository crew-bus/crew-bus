#\!/bin/bash
# Build the CrewBus MCPB bundle for distribution
set -e

BUNDLE_NAME="crew-bus"
VERSION=$(python3 -c "import json; print(json.load(open('manifest.json'))['version'])")
OUTPUT="${BUNDLE_NAME}-${VERSION}.mcpb"

echo "Building CrewBus MCPB bundle v${VERSION}..."

# Create a clean temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy required files
cp manifest.json "$TEMP_DIR/"
cp crew_bus_mcp.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"

# Copy the icon if it exists
if [ -f "assets/icon.png" ]; then
    mkdir -p "$TEMP_DIR/assets"
    cp assets/icon.png "$TEMP_DIR/assets/"
fi

# Build the .mcpb (it is just a zip)
cd "$TEMP_DIR"
zip -r "/tmp/$OUTPUT" . -x ".*"
cd -
mv "/tmp/$OUTPUT" "./$OUTPUT"

echo ""
echo "Built: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
echo ""
echo "To install: double-click the .mcpb file with Claude Desktop open"
echo "To distribute: upload to GitHub Releases or share directly"
