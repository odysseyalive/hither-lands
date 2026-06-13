#!/usr/bin/env python3
"""Build the distributable tileset from manifest.json + source-tiles/.

Outputs into dist/<directory>/:
  - the 32x32 atlas PNG (tiles composited at their manifest grid positions)
  - the graf-*.prf mapping file
  - a buildsys Makefile so FAangband's `make install` deploys the tileset
plus dist/list-stanza.txt, the lib/tiles/list.txt entry with @SERIAL@ left
for install.sh to fill in.

Source tiles may be any size; they are downscaled to tile_size. A tile with
"chroma": true has near-magenta (255,0,255) pixels keyed to transparent —
use this for AI-generated renders, which can't emit an alpha channel.
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHROMA = (255, 0, 255)
CHROMA_TOL = 60


FAMILY_TOL = 50  # for "family" mode: how far magenta must dominate green


def key_out_chroma(img, family=False):
    """Make the magenta background transparent.

    Tight mode (default): only near-pure #FF00FF. Safe for sprites that may
    contain legitimate purple/magenta detail.

    Family mode: any pixel where magenta dominates green (r-g and b-g both
    large) — also removes the darkened-magenta drop shadows the generator
    bakes under buildings. Do NOT use on art with genuine purple (the magic
    shop therefore uses a deep-blue roof, which survives this key).
    """
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if family:
                hit = (r - g > FAMILY_TOL) and (b - g > FAMILY_TOL)
            else:
                hit = (abs(r - CHROMA[0]) < CHROMA_TOL
                       and abs(g - CHROMA[1]) < CHROMA_TOL
                       and abs(b - CHROMA[2]) < CHROMA_TOL)
            if hit:
                px[x, y] = (r, g, b, 0)
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


def main():
    m = json.loads((ROOT / "manifest.json").read_text())
    ts = m["tileset"]["tile_size"]
    tiles = m["tiles"]

    rows = max(t["row"] for t in tiles) + 1
    cols = max(t["col"] for t in tiles) + 1
    atlas = Image.new("RGBA", (cols * ts, rows * ts), (0, 0, 0, 0))

    seen = set()
    for t in tiles:
        pos = (t["row"], t["col"])
        if pos in seen:
            sys.exit(f"manifest error: duplicate grid cell {pos}")
        seen.add(pos)
        if t["row"] > 0x7F or t["col"] > 0x7F:
            sys.exit(f"manifest error: cell {pos} beyond the 128x128 prf limit")
        src = ROOT / "source-tiles" / t["source"]
        if not src.is_file():
            sys.exit(f"missing source tile: {src}")
        img = Image.open(src)
        if t.get("chroma") == "family":
            img = key_out_chroma(img, family=True)
        elif t.get("chroma"):
            img = key_out_chroma(img)
        img = img.convert("RGBA").resize((ts, ts), Image.LANCZOS)
        # A terrain feature (e.g. a building) fills its whole cell — the engine
        # draws only one tile per grid square, so transparent corners would
        # show the black terminal background. Bake a ground texture underneath
        # so the tile is opaque and its edges match the surrounding floor.
        # Reusing the same seamless texture the floor uses makes the join
        # invisible. (Monster/player sprites omit "ground" and stay
        # transparent, so the engine composites them over real terrain.)
        if t.get("ground"):
            ground_src = ROOT / "source-tiles" / t["ground"]
            if not ground_src.is_file():
                sys.exit(f"missing ground texture: {ground_src}")
            base = Image.open(ground_src).convert("RGBA").resize(
                (ts, ts), Image.LANCZOS)
            base.alpha_composite(img)
            img = base
        atlas.paste(img, (t["col"] * ts, t["row"] * ts))

    # Lock the whole atlas to the theme palette (art-direction rule 1). This is
    # the cohesion guarantee: every tile snaps to the same colors.
    palette = load_palette()
    if palette:
        atlas = snap_to_palette(atlas, palette)
        print(f"palette: snapped to {len(palette)} locked colors")
    else:
        print("palette: WARNING — no palette.json; tiles are NOT palette-locked "
              "(see /tileset art-direction rule 1)")

    outdir = ROOT / "dist" / m["tileset"]["directory"]
    outdir.mkdir(parents=True, exist_ok=True)
    atlas.save(outdir / m["tileset"]["atlas"])

    prf = [
        f"# File: {m['tileset']['pref']}",
        "#",
        "# Generated by tools/build.py from manifest.json -- do not hand-edit.",
        "",
    ]
    for t in tiles:
        attr = 0x80 + t["row"]
        char = 0x80 + t["col"]
        for entity in t["maps"]:
            prf.append(f"{entity}:0x{attr:02X}:0x{char:02X}")
    (outdir / m["tileset"]["pref"]).write_text("\n".join(prf) + "\n")

    (outdir / "Makefile").write_text(
        "MKPATH=../../../mk/\n"
        "include $(MKPATH)buildsys.mk\n"
        "\n"
        f"DATA = {m['tileset']['atlas']} {m['tileset']['pref']}\n"
        "\n"
        f"PACKAGE = tiles/{m['tileset']['directory']}\n"
    )

    alpha = 1 if m["tileset"].get("alpha") else 0
    (ROOT / "dist" / "list-stanza.txt").write_text(
        f"name:@SERIAL@:{m['tileset']['name']}\n"
        f"directory:{m['tileset']['directory']}\n"
        f"size:{ts}:{ts}:{m['tileset']['atlas']}\n"
        f"pref:{m['tileset']['pref']}\n"
        f"extra:{alpha}:0:0\n"
    )

    mapped = sum(len(t["maps"]) for t in tiles)
    print(f"built {len(tiles)} tiles ({rows}x{cols} atlas), {mapped} prf mappings -> {outdir}")


if __name__ == "__main__":
    main()
