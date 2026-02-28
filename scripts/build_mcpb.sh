#!/bin/bash
# Build the CrewBus MCPB bundle for distribution
set -e

BUNDLE_NAME="crew-bus"
VERSION=$(python3 -c "import json; print(json.load(open('manifest.json'))['version'])")
OUTPUT="${BUNDLE_NAME}-${VERSION}.mcpb"
INNER_DIR="crewbus-mcpb"

echo "Building CrewBus MCPB bundle v${VERSION}..."

# Create a clean temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Build the required directory structure:
#   crewbus-mcpb/
#     manifest.json
#     icon.png
#     server/
#       main.py
mkdir -p "$TEMP_DIR/$INNER_DIR/server"

cp manifest.json "$TEMP_DIR/$INNER_DIR/"
cp crew_bus_mcp.py "$TEMP_DIR/$INNER_DIR/server/main.py"

# Copy the icon (check both locations)
if [ -f "icon.png" ]; then
    cp icon.png "$TEMP_DIR/$INNER_DIR/"
elif [ -f "assets/icon.png" ]; then
    cp assets/icon.png "$TEMP_DIR/$INNER_DIR/icon.png"
fi

# Build the .mcpb (zip archive)
cd "$TEMP_DIR"
zip -r "/tmp/$OUTPUT" "$INNER_DIR/" -x ".*"
cd - > /dev/null
mv "/tmp/$OUTPUT" "./$OUTPUT"

echo ""
echo "Built: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
echo ""
echo "Contents:"
unzip -l "$OUTPUT"
echo ""
echo "To install: double-click the .mcpb file with Claude Desktop open"
echo "To distribute: upload to GitHub Releases or share directly"
