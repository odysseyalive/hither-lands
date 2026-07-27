#!/usr/bin/env python3
"""Build the distributable tileset from manifest.json + source-tiles/.

Outputs into dist/<directory>/:
  - the <N>x<N> atlas PNG (tiles composited at their manifest grid positions)
  - the graf-*.prf mapping file
  - a buildsys Makefile so FAangband's `make install` deploys the tileset
plus dist/list-stanza.txt, the lib/tiles/list.txt entry with @SERIAL@ left
for install.sh to fill in.

Source tiles may be any size; they are downscaled to the tile size. A tile with
"chroma": true has near-magenta (255,0,255) pixels keyed to transparent —
use this for AI-generated renders, which can't emit an alpha channel.

Tile size defaults to manifest `tileset.tile_size`; --size N overrides it (the
atlas is named <N>x<N>.png to match, and the list.txt registration follows).
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHROMA = (255, 0, 255)
CHROMA_TOL = 60

# Many GPUs cap a single texture at 8192px. A taller/wider atlas can silently
# fail to upload in the SDL2 front-end, so warn at build time (mostly relevant
# at --size 128, where the atlas grows quadratically).
MAX_TEXTURE = 8192


FAMILY_TOL = 50  # for "family" mode: how far magenta must dominate green
BG_COLOR = (23, 19, 16)  # #171310 — the shared dark background

# AI renders often leave an impure-magenta fringe (e.g. (255,70,250)) a pixel or
# two in from the frame — too far from pure #FF00FF for the tight chroma key, so
# it survives as opaque magenta and LANCZOS-downscales into a faint colored edge
# line. The tight key sweeps this outer ring for magenta-DOMINANT pixels too, so
# the fringe dies at full resolution (before it can bleed) while genuine purple
# detail in the interior is untouched. ALPHA_FLOOR then clears any sub-threshold
# feathering the resize leaves — invisible as art, but the SDL2 front-end scales
# it into a visible line.
EDGE_BAND_FRAC = 0.03  # outer ring (fraction of the shorter side) swept for fringe
ALPHA_FLOOR = 16       # alpha below this reads as invisible art but renders as a line

# A character cell on screen is TALLER THAN IT IS WIDE (about 10x22 px at a 16px
# font), but an atlas cell is square. Block art -- an illuminated capital spread
# over several cells -- must therefore be pre-distorted horizontally, or the
# engine's square-cell-to-tall-cell mapping squashes the letter flat. This is a
# pure ratio, so it holds at any --size: the atlas cell and the screen cell scale
# together. It describes the reader's font, not the tileset, so it is a constant
# here rather than manifest data.
CELL_ASPECT = (10, 22)


def key_out_chroma(img, family=False, edge_fringe=False):
    """Make the magenta background transparent.

    Tight mode (default): only near-pure #FF00FF. Safe for sprites that may
    contain legitimate purple/magenta detail.

    Family mode: any pixel where magenta dominates green (r-g and b-g both
    large) — also removes the darkened-magenta drop shadows the generator
    bakes under buildings. Do NOT use on art with genuine purple (the magic
    shop therefore uses a deep-blue roof, which survives this key).

    edge_fringe (tight mode only): additionally apply the magenta-dominant
    family test, but confined to the outer EDGE_BAND_FRAC ring. This catches the
    impure-magenta edge fringe the near-pure test misses, before it bleeds into
    a faint edge line — without touching interior detail (see EDGE_BAND_FRAC).
    """
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    band = int(min(w, h) * EDGE_BAND_FRAC) if edge_fringe else 0
    for y in range(h):
        # In edge-fringe mode, whole top/bottom band rows are "near an edge"; on
        # interior rows only the left/right band columns are. Precomputing this
        # per row keeps the interior fast (a couple of int compares, no min()).
        row_edge = band and (y < band or y >= h - band)
        for x in range(w):
            r, g, b, a = px[x, y]
            if family:
                hit = (r - g > FAMILY_TOL) and (b - g > FAMILY_TOL)
            else:
                hit = (abs(r - CHROMA[0]) < CHROMA_TOL
                       and abs(g - CHROMA[1]) < CHROMA_TOL
                       and abs(b - CHROMA[2]) < CHROMA_TOL)
                if (not hit and band
                        and (row_edge or x < band or x >= w - band)
                        and (r - g > FAMILY_TOL) and (b - g > FAMILY_TOL)):
                    hit = True
            if hit:
                px[x, y] = (r, g, b, 0)
    return img


def apply_margin_fade(img, margin_frac=0.10, fade_frac=0.05):
    """Fade scattered-element tiles to the dark background at all edges.

    Guarantees the edge-containment rule (art-direction § 10) mechanically:
    source tiles can be generated with full coverage, and the build enforces
    the dark margin — same philosophy as palette snap enforcing the palette.
    """
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    margin = int(w * margin_frac)
    fade = int(w * fade_frac)
    solid = margin - fade
    for y in range(h):
        for x in range(w):
            dist = min(x, y, w - 1 - x, h - 1 - y)
            if dist < solid:
                px[x, y] = (*BG_COLOR, 255)
            elif dist < margin:
                t = (dist - solid) / fade if fade > 0 else 1.0
                r, g, b, a = px[x, y]
                px[x, y] = (
                    int(BG_COLOR[0] * (1 - t) + r * t),
                    int(BG_COLOR[1] * (1 - t) + g * t),
                    int(BG_COLOR[2] * (1 - t) + b * t),
                    255,
                )
    return img


def load_palette():
    """Load the locked theme palette from palette.json (list of #rrggbb or [r,g,b])."""
    p = ROOT / "palette.json"
    if not p.is_file():
        return None
    data = json.loads(p.read_text())
    cols = data["colors"] if isinstance(data, dict) else data
    out = []
    for c in cols:
        if isinstance(c, str):
            c = c.lstrip("#")
            out.append(tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)))
        else:
            out.append(tuple(c))
    return out


