#!/usr/bin/env bash
# Install the built tileset into an FAangband source tree, then compile it.
#
# Usage: ./install.sh [path-to-FAangband-tree] [--size 32|64|128] [--yes]
#        (defaults: ~/lab/FAangband, manifest tile_size)
#
# --size picks the tile resolution (default 64, from manifest.json). Source tiles
# are 1024px native, so 64 and 128 carry real detail; 32 is a lightweight
# fallback. The whole tileset rebuilds at that size and the list.txt registration
# is written to match; no engine change is needed (FAangband reads each mode's
# tile dimensions from its registration).
#
# --yes acknowledges the step-1 local-changes notice without prompting, for
# non-interactive runs (an update script, CI). Without it, a tree carrying
# changes that are not ours asks "Proceed with installation, Y/n?" and stops if
# stdin is not a terminal -- the acknowledgement is the point, so it is never
# assumed.
#
# Installs into the SOURCE tree (not the installed prefix) on purpose:
# FAangband's own `make install` then deploys it alongside the stock tilesets,
# and the registration survives future `make install` runs, which rewrite
# lib-derived files in the prefix. Step 7 runs that build for you -- `make` or
# `make install`, whichever this tree's own configuration calls for -- and
# prints the exact command that starts the game afterwards.
#
# There is no gender option. Both genders ship in the one player-sprite prf,
# and the character's own choice at character generation picks between them:
# the HITHER-LANDS:pgender-* patches applied in step 6 add a birth menu stage
# and a $GENDER pref variable that the prf's conditional lines read.
#
# Portability: Linux and macOS. Everything here is POSIX-portable or guarded --
# no `sed -i`, no template-less `mktemp`, no GNU-only `\b` in a grep pattern,
# all three being GNU extensions that fail on macOS/BSD userland. The Windows
# equivalent is install.ps1, which mirrors this script step for step.
set -euo pipefail

FA_DIR="$HOME/lab/FAangband"
SIZE=""
ASSUME_YES=0
UPSTREAM_URL="https://github.com/NickMcConnell/FAangband.git"

# Print the header banner as help: everything from line 2 down to the first line
# that is not a comment. Bounded by the shape of the file, not by a line number
# that silently truncates the next time the banner grows.
usage() { sed -n '2,/^[^#]/p' "$0" | sed -n 's/^#\{1,\} \{0,1\}//p'; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage 0 ;;
        -y|--yes) ASSUME_YES=1; shift ;;
        # Rejected explicitly: without this arm the old flag would fall through
        # to the catch-all below and be silently taken as the FAangband path.
        --gender*) echo "error: --gender was removed -- gender is chosen in-game at character generation" >&2; exit 1 ;;
        --size) SIZE="${2:-}"; shift 2 ;;
        --size=*) SIZE="${1#*=}"; shift ;;
        *) FA_DIR="$1"; shift ;;
    esac
done
if [ -n "$SIZE" ]; then
    case "$SIZE" in
        32|64|128) ;;
        *) echo "error: --size must be 32, 64, or 128 (got '$SIZE')" >&2; exit 1 ;;
    esac
fi

HERE="$(cd "$(dirname "$0")" && pwd)"

# --- portable helpers -------------------------------------------------------
# GNU mktemp invents a template when given none; BSD/macOS mktemp requires one.
hl_mktemp() { mktemp "${TMPDIR:-/tmp}/hither-lands.XXXXXX"; }

# `sed -i` cannot be spelled portably: GNU takes an optional suffix, BSD/macOS
# requires one, so either spelling breaks on the other platform. Write through a
# temp file and copy the bytes back, which also preserves the target's inode and
# permissions -- the same shape as the awk rewrite in step 5.
sed_i() {
    _tmp="$(hl_mktemp)"
    sed "$1" "$2" >"$_tmp"
    cat "$_tmp" >"$2"
    rm -f "$_tmp"
}

DIRNAME=$(python3 -c "import json; print(json.load(open('$HERE/manifest.json'))['tileset']['directory'])")
TILES_DIR="$FA_DIR/lib/tiles"
DIST="$HERE/dist/$DIRNAME"

