#!/usr/bin/env bash
# Install the built tileset into an FAangband source tree.
#
# Usage: ./install.sh [path-to-FAangband-tree] [--gender male|female] [--size 32|64|128]
#        (defaults: ~/lab/FAangband, male, manifest tile_size)
#
# --size picks the tile resolution (default 64, from manifest.json). Source tiles
# are 1024px native, so 64 and 128 carry real detail; 32 is a lightweight
# fallback. The whole tileset rebuilds at that size and the list.txt registration
# is written to match; no engine change is needed (FAangband reads each mode's
# tile dimensions from its registration).
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
SIZE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --gender) GENDER="${2:-male}"; shift 2 ;;
        --gender=*) GENDER="${1#*=}"; shift ;;
        --size) SIZE="${2:-}"; shift 2 ;;
        --size=*) SIZE="${1#*=}"; shift ;;
        *) FA_DIR="$1"; shift ;;
    esac
done
GENDER="$(printf '%s' "$GENDER" | tr '[:upper:]' '[:lower:]')"
[ "$GENDER" = "male" ] || [ "$GENDER" = "female" ] || {
    echo "error: --gender must be 'male' or 'female' (got '$GENDER')" >&2; exit 1; }
if [ -n "$SIZE" ]; then
    case "$SIZE" in
        32|64|128) ;;
        *) echo "error: --size must be 32, 64, or 128 (got '$SIZE')" >&2; exit 1 ;;
    esac
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

DIRNAME=$(python3 -c "import json; print(json.load(open('$HERE/manifest.json'))['tileset']['directory'])")
PREF=$(python3 -c "import json; print(json.load(open('$HERE/manifest.json'))['tileset']['pref'])")
XTRA="${PREF/graf-/xtra-}"          # e.g. graf-fai.prf -> xtra-fai.prf
XTRA_STEM="${XTRA%.prf}"            # xtra-fai
TILES_DIR="$FA_DIR/lib/tiles"
DIST="$HERE/dist/$DIRNAME"

[ -d "$DIST" ] || { echo "error: $DIST not built -- run tools/build.py first" >&2; exit 1; }
[ -f "$TILES_DIR/list.txt" ] || { echo "error: $TILES_DIR/list.txt not found -- is $FA_DIR an FAangband tree?" >&2; exit 1; }

TOTAL_STEPS=6
step() { printf '[%d/%d] %s\n' "$1" "$TOTAL_STEPS" "$2"; }

# 1. Build the tileset (atlas + prf files) from source tiles + manifest.
if [ -n "$SIZE" ]; then
    step 1 "Building tileset at ${SIZE}x${SIZE} (tools/build.py) ..."
    python3 "$HERE/tools/build.py" --size "$SIZE"
else
    step 1 "Building tileset (tools/build.py) ..."
    python3 "$HERE/tools/build.py"
fi

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
    # Already registered -- refresh the size:/atlas line in case --size (or the
    # manifest) changed it, so the registration matches the atlas we just built.
    NEWSIZE=$(grep '^size:' "$HERE/dist/list-stanza.txt")
    TMP=$(mktemp)
    awk -v dir="directory:$DIRNAME" -v newsize="$NEWSIZE" '
        $0 == dir { print; indir=1; next }
        indir && /^size:/ { print newsize; indir=0; next }
        { print }
    ' "$TILES_DIR/list.txt" > "$TMP" && mv "$TMP" "$TILES_DIR/list.txt"
    echo "      already registered -- updated $NEWSIZE"
fi

# 5. Apply C source patches (anchor-based, idempotent; see patches/).
step 5 "Applying C source patches ..."
if [ -f "$HERE/patches/apply_patches.py" ]; then
    python3 "$HERE/patches/apply_patches.py" "$FA_DIR"
else
    echo "      no patches/ -- skipped"
fi

echo "Installed '$DIRNAME' into $TILES_DIR (registered in list.txt + Makefile)."
echo

# 6. Review the FAangband build configuration and print the EXACT command(s)
#    needed to get these tiles into the running game. install.sh only writes
#    into the source tree; how that reaches the running game depends on how the
#    tree was configured (run-in-place vs. prefixed install). Detect it from
#    config.log instead of printing a one-size-fits-all 'make install', which is
#    wrong for --with-no-install and silently misses the user's launcher.
step 6 "Reviewing FAangband build configuration ..."
CFG_LOG="$FA_DIR/config.log"
if [ ! -f "$CFG_LOG" ]; then
    cat <<EOF
      FAangband isn't configured yet (no $CFG_LOG). Configure, then build:
        run in place from this tree:
          ( cd "$FA_DIR" && ./configure --with-no-install --enable-sdl2 && make )
          then run: "$FA_DIR/src/faangband" -msdl2
        or a no-sudo user install:
          ( cd "$FA_DIR" && ./configure --prefix=\$HOME/.local --bindir=\$HOME/.local/bin --enable-sdl2 && make install )
EOF
else
    # The ./configure invocation the tree was last built with, and its prefix.
    CFG_LINE=$(sed -n 's/^  \$ //p' "$CFG_LOG" | grep -m1 configure || true)
    PREFIX=$(sed -n "s/^prefix='\(.*\)'\$/\1/p" "$CFG_LOG" | tail -1 || true)
    if printf '%s' "$CFG_LINE" | grep -q -- '--with-no-install'; then
        # Run-in-place: the game reads data straight from this tree's lib/,
        # which install.sh just updated. No `make install`, no copy step.
        cat <<EOF
      Build mode: run-in-place (--with-no-install).
      The game reads tiles directly from this tree -- already updated:
          $TILES_DIR/
      To see them, recompile and launch the IN-PLACE binary:

          make -C "$FA_DIR"
          "$FA_DIR/src/faangband" -msdl2

      Do NOT run 'make install' in this mode. If a desktop launcher or the
      'faangband' command runs an INSTALLED binary (e.g. ~/.local/bin/faangband),
      it reads a different data copy and will NOT show these tiles -- point it at
      "$FA_DIR/src/faangband" instead.
EOF
    else
        # Prefixed install: tiles must be copied to the prefix data dir by
        # `make install`; the game runs from there, not this tree.
        DATADIR="${PREFIX:-/usr/local}/share/faangband"
        cat <<EOF
      Build mode: prefixed install (prefix = ${PREFIX:-/usr/local}).
      The game runs from the installed copy, so deploy these tiles with:

          make -C "$FA_DIR" install

      That copies them to $DATADIR/tiles/ and rebuilds the installed binary.
      Then run the installed 'faangband -msdl2'.
EOF
        if [ "${PREFIX:-/usr/local}" = "/usr/local" ]; then
            cat <<EOF

      WARNING: prefix is /usr/local -- 'make install' needs root (sudo) and will
      NOT update a ~/.local install. If you launch ~/.local/bin/faangband,
      reconfigure for a user install first:
          ( cd "$FA_DIR" && ./configure --prefix=\$HOME/.local --bindir=\$HOME/.local/bin --enable-sdl2 && make install )
EOF
        fi
    fi
fi
