#!/usr/bin/env bash
# Install the built tileset into an FAangband source tree.
#
# Usage: ./install.sh [path-to-FAangband-tree]   (default: ~/lab/FAangband)
#
# Installs into the SOURCE tree (not the installed prefix) on purpose:
# FAangband's own `make install` then deploys it alongside the stock
# tilesets, and the registration survives future `make install` runs,
# which rewrite lib-derived files in the prefix.
set -euo pipefail

FA_DIR="${1:-$HOME/lab/FAangband}"
HERE="$(cd "$(dirname "$0")" && pwd)"

DIRNAME=$(python3 -c "import json; print(json.load(open('$HERE/manifest.json'))['tileset']['directory'])")
TILES_DIR="$FA_DIR/lib/tiles"
DIST="$HERE/dist/$DIRNAME"

[ -d "$DIST" ] || { echo "error: $DIST not built -- run tools/build.py first" >&2; exit 1; }
[ -f "$TILES_DIR/list.txt" ] || { echo "error: $TILES_DIR/list.txt not found -- is $FA_DIR an FAangband tree?" >&2; exit 1; }

# 1. Copy the tileset directory (replace wholesale; it is generated output).
rm -rf "${TILES_DIR:?}/${DIRNAME:?}"
cp -r "$DIST" "$TILES_DIR/$DIRNAME"

# 2. Register with the build system so `make install` deploys it.
if ! grep -qE "^SUBDIRS\b.*\b$DIRNAME\b" "$TILES_DIR/Makefile"; then
    sed -i "s/^SUBDIRS = .*/& $DIRNAME/" "$TILES_DIR/Makefile"
fi

# 3. Register in list.txt (serial = highest existing + 1).
if ! grep -q "^directory:$DIRNAME\$" "$TILES_DIR/list.txt"; then
    SERIAL=$(( $(grep '^name:' "$TILES_DIR/list.txt" | cut -d: -f2 | sort -n | tail -1) + 1 ))
    { echo ""; sed "s/@SERIAL@/$SERIAL/" "$HERE/dist/list-stanza.txt"; } >> "$TILES_DIR/list.txt"
fi

echo "Installed '$DIRNAME' into $TILES_DIR and registered it in list.txt + Makefile."
echo "Deploy with: make -C $FA_DIR install"