# Validate the target is a real FAangband tree before doing any work. The
# tileset itself is built by step 2 below (it need not exist yet -- dist/ is
# generated and git-ignored), so we do NOT pre-check $DIST here; step 2 creates
# it and we sanity-check its output afterward.
[ -f "$TILES_DIR/list.txt" ] || { echo "error: $TILES_DIR/list.txt not found -- is $FA_DIR an FAangband tree?" >&2; exit 1; }

# Pre-check Python dependencies before the minutes-long build. Pillow is
# required (the atlas can't be built without it); numpy and reportlab are
# optional features that degrade cleanly.
python3 -c "from PIL import Image" 2>/dev/null || {
    echo "error: Python Pillow is not installed. Install it with:" >&2
    echo "    pip install Pillow" >&2
    exit 1
}
_opt_missing=""
python3 -c "import numpy" 2>/dev/null ||
    _opt_missing="${_opt_missing}  - numpy: enables the light-mode atlas (pip install numpy)
"
python3 -c "import reportlab" 2>/dev/null ||
    _opt_missing="${_opt_missing}  - reportlab: enables PDF help export (pip install reportlab)
"
if [ -n "$_opt_missing" ]; then
    printf 'note: optional dependencies not installed (the atlas build is unaffected):\n%s\n' "$_opt_missing"
fi

TOTAL_STEPS=7
step() { printf '[%d/%d] %s\n' "$1" "$TOTAL_STEPS" "$2"; }

# 1. Preflight: what state is the target tree in?
#
#    Two kinds of local change live here and they mean opposite things. Our own
#    installs edit tracked files -- every patches.json target, plus lib/help/,
#    lib/tiles/ and the sleepiness pass over monster.txt -- so a tree that has
#    been installed into before is ALWAYS dirty, and treating that as a warning
#    would nag on every re-run and hard-stop every non-interactive one. A change
#    to any OTHER file is a real unknown: it is what makes an anchor ambiguous,
#    or a conflict on the next upstream pull. So classify, then ask only about
#    the unknowns. (Upstream having MOVED is a separate question, answered by
#    the baseline-drift report apply_patches.py prints in step 6.)
step 1 "Checking the FAangband tree for local changes ..."
if ! command -v git >/dev/null 2>&1; then
    echo "      git not found -- skipping the local-changes check"
