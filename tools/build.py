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

    # Player variants: conditional player sprites keyed on $RACE/$CLASS/$GENDER.
    # Place them on the atlas now (before palette snap) so they get snapped too.
    pvars = m.get("player_variants", [])
    for pv in pvars:
        pos = (pv["row"], pv["col"])
        if pos in seen:
            sys.exit(f"manifest error: duplicate grid cell {pos} (player variant)")
        seen.add(pos)
        if pv["row"] > 0x7F or pv["col"] > 0x7F:
            sys.exit(f"manifest error: cell {pos} beyond the 128x128 prf limit")
        src = ROOT / "source-tiles" / pv["source"]
        if not src.is_file():
            sys.exit(f"missing source tile: {src}")
        img = Image.open(src)
        if pv.get("chroma") == "family":
            img = key_out_chroma(img, family=True)
        elif pv.get("chroma"):
            img = key_out_chroma(img)
        img = img.convert("RGBA").resize((ts, ts), Image.LANCZOS)
        need_w = (pv["col"] + 1) * ts
        need_h = (pv["row"] + 1) * ts
        if need_w > atlas.width or need_h > atlas.height:
            new_w = max(atlas.width, need_w)
            new_h = max(atlas.height, need_h)
            new_atlas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
            new_atlas.paste(atlas, (0, 0))
            atlas = new_atlas
        atlas.paste(img, (pv["col"] * ts, pv["row"] * ts))

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

    has_flavors = len(flvr) > flvr_header_len
    if has_flavors:
        prf += ["", "# Flavored-item appearances (mapped by flavor index):",
                f"%:{flavor_pref}"]

    data_files = f"{m['tileset']['atlas']} {m['tileset']['pref']}"
    if has_flavors:
        data_files += f" {flavor_pref}"

    # Generate the xtra-*.prf for player variants (conditional prf lines).
    if pvars:
        xtra_pref = m["tileset"]["pref"].replace("graf-", "xtra-", 1)
        xtra = [
            f"# File: {xtra_pref}",
            "#",
            "# Generated by tools/build.py from manifest.json -- do not hand-edit.",
            "#",
            "# Conditional player sprites: $RACE / $CLASS / $GENDER.",
            "",
        ]

        def sort_key(pv):
            has_race = 1 if pv.get("race") else 0
            race = pv.get("race", "")
            has_class = 1 if pv.get("class") else 0
            cls = pv.get("class", "")
            is_female = 1 if pv.get("gender") == "Female" else 0
            return (has_race, race, has_class, cls, is_female)

        for pv in sorted(pvars, key=sort_key):
            attr = 0x80 + pv["row"]
            char = 0x80 + pv["col"]
            conds = []
            if pv.get("class"):
                conds.append(f"[EQU $CLASS {pv['class']}]")
            if pv.get("race"):
                conds.append(f"[EQU $RACE {pv['race']}]")
            if pv.get("gender") == "Female":
                conds.append("[EQU $GENDER Female]")
            if len(conds) == 1:
                xtra.append(f"?:{conds[0]}")
            elif len(conds) > 1:
                xtra.append(f"?:[AND {' '.join(conds)}]")
            xtra.append(f"monster:<player>:0x{attr:02X}:0x{char:02X}")

        prf += ["", "# Player variant sprites (conditional on race/class/gender):",
                f"%:{xtra_pref}"]
        (outdir / xtra_pref).write_text("\n".join(xtra) + "\n")
        data_files += f" {xtra_pref}"

    # Write all prf/data files now that all sections are assembled.
    if has_flavors:
        (outdir / flavor_pref).write_text("\n".join(flvr) + "\n")
    (outdir / m["tileset"]["pref"]).write_text("\n".join(prf) + "\n")

    (outdir / "Makefile").write_text(
        "MKPATH=../../../mk/\n"
        "include $(MKPATH)buildsys.mk\n"
        "\n"
        f"DATA = {data_files}\n"
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
    pvcount = len(pvars)
    print(f"built {len(tiles) + pvcount} tiles ({rows}x{cols}+ atlas), "
          f"{mapped} prf mappings, {pvcount} player variants -> {outdir}")


if __name__ == "__main__":
    main()