def light_atlas_name(m):
    """Filename of the light-mode plate: "64x64.png" -> "64x64-light.png".

    This rule is duplicated ON PURPOSE in the HITHER-LANDS:display-lightmode-atlas
    C patch, which has only the graphics mode's own directory + atlas filename to
    work from -- the engine never learns about a second plate, so the name IS the
    contract between the two halves. Change it here and you must change it there;
    there is no third place that could mediate.
    """
    stem, _, ext = m["tileset"]["atlas"].rpartition(".")
    return f"{stem}-light.{ext}" if stem else m["tileset"]["atlas"] + "-light"


def snap_to_palette(img, palette):
    """Quantize every pixel to the nearest locked-palette color, preserving alpha.

    This is what actually enforces tileset cohesion — the image model only
    biases toward the theme; this guarantees it. Re-running build after editing
    palette.json re-themes the whole set without regenerating any art.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.split()[3]
    palimg = Image.new("P", (1, 1))
    flat = []
    for c in palette:
        flat += list(c)
    flat += flat[:3] * (256 - len(palette))  # pad to a full 256-entry palette
    palimg.putpalette(flat)
    q = rgba.convert("RGB").quantize(
        palette=palimg, dither=Image.Dither.NONE).convert("RGBA")
    q.putalpha(alpha)
    return q


def floor_alpha(img, threshold=ALPHA_FLOOR):
    """Zero pixels whose alpha is below `threshold`.

    A near-invisible feather (a few % opacity) is imperceptible as art, but the
    SDL2 front-end composites and scales it into a faint line. Real anti-aliased
    silhouettes keep their meaningful (higher-alpha) body; only the faintest
    feather is trimmed. Applied once to the assembled atlas so tiles, player
    variants and shapes are treated uniformly.
    """
    rgba = img.convert("RGBA")
    a = rgba.split()[3].point(lambda v: 0 if v < threshold else v)
    rgba.putalpha(a)
    return rgba


def _progress(label, done, total):
    """Live progress bar on stderr (visible even when stdout is piped to tail)."""
    width = 28
    frac = (done / total) if total else 1.0
    filled = int(width * frac)
    bar = "#" * filled + "-" * (width - filled)
    sys.stderr.write(f"\r  {label:<20} [{bar}] {done}/{total} ({frac * 100:3.0f}%)")
    sys.stderr.flush()
    if done >= total:
        sys.stderr.write("\n")


def render_tile_image(spec, source_rel, ts, block=None):
    """Run one source tile through the chroma/resize/margin/ground pipeline.

    Factored out so animation frames get exactly the same treatment as the
    base tile (an animated tile is just N of these pasted in a row).
    """
    src = ROOT / "source-tiles" / source_rel
    if not src.is_file():
        sys.exit(f"missing source tile: {src}")
    img = Image.open(src)
    if spec.get("chroma") == "family":
        img = key_out_chroma(img, family=True)
    elif spec.get("chroma"):
        img = key_out_chroma(img, edge_fringe=True)
    if block:
        img = fit_block_art(img, block[0], block[1], ts)
    else:
        img = img.convert("RGBA").resize((ts, ts), Image.LANCZOS)
    if spec.get("margin"):
        img = apply_margin_fade(img)
    # A terrain feature (e.g. a building) fills its whole cell — the engine
    # draws only one tile per grid square, so transparent corners would show
    # the black terminal background. Bake a ground texture underneath so the
    # tile is opaque and its edges match the surrounding floor. (Monster/player
    # sprites omit "ground" and stay transparent for compositing over terrain.)
    if spec.get("ground"):
        ground_src = ROOT / "source-tiles" / spec["ground"]
        if not ground_src.is_file():
            sys.exit(f"missing ground texture: {ground_src}")
        base = Image.open(ground_src).convert("RGBA").resize(
            (ts, ts), Image.LANCZOS)
        base.alpha_composite(img)
        img = base
    return img


def fit_block_art(img, bw, bh, ts):
    """Fit one drawing into a bw x bh block of atlas cells, undistorted on screen.

    Trims the source's empty margin, then scales so the letter keeps its true
    proportions AFTER the engine maps each square atlas cell onto a tall narrow
    character cell (see CELL_ASPECT). Centred on a transparent canvas, so the
    outer cells of a block may legitimately be blank.
    """
    img = img.convert("RGBA")
    # Alpha-only bbox: the chroma key zeroes alpha but keeps the magenta RGB, so a
    # plain getbbox() would see the whole frame on older Pillow. The ALPHA_FLOOR
    # threshold also drops the sub-threshold feather that would inflate the box.
    box = img.getchannel("A").point(lambda v: 255 if v >= ALPHA_FLOOR else 0).getbbox()
    if box:
        img = img.crop(box)

    cw, ch = bw * ts, bh * ts
    # Pre-distort: widen by the cell's height:width ratio so the on-screen result
    # is true to the source.
    stretch = CELL_ASPECT[1] / CELL_ASPECT[0]
    want_w, want_h = img.width * stretch, img.height
    scale = min(cw / want_w, ch / want_h)
    w, h = max(1, round(want_w * scale)), max(1, round(want_h * scale))

    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    out.paste(img.resize((w, h), Image.LANCZOS), ((cw - w) // 2, (ch - h) // 2))
    return out


def block_of(t):
    """A tile's cell span, (width, height). Ordinary tiles are 1x1; an
    illuminated capital declares e.g. "block": [3, 2] and is sliced across
    that many atlas cells so one drawing becomes one large letter."""
    b = t.get("block")
    return (int(b[0]), int(b[1])) if b else (1, 1)


def frame_sources(t):
    """A tile's animation frames, in order. Static tiles return their one
    source; an animated tile lists its frames in "frames" (frame 0 first,
    placed at the base cell the prf maps to)."""
    fr = t.get("frames")
    if isinstance(fr, list) and fr:
        return fr
    return [t["source"]]


def parse_args():
    ap = argparse.ArgumentParser(
        description="Build the FAangband tileset from manifest.json + source-tiles/.")
    ap.add_argument(
        "--size", type=int, default=None, metavar="N",
        help="override tile size in pixels (e.g. 32, 64, 128); default is the "
             "manifest tile_size. The atlas is named <N>x<N>.png to match.")
    return ap.parse_args()


TILE_MARKER = re.compile(r"\{tile:([^|{}]+)\|(.)\}")
KEY_MARKER = re.compile(r"\{key:([^{}]+)\}")
CMD_ROW = re.compile(r'\{\s*"((?:[^"\\]|\\.)*)"\s*,\s*\{([^}]*)\}')
CHAR_LIT = re.compile(r"'(\\.|[^'])'")


def fa_tree():
    """The FAangband clone this repo installs into, if it is beside us."""
    for cand in (os.environ.get("HL_FA_DIR"), ROOT.parent / "FAangband"):
        if cand and Path(cand).joinpath("src/ui-game.c").is_file():
            return Path(cand)
    return None


def cmd_rows(text):
    """(desc, (standard key, roguelike key)) for each cmd_info row in C source."""
    rows = []
    for desc, keys in CMD_ROW.findall(text):
        # Classify each slot separately: a bare 'x' is a printable key, while
        # KTRL('T') or a named keycode is not one a help file can show as a
        # single character.  Matching char literals loosely would read
        # KTRL('T') as plain "T" and document the wrong key.
        slots = []
        for part in keys.split(","):
            part = part.strip()
            lit = CHAR_LIT.fullmatch(part)
            slots.append(lit.group(1).replace("\\", "") if lit else None)
        if not slots:
            continue
        std = slots[0]
        rogue = slots[1] if len(slots) > 1 else std
        if rogue is None and len(slots) > 1:
            rogue = False     # bound, but not printable -- never tokenisable
        rows.append((desc, (std, rogue)))
    return rows


def patched_cmd_rows():
    """(rows our patches add, descriptions they take away) for ui-game.c.

    The help files are written against the PATCHED game -- song-cmd-* renames
    "Cast a spell" to "Sing a song" -- but install.sh builds (step 1) before it
    applies the patches (step 5), so on a fresh or freshly-reset tree ui-game.c
    still carries upstream's wording and every {key:} token naming a renamed
    command would be reported as unknown.  Reading patches.json here closes
    that gap from the same single source of truth that does the renaming, and
    is correct whichever state the tree is in: on an already-patched tree the
    added rows are present anyway and the replaced anchors are already gone.
    """
    path = ROOT / "patches" / "patches.json"
    if not path.is_file():
        return [], set()
    added, removed = [], set()
    for rec in json.loads(path.read_text(encoding="utf-8")).get("patches", []):
        if not rec.get("file", "").endswith("ui-game.c"):
            continue
        added.extend(cmd_rows(rec.get("payload", "")))
        # Only a "replace" consumes its anchor; before/after leave it in place.
        if rec.get("where") == "replace":
            removed.update(desc for desc, _ in cmd_rows(rec.get("anchor", "")))
    return added, removed


def load_keysets(fa):
    """desc -> (standard key, roguelike key) from the cmd_info tables.

    Keys are the game's own, read from source rather than remembered: the
    roguelike slot falls back to the standard key when unset, exactly as
    cmd_init does.  Also returns the set of keys the roguelike movement
    keymaps shadow, which a fallback cannot escape.
    """
    src = (fa / "src/ui-game.c").read_text(encoding="utf-8", errors="replace")
    cmds = {}
    for desc, slots in cmd_rows(src):
        cmds.setdefault(desc, slots)
    added, removed = patched_cmd_rows()
    for desc in removed:
        cmds.pop(desc, None)
    for desc, slots in added:
        cmds[desc] = slots

    shadowed = set()
    pref = fa / "lib/customize/pref.prf"
    if pref.is_file():
        for line in pref.read_text(encoding="utf-8", errors="replace").split("\n"):
            if line.startswith("keymap-input:1:"):
                trigger = line[len("keymap-input:1:"):]
                if len(trigger) == 1:
                    shadowed.add(trigger)
    return cmds, shadowed
HELP_TILE_MAX = 1024   # must match HELP_TILE_MAX in the help-tile-code patch
HELP_LINE_BYTES = 1000  # ui-help.c reads lines into char[1024]


def write_lf(path, text):
    """Write text with LF line endings on every platform.

    Path.write_text() opens in text mode, so on Windows every "\\n" here would
    be written as "\\r\\n" -- and these are not files a human reads.  A stray CR
    lands inside a filename in the generated lib/tiles/Makefile, inside a frame
    count in anim.txt, and inside the prf tokens the engine parses; make and the
    C readers take it as data, so the failure is a wrong path or a wrong number
    rather than an error.  (write_text() gained a newline= argument only in
    3.10; this project supports 3.6, hence open().)
    """
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def fnv1a(text):
    """32-bit FNV-1a over the UTF-8 bytes -- the hash the help-tile patch uses."""
    h = 2166136261
    for byte in text.encode("utf-8"):
        h = ((h ^ byte) * 16777619) & 0xFFFFFFFF
    return h


def build_help(m):
    """Resolve {tile:<entity>|<glyph>} markers in help-source/ into dist/help/.

    Each marker is replaced by its one-character ASCII fallback glyph, so the
    shipped file stays plain text of exactly the width the author saw -- line
    wrapping, `/` search and the browser's highlight all keep working.  The
    atlas cell to draw over that column instead, when the SDL2 front end is
    running with graphics, goes into help-tiles.idx keyed on a hash of the
    emitted line rather than its number: the browser skips RST directives when
    it counts lines, and hashing needs no such rule.

    Read by the help-tile-* patch group.  Missing index, ASCII mode, or an
    unpatched tree all degrade to the fallback glyph.
    """
    src = ROOT / "help-source"
    topics = sorted(src.glob("*.txt")) if src.is_dir() else []
    if not topics:
        return

    # Exact entity-string lookup: "monster:warg", "feat:open floor:*".
    cells = {}
    for t in m["tiles"]:
        for entity in t.get("maps", []):
            cells[entity] = (t["row"], t["col"])
        # Art-only tiles (empty maps[], so no prf line is emitted) may still be
        # named for the help text via "help": decorative initials and the like,
        # which are pictures rather than game entities.
        if t.get("help"):
            cells[t["help"]] = (t["row"], t["col"]) + block_of(t)

    outdir = ROOT / "dist" / "help"
    outdir.mkdir(parents=True, exist_ok=True)
    for stale in outdir.iterdir():
        stale.unlink()

    fa = fa_tree()
    cmds, shadowed = load_keysets(fa) if fa else ({}, set())
    if not fa:
        print("help: no FAangband tree found -- {key:...} tokens NOT verified")

    errors = []
    index = []
    n_plates = 0
    n_keys = 0
    for i, topic in enumerate(topics):
        raw = topic.read_text()
        # file_getl() strips CR/LF but not trailing spaces, and expands tabs to
        # 4-column stops; rather than reimplement that, forbid tabs outright.
        lines = raw.rstrip("\n").split("\n")
        emitted = []
        plates = []          # (line index, column, attr, char)
        gutter = []          # (where, line, col, bw, bh) for block capitals
        skipping = False
        for n, line in enumerate(lines):
            line = line.rstrip("\r")
            where = f"{topic.name}:{n + 1}"
            if "\t" in line:
                errors.append(f"{where}: literal tab -- use spaces")
            if not unicodedata.is_normalized("NFC", line):
                errors.append(f"{where}: not NFC-normalised")
            if len(line.encode("utf-8")) > HELP_LINE_BYTES:
                errors.append(f"{where}: line exceeds {HELP_LINE_BYTES} bytes")

            # {key:...} stays in the shipped file and is expanded per reader by
            # the help-key patch, so both keysets must be checked here.
            keys = KEY_MARKER.findall(line)
            if keys and TILE_MARKER.search(line):
                errors.append(
                    f"{where}: a key token and a tile plate on one line -- the "
                    "plate is keyed on the on-disk line, which key expansion "
                    "changes; split them across two lines")
            for desc in keys:
                n_keys += 1
                if not cmds:
                    continue
                if desc not in cmds:
                    errors.append(
                        f"{where}: '{desc}' is no command description in "
                        "ui-game.c's cmd_info tables")
                    continue
                std, rogue = cmds[desc]
                if std is None or rogue is False:
                    errors.append(
                        f"{where}: '{desc}' is bound to a control or named key "
                        "in at least one keyset, which cannot be shown as one "
                        "character -- name it in prose instead")
                elif rogue in shadowed:
                    errors.append(
                        f"{where}: '{desc}' resolves to '{rogue}' in the "
                        "roguelike keyset, which a movement keymap shadows -- "
                        "the token would print a dead key, so write prose "
                        "naming the working path instead")

            # Mirror the browser's RST skipping: a '.. ' directive and every
            # line after it up to a blank one are never drawn, so a marker
            # there would silently never appear.
            drawn = True
            if skipping:
                drawn = False
                if not line.strip():
                    skipping = False
            elif line.startswith(".. "):
                drawn = False
                skipping = True

            out = []
            col = 0
            pos = 0
            for mark in TILE_MARKER.finditer(line):
                out.append(line[pos:mark.start()])
                col += mark.start() - pos
                entity = mark.group(1).strip()
                if entity not in cells:
                    errors.append(
                        f"{where}: tile '{entity}' is mapped by no manifest "
                        "entry -- a wrong plate is worse than none")
                elif not drawn:
                    errors.append(
                        f"{where}: tile marker inside an RST directive block, "
                        "where the browser never draws it")
                elif col >= 80:
                    errors.append(
                        f"{where}: tile at column {col} is off the 80-column "
                        "screen")
                else:
                    cell = cells[entity]
                    row, tcol = cell[0], cell[1]
                    bw, bh = (cell[2], cell[3]) if len(cell) > 2 else (1, 1)
                    for br in range(bh):
                        for bc in range(bw):
                            plates.append((n + br, col + bc,
                                           0x80 + row + br, 0x80 + tcol + bc))
                    if (bw, bh) != (1, 1):
                        # The first cell carries the fallback glyph; every other
                        # cell must be blank gutter the author indented for it,
                        # or the capital would paint over its own prose.
                        gutter.append((where, n, col, bw, bh))
                out.append(mark.group(2))
                col += 1
                pos = mark.end()
            out.append(line[pos:])
            shipped = "".join(out)
            emitted.append(shipped)

            # Width is what the READER sees: plates are already collapsed here,
            # key tokens collapse at display time, and the two keysets can
            # differ in length, so check both.
            for slot, keyset in ((0, "standard"), (1, "roguelike")):
                shown = KEY_MARKER.sub(
                    lambda mk: cmds.get(mk.group(1), ("?", "?"))[slot], shipped)
                if len(shown) > 76:
                    errors.append(
                        f"{where}: renders {len(shown)} columns in the "
                        f"{keyset} keyset")

        for where, n, col, bw, bh in gutter:
            if n + bh > len(emitted):
                errors.append(f"{where}: block capital needs {bh} lines but the "
                              "file ends first")
                continue
            for br in range(bh):
                line_ = emitted[n + br]
                span = line_[col:col + bw] if br else line_[col + 1:col + bw]
                if span.strip():
                    errors.append(
                        f"{where}: block capital overlaps text on line "
                        f"{n + br + 1} -- indent {bw} columns for {bh} lines")
                    break

        if len(plates) > HELP_TILE_MAX:
            errors.append(
                f"{topic.name}: {len(plates)} plates exceeds the loader's "
                f"{HELP_TILE_MAX}-cell limit")

        # The loader matches by hash alone and queues EVERY match, so a plate
        # line sharing a hash with any other line would paint that line too.
        hashes = [fnv1a(line) for line in emitted]
        counts = {}
        for h in hashes:
            counts[h] = counts.get(h, 0) + 1
        for n, col, attr, char in plates:
            if counts[hashes[n]] > 1:
                errors.append(
                    f"{topic.name}:{n + 1}: this line is not unique within the "
                    "file, so its plate would also paint the twin -- reword one")
                continue
            index.append(f"{topic.name}|{hashes[n]:08x}|{col}|{attr}|{char}")
            n_plates += 1

        write_lf(outdir / topic.name, "\n".join(emitted) + "\n")
        _progress("help", i + 1, len(topics))

    if errors:
        sys.exit("help error:\n  " + "\n  ".join(errors))

    write_lf(outdir / "help-tiles.idx", "\n".join([
        "# File: help-tiles.idx",
        "# Generated by tools/build.py -- do not hand-edit.",
        "# <help file>|<FNV-1a of the emitted line>|<column>|<attr>|<char>",
    ] + index) + "\n")
    print(f"help: {len(topics)} topic(s), {n_plates} tile plate(s), "
          f"{n_keys} key token(s) -> dist/help/")


def main():
    args = parse_args()
    m = json.loads((ROOT / "manifest.json").read_text())
    # --size overrides the manifest tile_size; derive the atlas filename from it
    # so the on-disk name and the list.txt `size:` registration stay consistent.
    if args.size is not None:
        if args.size < 1:
            sys.exit(f"--size must be a positive integer (got {args.size})")
        m["tileset"]["tile_size"] = args.size
        m["tileset"]["atlas"] = f"{args.size}x{args.size}.png"
    ts = m["tileset"]["tile_size"]
    tiles = m["tiles"]

    rows = max(t["row"] + block_of(t)[1] - 1 for t in tiles) + 1
    # Animated tiles extend rightward into (col + frame) columns; size for that.
    # Block tiles (illuminated capitals) extend both right and down.
    cols = max(t["col"] + max(len(frame_sources(t)), block_of(t)[0]) - 1
               for t in tiles) + 1
    atlas = Image.new("RGBA", (cols * ts, rows * ts), (0, 0, 0, 0))

    seen = set()
    anim_entries = []   # (row, col, nframes) for tiles with >1 frame
    n_tiles = len(tiles)
    for i, t in enumerate(tiles):
        frames = frame_sources(t)
        base_row, base_col = t["row"], t["col"]
        bw, bh = block_of(t)
        if (bw, bh) != (1, 1):
            # An illuminated capital is ONE drawing spread over a bw x bh grid
            # of cells: slice it here so the art can be authored (and judged) as
            # a single letter rather than as a dozen unreadable fragments.
            if len(frames) > 1:
                sys.exit(f"manifest error: {frames[0]} is both animated and a "
                         "block tile; frames and block cannot combine")
            if t.get("ground") or t.get("margin"):
                sys.exit(f"manifest error: {frames[0]} combines block with "
                         "ground/margin; both assume a single square cell")
            whole = render_tile_image(t, frames[0], ts, block=(bw, bh))
            for br in range(bh):
                for bc in range(bw):
                    pos = (base_row + br, base_col + bc)
                    if pos in seen:
                        sys.exit(f"manifest error: duplicate grid cell {pos} "
                                 f"(block {frames[0]})")
                    seen.add(pos)
                    if pos[0] > 0x7F or pos[1] > 0x7F:
                        sys.exit(f"manifest error: cell {pos} beyond the "
                                 "128x128 prf limit")
                    atlas.paste(whole.crop((bc * ts, br * ts,
                                            (bc + 1) * ts, (br + 1) * ts)),
                                (pos[1] * ts, pos[0] * ts))
            _progress("tiles", i + 1, n_tiles)
            continue
        for fi, fsrc in enumerate(frames):
            col = base_col + fi
            pos = (base_row, col)
            if pos in seen:
                detail = f" (frame {fi} of {frames[0]})" if len(frames) > 1 else ""
                sys.exit(f"manifest error: duplicate grid cell {pos}{detail}")
            seen.add(pos)
            if base_row > 0x7F or col > 0x7F:
                sys.exit(f"manifest error: cell {pos} beyond the 128x128 prf limit")
            atlas.paste(render_tile_image(t, fsrc, ts), (col * ts, base_row * ts))
        if len(frames) > 1:
            anim_entries.append((base_row, base_col, len(frames)))
        _progress("tiles", i + 1, n_tiles)

    # Player variants: conditional player sprites keyed on $RACE/$CLASS/$GENDER.
    # Place them on the atlas now (before palette snap) so they get snapped too.
    pvars = m.get("player_variants", [])
    n_pvars = len(pvars)
    for i, pv in enumerate(pvars):
        pos = (pv["row"], pv["col"])
        if pos in seen:
            sys.exit(f"manifest error: duplicate grid cell {pos} (player variant)")
        seen.add(pos)
        if pv["row"] > 0x7F or pv["col"] > 0x7F:
            sys.exit(f"manifest error: cell {pos} beyond the 128x128 prf limit")
        # Player variants get the identical chroma/resize/fringe treatment as
        # tiles (they carry no margin/ground/frames keys, so those steps no-op).
        img = render_tile_image(pv, pv["source"], ts)
        need_w = (pv["col"] + 1) * ts
        need_h = (pv["row"] + 1) * ts
        if need_w > atlas.width or need_h > atlas.height:
            new_w = max(atlas.width, need_w)
            new_h = max(atlas.height, need_h)
            new_atlas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
            new_atlas.paste(atlas, (0, 0))
            atlas = new_atlas
        atlas.paste(img, (pv["col"] * ts, pv["row"] * ts))
        _progress("player variants", i + 1, n_pvars)

    # Lock the whole atlas to the theme palette (art-direction rule 1). This is
    # the cohesion guarantee: every tile snaps to the same colors.
    palette = load_palette()
    if palette:
        sys.stderr.write("  snapping palette ... ")
        sys.stderr.flush()
        atlas = snap_to_palette(atlas, palette)
        sys.stderr.write("done\n")
        print(f"palette: snapped to {len(palette)} locked colors")
    else:
        print("palette: WARNING — no palette.json; tiles are NOT palette-locked "
              "(see /tileset art-direction rule 1)")

    # Clear near-invisible feathering/fringe from the whole atlas at once. NOTE:
    # this runs before the shape blank-cell guard below, so that guard's "zero
    # opaque pixels" test now means "zero pixels >= ALPHA_FLOOR alpha" — a
    # correct strengthening (a near-invisible shape sprite should also fail).
    atlas = floor_alpha(atlas)

    # Guard: every shapechange sprite must resolve to visible art. A `shapes`
    # entry only binds a transform name to a grid cell (emitting a `shape:` prf
    # line); it carries no art of its own, so the cell must be painted by a
    # co-located tiles[] entry (a monster tile, or a maps:[] art-only tile). If
    # that cell is fully transparent, the engine swaps the player sprite to a
    # blank tile mid-shapechange and the character icon vanishes in-game
    # (fa-playtest case 002: a low-level Beorning's "bear cub" form). Catch it at
    # build time so this class of bug can never ship silently again.
    blank_shapes = []
    for sh in m.get("shapes", []):
        x0, y0 = sh["col"] * ts, sh["row"] * ts
        alpha = atlas.crop((x0, y0, x0 + ts, y0 + ts)).split()[3]
        if alpha.getextrema()[1] == 0:   # max alpha 0 -> zero opaque pixels
            blank_shapes.append((sh["name"], sh["row"], sh["col"]))
    if blank_shapes:
        detail = "; ".join(f"'{n}' at cell ({r},{c})" for n, r, c in blank_shapes)
        sys.exit(
            "manifest error: shapechange sprite(s) map to a fully transparent "
            "atlas cell, so the player icon would vanish in-game -- add a tiles[] "
            f"entry with art at that cell (or point the shape at a painted cell): "
            f"{detail}")

    outdir = ROOT / "dist" / m["tileset"]["directory"]
    outdir.mkdir(parents=True, exist_ok=True)
    # Drop atlases left by a previous build at a different --size, so dist/ (and
    # the wholesale copy install.sh does) never carries an orphaned PNG.
    for old in outdir.glob("*.png"):
        if re.fullmatch(r"\d+x\d+\.png", old.name) and old.name != m["tileset"]["atlas"]:
            old.unlink()
    # Same for prf files this build no longer emits (e.g. the per-gender
    # xtra-*-male/-female.prf a pre-2026-07 build wrote). Every prf here is
    # generated, and install.sh copies the directory wholesale, so a leftover
    # would be deployed forever -- inert, since nothing %:-includes it, but it
    # would outlive every explanation of what it was.
    for old in outdir.glob("*.prf"):
        old.unlink()
    if atlas.width > MAX_TEXTURE or atlas.height > MAX_TEXTURE:
        print(f"WARNING: atlas is {atlas.width}x{atlas.height}px, over the "
              f"{MAX_TEXTURE}px texture limit on some GPUs -- it may fail to "
              f"load in the SDL2 front-end. Consider a smaller --size.",
              file=sys.stderr)
    atlas.save(outdir / m["tileset"]["atlas"])

    prf = [
        f"# File: {m['tileset']['pref']}",
        "#",
        "# Generated by tools/build.py from manifest.json -- do not hand-edit.",
        "",
    ]
    # Warm the "Dark" colour (index 0) to the tile background tone, so untiled
    # cells, panel backgrounds and the unexplored void blend with the tiles
    # instead of reading as stark black. This is a `color:` pref directive
    # shipped IN the tileset (parsed by ui-prefs; the SDL2 front-end re-reads
    # the table on TERM_XTRA_REACT) -- it needs no engine change and applies for
    # anyone who installs the tileset. Reset on switching to another tileset.
    dark = m["tileset"].get("dark_colour")
    if dark:
        r, g, b = (int(dark.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        prf += [
            f"# Dark (index 0) -> {dark} to match the tile background.",
            f"color:0:0:{r}:{g}:{b}",
            "",
        ]
    # Flavored items (potions/scrolls/wands/rods/staves/mushrooms) are mapped by
    # FLAVOR INDEX in a sibling flvr-*.prf, which the graphics prf pulls in via a
    # `%:` include (mirrors the stock tilesets). A tile lists its covered indices
    # in a "flavors" array; every index maps to that one category icon.
    flavor_pref = m["tileset"]["pref"].replace("graf-", "flvr-", 1)
    flvr = [
        f"# File: {flavor_pref}",
        "#",
        "# Generated by tools/build.py from manifest.json -- do not hand-edit.",
        "",
    ]
    flvr_header_len = len(flvr)
    for t in tiles:
        attr = 0x80 + t["row"]
        char = 0x80 + t["col"]
        for entity in t["maps"]:
            prf.append(f"{entity}:0x{attr:02X}:0x{char:02X}")
        for idx in t.get("flavors", []):
            flvr.append(f"flavor:{idx}:0x{attr:02X}:0x{char:02X}")

    # Shapechange sprites: bind a tile to each player shape by name. The engine
    # patch (HITHER-LANDS:shape-parser) adds the `shape:` prf directive and uses
    # shape_x_attr[sidx] when the player is shapechanged. No ASCII default, so in
    # non-graphics mode the player keeps the '@' glyph.
    shapes = m.get("shapes", [])
    if shapes:
        prf += ["", "# Shapechange sprites (player tile while transformed):"]
        for sh in shapes:
            attr = 0x80 + sh["row"]
            char = 0x80 + sh["col"]
            prf.append(f"shape:{sh['name']}:0x{attr:02X}:0x{char:02X}")

    has_flavors = len(flvr) > flvr_header_len
    if has_flavors:
        prf += ["", "# Flavored-item appearances (mapped by flavor index):",
                f"%:{flavor_pref}"]

    # The light-mode plate ships INSIDE the tileset directory, beside the dark
    # atlas, because that is the only place the runtime can find it: the
    # display-lightmode-atlas patch derives its path from the loaded graphics
    # mode's own directory and atlas filename. It is deliberately NOT added to
    # list-stanza.txt -- it is this tileset wearing a different theme, not a
    # second tileset, so it must never appear in the tileset menu (two entries
    # sharing one set of prf coordinates is a trap, not a feature).
    # Written at the end of the build by build_light_atlas.py; named here so the
    # `make install` deploy path, which copies via DATA, carries it too.
    #
    # light.txt rides along for the same reason and is just as load-bearing: it
    # carries the light-mode void tone, which the runtime CANNOT re-derive (the
    # C-side transform serves text and no longer agrees with the atlas one).
    # Omitted from DATA it would install-and-vanish, and light mode would come
    # back with unlit grids brighter than lit ground -- the silent-fallback
    # failure the light plate itself already had once.
    data_files = (f"{m['tileset']['atlas']} {light_atlas_name(m)} light.txt "
                  f"{m['tileset']['pref']}")
    if has_flavors:
        data_files += f" {flavor_pref}"

    # Generate the xtra-*.prf for player variants (conditional prf lines).
    #
    # Gender is a RUNTIME choice made at character generation: the
    # HITHER-LANDS:pgender-* patch group adds a birth stage that sets the
    # `birth_female_sprite` option plus a `$GENDER` pref variable that reads it,
    # so `?:[EQU $GENDER Female]` resolves exactly like the $RACE / $CLASS
    # conditions already do. Prefs are re-processed after birth (ui-game.c
    # play_game -> EVENT_LEAVE_INIT -> reset_visuals), so the choice takes
    # effect for the character that just chose it.
    #
    # ONE file carries both genders: every race/class group emitted for Male,
    # UNGATED, then every group again for Female behind a $GENDER gate. prf is
    # last-match-wins, so the gated block wins wherever $GENDER resolves.
    # The first block must never be gated: on an engine without the pgender
    # patches an unknown $VAR expands to the placeholder "?o?o?", so every gated
    # line is skipped -- the ungated block is what keeps such a tree showing a
    # complete set of player sprites. Which gender that unreachable-on-a-patched-
    # tree fallback happens to show is arbitrary; it is not a setting, and there
    # is deliberately no build- or install-time gender option.
    if pvars:
        xtra_pref = m["tileset"]["pref"].replace("graf-", "xtra-", 1)

        # Two ordering invariants, both load-bearing (prf = last match wins):
        #   1. Class-only groups sort before race+class, so the more specific
        #      line is the later match and wins.
        #   2. The gated block repeats ALL groups in that same order, so it
        #      shadows the ungated block whole. A partial second block would let
        #      a gated class-only line outrank an ungated race+class one.
        groups = {}
        for pv in pvars:
            key = (pv.get("race", ""), pv.get("class", ""))
            g = "Female" if pv.get("gender") == "Female" else "Male"
            groups.setdefault(key, {})[g] = pv
        order = sorted(groups, key=lambda k: (1 if k[0] else 0, k[0],
                                              1 if k[1] else 0, k[1]))

        def block(gender, gated):
            """One pass over every group. A group with no art for the wanted
            gender falls back to whatever tile that group does have."""
            out = []
            for race, cls in order:
                choices = groups[(race, cls)]
                pv = choices.get(gender) or next(iter(choices.values()))
                attr = 0x80 + pv["row"]
                char = 0x80 + pv["col"]
                conds = []
                if gated:
                    conds.append(f"[EQU $GENDER {gender}]")
                if cls:
                    conds.append(f"[EQU $CLASS {cls}]")
                if race:
                    conds.append(f"[EQU $RACE {race}]")
                if len(conds) == 1:
                    out.append(f"?:{conds[0]}")
                elif len(conds) > 1:
                    out.append(f"?:[AND {' '.join(conds)}]")
                out.append(f"monster:<player>:0x{attr:02X}:0x{char:02X}")
            return out

        lines = [
            f"# File: {xtra_pref}",
            "#",
            "# Generated by tools/build.py from manifest.json -- do not hand-edit.",
            "#",
            "# Player sprites keyed on $RACE / $CLASS / $GENDER. Both genders ship",
            "# here; the character's own choice at birth picks between them",
            "# (HITHER-LANDS:pgender-* patches). The ungated block is only the",
            "# fallback for a tree without those patches, where $GENDER cannot resolve.",
            "",
            "# Male -- ungated, and the fallback when $GENDER cannot resolve:",
        ] + block("Male", False) + [
            "",
            "# Female -- wins wherever the engine resolves $GENDER:",
        ] + block("Female", True)
        write_lf(outdir / xtra_pref, "\n".join(lines) + "\n")

        prf += ["", "# Player variant sprites (race/class/gender; gender chosen at birth):",
                f"%:{xtra_pref}"]
        data_files += f" {xtra_pref}"

        # Per-race tiles for PLAYER-flag monsters (e.g. "Ent cutpurse"): reuse
        # each race's Warrior player sprite. Unlike the player's own tile, these
        # must load regardless of the install-time player gender (a monster's
        # gender is its own), so they go in the always-loaded graphics prf rather
        # than the gendered xtra files. prace: = male/default row; prace-female:
        # = female row; the engine (ui-map.c HITHER-LANDS:prace-render-grid) picks
        # per monster -- RF_FEMALE pins female, RF_MALE professions randomise.
        prace_male, prace_female = {}, {}
        for pv in pvars:
            if pv.get("class") != "Warrior" or not pv.get("race"):
                continue
            cell = (0x80 + pv["row"], 0x80 + pv["col"])
            if pv.get("gender") == "Female":
                prace_female[pv["race"]] = cell
            else:
                prace_male[pv["race"]] = cell
        if prace_male or prace_female:
            prf += ["", "# Per-race tiles for PLAYER-flag monsters (race-prefixed",
                    "# persons like 'Ent cutpurse'): reuse each race's Warrior sprite."]
            for race in sorted(prace_male):
                a, c = prace_male[race]
                prf.append(f"prace:{race}:0x{a:02X}:0x{c:02X}")
            for race in sorted(prace_female):
                a, c = prace_female[race]
                prf.append(f"prace-female:{race}:0x{a:02X}:0x{c:02X}")

    # Write all prf/data files now that all sections are assembled.
    if has_flavors:
        write_lf(outdir / flavor_pref, "\n".join(flvr) + "\n")
    write_lf(outdir / m["tileset"]["pref"], "\n".join(prf) + "\n")

    # Animation table: frame counts per base cell, read by the SDL2 front-end
    # (HITHER-LANDS:tile-anim patches). Frame k of a base tile lives at atlas
    # column (col + k) of the same row. Listed in DATA so `make install`
    # deploys it alongside the atlas/prf.
    if anim_entries:
        anim = [
            "# File: anim.txt",
            "# Generated by tools/build.py from manifest.json -- do not hand-edit.",
            "# <row>:<col>:<frames>  (frame k is at atlas column col+k, same row)",
            "",
        ]
        for r, c, n in anim_entries:
            anim.append(f"{r}:{c}:{n}")
        write_lf(outdir / "anim.txt", "\n".join(anim) + "\n")
        data_files += " anim.txt"
        print(f"animation: {len(anim_entries)} animated tile(s) -> anim.txt")

    write_lf(outdir / "Makefile",
        "MKPATH=../../../mk/\n"
        "include $(MKPATH)buildsys.mk\n"
        "\n"
        f"DATA = {data_files}\n"
        "\n"
        f"PACKAGE = tiles/{m['tileset']['directory']}\n"
    )

    alpha = 1 if m["tileset"].get("alpha") else 0
    write_lf(ROOT / "dist" / "list-stanza.txt",
        f"name:@SERIAL@:{m['tileset']['name']}\n"
        f"directory:{m['tileset']['directory']}\n"
        f"size:{ts}:{ts}:{m['tileset']['atlas']}\n"
        f"pref:{m['tileset']['pref']}\n"
        f"extra:{alpha}:0:0\n"
    )

    build_help(m)

    # Tier-1 illustrated PDF (issue #13 D8): text + embedded tile art, fully
    # deterministic off help-source/ + the atlas we just built, so it stays in
    # lockstep with every build.  Optional dependency (reportlab): a clean
    # notice and skip if it is absent, never a build failure.
    try:
        import build_pdf
        build_pdf.build_pdf(m)
    except Exception as e:  # pragma: no cover - export is best-effort
        print(f"pdf: skipped ({type(e).__name__}: {e})")

    # Pinned LIGHT atlas (issue #13 D9): a locked luminance transform of the
    # dark atlas we just built, kept in lockstep so the runtime light/dark
    # toggle never drifts.  No source art is redrawn.  Best-effort.
    try:
        import build_light_atlas
        build_light_atlas.build_light_atlas(m)
    except Exception as e:  # pragma: no cover
        print(f"light: skipped ({type(e).__name__}: {e})")

    mapped = sum(len(t["maps"]) for t in tiles)
    pvcount = len(pvars)
    print(f"built {len(tiles) + pvcount} tiles ({rows}x{cols}+ atlas), "
          f"{mapped} prf mappings, {pvcount} player variants -> {outdir}")


if __name__ == "__main__":
    main()