elif ! git -C "$FA_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    echo "      $FA_DIR is not a git repository -- skipping the local-changes check"
else
    DIRTY=$(git -C "$FA_DIR" status --porcelain --untracked-files=no || true)
    if [ -z "$DIRTY" ]; then
        echo "      clean"
    else
        # Paths this installer itself writes. Derived from patches.json rather
        # than listed here, so a new patch group never silently reclassifies as
        # a foreign edit.
        OURS=$(python3 - "$HERE/patches/patches.json" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        files = {r.get("file", "") for r in json.load(fh).get("patches", [])}
except OSError:
    files = set()
files.add("lib/gamedata/monster.txt")   # tools/adjust_sleepiness.py
print("\n".join(sorted(f for f in files if f)))
PY
)
        # Rename lines read "R  old -> new"; keep the destination path. Quoted
        # here-string, not a pipeline, so FOREIGN survives the loop.
        FOREIGN=""
        while IFS= read -r p; do
            [ -n "$p" ] || continue
            case "$p" in
                lib/help/*|lib/tiles/*) continue ;;    # installed wholesale by steps 3-5
            esac
            if printf '%s\n' "$OURS" | grep -qxF -- "$p"; then
                continue
            fi
            FOREIGN="$FOREIGN$p
"
        done <<<"$(printf '%s\n' "$DIRTY" | cut -c4- | sed 's/.* -> //' | tr -d '"')"

        if [ -z "$FOREIGN" ]; then
            echo "      dirty, but every change is one this installer makes"
            echo "      (previous install: patched C sources, tiles, help, gamedata)."
            echo "      To install against pristine upstream instead, stash and pull first."
        else
            ORIGIN=$(git -C "$FA_DIR" remote get-url origin 2>/dev/null || echo "$UPSTREAM_URL")
            N=$(printf '%s' "$FOREIGN" | grep -c '' || true)
            echo
            echo "  NOTICE: $FA_DIR carries $N local change(s) this installer did not make:"
            printf '%s' "$FOREIGN" | head -20 | sed 's/^/      /'
            [ "$N" -gt 20 ] && echo "      ... and $((N - 20)) more"
            cat <<EOF

  Those changes should be stashed and the latest code pulled from the official
  FAangband repository before installing, so the C patches apply to a tree we
  know:

      git -C "$FA_DIR" stash push --include-untracked
      git -C "$FA_DIR" pull --ff-only $ORIGIN

  Then re-run this script; step 6 reapplies our patches from scratch.
EOF
            echo
            if [ "$ASSUME_YES" -eq 1 ]; then
                echo "  --yes given -- proceeding without asking."
            elif [ -t 0 ]; then
                printf '  Proceed with installation, Y/n? '
                read -r ACK || ACK=""
                case "$ACK" in
                    y|Y|yes|Yes|YES|"") ;;
                    *) echo "  Aborted -- nothing was changed."; exit 1 ;;
                esac
            else
                echo "error: the FAangband tree has local changes we did not make, and stdin" >&2
                echo "       is not a terminal. Stash them, or re-run with --yes to proceed." >&2
                exit 1
            fi
            echo
        fi
    fi
fi

# 2. Build the tileset (atlas + prf files) from source tiles + manifest.
if [ -n "$SIZE" ]; then
    step 2 "Building tileset at ${SIZE}x${SIZE} (tools/build.py) ..."
    python3 "$HERE/tools/build.py" --size "$SIZE"
else
    step 2 "Building tileset (tools/build.py) ..."
    python3 "$HERE/tools/build.py"
fi
# Sanity-check the build produced the expected output dir. set -e already
# catches a non-zero build.py; this catches the exit-0-but-no-output case
# (e.g. manifest tileset.directory not matching what build.py wrote).
[ -d "$DIST" ] || { echo "error: build did not produce $DIST (directory-name mismatch?)" >&2; exit 1; }

# 3. Copy the tileset directory (replace wholesale; it is generated output).
step 3 "Copying tileset '$DIRNAME' -> $TILES_DIR ..."
rm -rf "${TILES_DIR:?}/${DIRNAME:?}"
cp -r "$DIST" "$TILES_DIR/$DIRNAME"

# In-game documentation: the guide topics plus the tile-plate index that the
# help-tile patches read. Built into dist/help by tools/build.py, which resolves
# {tile:...} markers -- never install help-source/ directly.
HELP_SRC="$HERE/dist/help"
if [ -d "$HELP_SRC" ]; then
  cp "$HELP_SRC"/*.txt "$HELP_SRC"/help-tiles.idx "$FA_DIR/lib/help/"
  HELP_MK="$FA_DIR/lib/help/Makefile"
  for f in "$HELP_SRC"/*.txt "$HELP_SRC"/help-tiles.idx; do
    b=$(basename "$f")
    grep -q "$b" "$HELP_MK" || sed_i "s|^DATA = |DATA = $b |" "$HELP_MK"
  done
  echo "  installed $(ls "$HELP_SRC" | wc -l) help files"
fi

# 4. Register with the build system so `make install` deploys it.
#    The guard matches on the split-out SUBDIRS value rather than a `\b` grep
#    pattern: word boundaries are a GNU extension BSD/macOS grep does not
#    honour, and a guard that silently fails there would append a duplicate
#    SUBDIRS entry on every single run.
step 4 "Registering in lib/tiles/Makefile ..."
SUBDIRS_LINE=$(grep -m1 '^SUBDIRS' "$TILES_DIR/Makefile" || true)
case " ${SUBDIRS_LINE#*=} " in
    *" $DIRNAME "*) echo "      already registered" ;;
    *) sed_i "s/^SUBDIRS = .*/& $DIRNAME/" "$TILES_DIR/Makefile"
       echo "      added '$DIRNAME' to SUBDIRS" ;;
esac

# 5. Register in list.txt (serial = highest existing + 1).
step 5 "Registering in lib/tiles/list.txt ..."
if ! grep -q "^directory:$DIRNAME\$" "$TILES_DIR/list.txt"; then
    SERIAL=$(( $(grep '^name:' "$TILES_DIR/list.txt" | cut -d: -f2 | sort -n | tail -1) + 1 ))
    { echo ""; sed "s/@SERIAL@/$SERIAL/" "$HERE/dist/list-stanza.txt"; } >> "$TILES_DIR/list.txt"
    echo "      added with serial $SERIAL"
