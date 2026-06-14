#!/usr/bin/env bash
# Install the built tileset into an FAangband source tree.
#
# Usage: ./install.sh [path-to-FAangband-tree] [--gender male|female]
#        (defaults: ~/lab/FAangband, male)
#
# Installs into the SOURCE tree (not the installed prefix) on purpose:
# FAangband's own `make install` then deploys it alongside the stock
# tilesets, and the registration survives future `make install` runs,
# which rewrite lib-derived files in the prefix.
#
# --gender selects which player sprites are used. FAangband has no runtime
# player gender, so the choice is baked in here: the build produced both a male
# and a female player-tile prf; we copy the chosen one over the default.
set -euo pipefail

FA_DIR="$HOME/lab/FAangband"
GENDER="male"
while [ $# -gt 0 ]; do
    case "$1" in
        --gender) GENDER="${2:-male}"; shift 2 ;;
        --gender=*) GENDER="${1#*=}"; shift ;;
        *) FA_DIR="$1"; shift ;;
    esac
done
GENDER="$(printf '%s' "$GENDER" | tr '[:upper:]' '[:lower:]')"
[ "$GENDER" = "male" ] || [ "$GENDER" = "female" ] || {
    echo "error: --gender must be 'male' or 'female' (got '$GENDER')" >&2; exit 1; }

HERE="$(cd "$(dirname "$0")" && pwd)"

DIRNAME=$(python3 -c "import json; print(json.load(open('$HERE/manifest.json'))['tileset']['directory'])")
PREF=$(python3 -c "import json; print(json.load(open('$HERE/manifest.json'))['tileset']['pref'])")
XTRA="${PREF/graf-/xtra-}"          # e.g. graf-fai.prf -> xtra-fai.prf
XTRA_STEM="${XTRA%.prf}"            # xtra-fai
TILES_DIR="$FA_DIR/lib/tiles"
DIST="$HERE/dist/$DIRNAME"

[ -d "$DIST" ] || { echo "error: $DIST not built -- run tools/build.py first" >&2; exit 1; }
[ -f "$TILES_DIR/list.txt" ] || { echo "error: $TILES_DIR/list.txt not found -- is $FA_DIR an FAangband tree?" >&2; exit 1; }

TOTAL_STEPS=5
step() { printf '[%d/%d] %s\n' "$1" "$TOTAL_STEPS" "$2"; }

# 1. Build the tileset (atlas + prf files) from source tiles + manifest.
step 1 "Building tileset (tools/build.py) ..."
python3 "$HERE/tools/build.py"

# 2. Copy the tileset directory (replace wholesale; it is generated output).
step 2 "Copying tileset '$DIRNAME' -> $TILES_DIR ..."
rm -rf "${TILES_DIR:?}/${DIRNAME:?}"
cp -r "$DIST" "$TILES_DIR/$DIRNAME"
# 1b. Select the gendered player sprites (default build is male).
GENDERED="$TILES_DIR/$DIRNAME/$XTRA_STEM-$GENDER.prf"
if [ -f "$GENDERED" ]; then
    cp "$GENDERED" "$TILES_DIR/$DIRNAME/$XTRA"
    echo "      player sprites: $GENDER"
fi

# 3. Register with the build system so `make install` deploys it.
step 3 "Registering in lib/tiles/Makefile ..."
if ! grep -qE "^SUBDIRS\b.*\b$DIRNAME\b" "$TILES_DIR/Makefile"; then
    sed -i "s/^SUBDIRS = .*/& $DIRNAME/" "$TILES_DIR/Makefile"
    echo "      added '$DIRNAME' to SUBDIRS"
else
    echo "      already registered"
fi

# 4. Register in list.txt (serial = highest existing + 1).
step 4 "Registering in lib/tiles/list.txt ..."
if ! grep -q "^directory:$DIRNAME\$" "$TILES_DIR/list.txt"; then
    SERIAL=$(( $(grep '^name:' "$TILES_DIR/list.txt" | cut -d: -f2 | sort -n | tail -1) + 1 ))
    { echo ""; sed "s/@SERIAL@/$SERIAL/" "$HERE/dist/list-stanza.txt"; } >> "$TILES_DIR/list.txt"
    echo "      added with serial $SERIAL"
else
    echo "      already registered"
fi

# 5. Apply C source patches (anchor-based, idempotent; see patches/).
step 5 "Applying C source patches ..."
if [ -f "$HERE/patches/apply_patches.py" ]; then
    python3 "$HERE/patches/apply_patches.py" "$FA_DIR"
else
    echo "      no patches/ -- skipped"
fi

echo "Installed '$DIRNAME' into $TILES_DIR and registered it in list.txt + Makefile."
echo "Deploy with: make -C $FA_DIR install"