else
    # Already registered -- refresh the size:/atlas line in case --size (or the
    # manifest) changed it, so the registration matches the atlas we just built.
    NEWSIZE=$(grep '^size:' "$HERE/dist/list-stanza.txt")
    TMP=$(hl_mktemp)
    awk -v dir="directory:$DIRNAME" -v newsize="$NEWSIZE" '
        $0 == dir { print; indir=1; next }
        indir && /^size:/ { print newsize; indir=0; next }
        { print }
    ' "$TILES_DIR/list.txt" > "$TMP" && cat "$TMP" > "$TILES_DIR/list.txt" && rm -f "$TMP"
    echo "      already registered -- updated $NEWSIZE"
fi

# 6. Apply C source patches (anchor-based, idempotent; see patches/).
step 6 "Applying C source patches ..."
if [ -f "$HERE/patches/apply_patches.py" ]; then
    python3 "$HERE/patches/apply_patches.py" "$FA_DIR"
else
    echo "      no patches/ -- skipped"
fi

# 6b. Retune monster sleepiness for the ecosystem patches (idempotent -- the
#     script appends its own sentinel to monster.txt and no-ops if present).
if [ -f "$HERE/tools/adjust_sleepiness.py" ] && [ -f "$FA_DIR/lib/gamedata/monster.txt" ]; then
    python3 "$HERE/tools/adjust_sleepiness.py" "$FA_DIR"
else
    echo "      no adjust_sleepiness.py or gamedata -- skipped"
fi

echo "Installed '$DIRNAME' into $TILES_DIR (registered in list.txt + Makefile)."
echo

# 7. Compile FAangband, so the tiles and the step-6 patches reach the running
#    game instead of sitting in the tree. WHICH command is correct depends on
#    how this tree was configured, and getting it wrong is silent: `make
#    install` is wrong for a run-in-place tree, while a plain `make` leaves a
#    prefixed install still reading its old deployed data. mk/extra.mk is
#    configure's own answer to that question (NOINSTALL / ENABLEWIN / prefix /
#    bindir, already expanded), so read it rather than re-deriving the mode from
#    the configure command line; config.log is the fallback when it is absent.
step 7 "Compiling FAangband ..."
EXTRA_MK="$FA_DIR/mk/extra.mk"
CFG_LOG="$FA_DIR/config.log"

mk_var() { sed -n "s/^$1 *?\{0,1\}= *//p" "$EXTRA_MK" | tail -1; }
cfg_var() { sed -n "s/^$1='\(.*\)'\$/\1/p" "$CFG_LOG" | tail -1; }

run_make() {
    # Never swallow make's output, and never let a compile failure read as an
    # install failure: steps 1-6 have already succeeded by now, and re-running
    # this script (a ~15-minute tile rebuild) fixes nothing.
    if ! make -C "$FA_DIR" "$@"; then
        echo >&2
        echo "error: the FAangband build failed. The tileset IS installed into" >&2
        echo "       $FA_DIR -- fix the build error above and re-run just" >&2
        echo "       'make -C \"$FA_DIR\"${*:+ $*}', not ./install.sh." >&2
        exit 1
    fi
}

if [ ! -f "$EXTRA_MK" ] && [ ! -f "$CFG_LOG" ]; then
    cat <<EOF
      FAangband is NOT configured yet (no $EXTRA_MK), so it was NOT compiled.
      The tileset is installed into the tree; configure and build to see it:

        a no-sudo user install (recommended):
          ( cd "$FA_DIR" && ./configure --prefix=\$HOME/.local --bindir=\$HOME/.local/bin --enable-sdl2 && make install )
          then run: faangband -msdl2

        or run in place from this tree:
          ( cd "$FA_DIR" && ./configure --with-no-install --enable-sdl2 && make )
          then run: "$FA_DIR/src/faangband" -msdl2

      Re-run this script afterwards and it will do the build for you.
EOF
    exit 0
fi

NOINSTALL=""; ENABLEWIN=""; PREFIX=""; BINDIR=""; DATADIR=""
if [ -f "$EXTRA_MK" ]; then
    NOINSTALL=$(mk_var NOINSTALL)
    ENABLEWIN=$(mk_var ENABLEWIN)
    PREFIX=$(mk_var prefix)
    BINDIR=$(mk_var bindir)
    DATADIR=$(mk_var libdatadir)
fi
if [ -f "$CFG_LOG" ]; then
    # Fallback / cross-check. A run-in-place tree is identified by NOINSTALL
    # above, but if extra.mk is missing or was hand-edited, the configure line
    # is the only other record of it -- and installing into such a tree is the
    # one build mistake this project must never make.
    CFG_LINE=$(sed -n 's/^  \$ //p' "$CFG_LOG" | grep -m1 configure || true)
    printf '%s' "$CFG_LINE" | grep -q -- '--with-no-install' && NOINSTALL="yes"
    [ -n "$PREFIX" ] || PREFIX=$(cfg_var prefix)
    if [ -z "$BINDIR" ]; then
        BINDIR=$(cfg_var bindir)
        EXEC_PREFIX=$(cfg_var exec_prefix); EXEC_PREFIX=${EXEC_PREFIX:-'${prefix}'}
        # autoconf records these unexpanded -- bindir='${exec_prefix}/bin'.
        EXEC_PREFIX=${EXEC_PREFIX//\$\{prefix\}/$PREFIX}
        BINDIR=${BINDIR//\$\{exec_prefix\}/$EXEC_PREFIX}
        BINDIR=${BINDIR//\$\{prefix\}/$PREFIX}
    fi
fi
PREFIX=${PREFIX:-/usr/local}
BINDIR=${BINDIR:-$PREFIX/bin}
DATADIR=${DATADIR:-$PREFIX/share/faangband}

if [ "$NOINSTALL" = "yes" ] || [ "$ENABLEWIN" = "yes" ]; then
    # Run-in-place: the game reads data straight from this tree's lib/, which
    # this script just updated. No `make install` -- see docs/never-regress.md.
    echo "      Build mode: run in place (no install step) -- running: make -C \"$FA_DIR\""
    echo
    run_make
    RUN_CMD="\"$FA_DIR/src/faangband\" -msdl2"
    NOTE="This build mode reads tiles straight out of $TILES_DIR/.
  A desktop launcher, or a 'faangband' on your PATH, may be a separately
  INSTALLED binary reading a different copy of the data -- it will not show
  these tiles. Point it at $FA_DIR/src/faangband instead."
elif [ "$PREFIX" = "/usr/local" ]; then
    # Prefixed install into a root-owned prefix: compile as the user, but never
    # invoke sudo on their behalf -- deploying is their call, not ours.
    echo "      Build mode: install into $PREFIX, which needs root to deploy."
    echo "      Compiling only -- running: make -C \"$FA_DIR\""
    echo
    run_make
    RUN_CMD="faangband -msdl2"
    NOTE="The tiles are NOT deployed yet -- '$PREFIX' needs root. Finish with:

      sudo make -C \"$FA_DIR\" install

  If what you actually launch is ~/.local/bin/faangband, reconfigure for a user
  install instead and no sudo is needed at all:
      ( cd \"$FA_DIR\" && ./configure --prefix=\$HOME/.local --bindir=\$HOME/.local/bin --enable-sdl2 && make install )"
else
    # Prefixed install: the game runs from the deployed copy under the prefix,
    # so `make install` is the step that actually moves these tiles into place.
    echo "      Build mode: install into $PREFIX -- running: make -C \"$FA_DIR\" install"
    echo
    run_make install
    RUN_CMD="faangband -msdl2"
    NOTE="Tiles and gamedata are deployed to $DATADIR, the binary to $BINDIR/.
  If '$BINDIR' is not on your PATH, run \"$BINDIR/faangband\" -msdl2 instead."
fi

cat <<EOF

Done. Run the game with:

    $RUN_CMD

  $NOTE

  Tiles are off until you switch them on: start or load a character first, then
  use the SDL2 window's own menu bar -- Menu > FAangband > Tiles > Set > Hither
  Lands. They never render in the curses frontend (-mgcu).
EOF
