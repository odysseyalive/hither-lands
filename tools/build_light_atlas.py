#!/usr/bin/env python3
"""Build the pinned LIGHT-mode atlas from the dark one (issue #13 D9).

Light mode ships as a runtime toggle with the two palettes PINNED, so the SAME
tileset serves both and no sprite is ever redrawn by hand (ledger
DEC-2026-07-23-pinned-light-dark-toggle).  This tool is the build half of that:

  1. Read the locked dark palette (palette.json).
  2. Compute the light palette as a LOCKED luminance transform of it -- hue and
     saturation preserved, lightness inverted, gamma-weighted, then scaled
     (L' = ((1 - L)^GAMMA) * LEVEL in HLS).  Because the light palette is a pure
     function of the dark one, the two can never drift.

     GAMMA and LEVEL are TWO KNOBS DOING DIFFERENT JOBS, and keeping them apart
     is the whole point of having both.  Conflating them is what made the
     original diagnosis hard to follow.

     GAMMA (2.4) darkens the INK relative to the paper.  It is the LEGIBILITY
     knob.  A plain inversion (GAMMA = 1) washed light mode out badly, because
     palette.json is bottom-heavy -- most of its 21 tones are dark -- so
     inverting crowds nearly every pixel into the top of the lightness range.
     Measured on the snaga orc at cell (7,2): its six most-used tones landed at
     L 0.58-0.92, and its outline tone #171310 mapped to #efebe8, which IS the
     light background, so Weber contrast fell from 2.6 in dark mode to 0.23.  At
     GAMMA = 2.4 the same sprite reads at L 0.44 against an L 0.83 ground, Weber
     0.47.  Raising it further costs warm-accent saturation: at 3.0 the clay roof
     reads brown rather than terracotta.  Note the outline and the void are the
     same palette entry, so NO per-colour transform can separate them -- the
     sprite is meant to read by its body against the ground, as in dark mode.

     LEVEL (0.88) scales the WHOLE palette uniformly, paper and ink together.  It
     is the COMFORT knob and it changes no contrast at all: scaling both terms
     leaves (k*Lbg - k*Ls) / (k*Lbg) identical, so Weber stays 0.47 at every
     value.  It exists because GAMMA deliberately barely moves the top of the
     range -- the void went only L 0.93 -> 0.83 -- so the paper stayed near-white
     and glared even once the sprites were legible.

     NEVER reach for LEVEL as a contrast fix.  A uniform scale preserves whatever
     ratio it is given, so lowering it against a washed-out palette yields only a
     beige version of the same mush.  That is precisely why "just darken the
     background" was never available as a fix for the original washout, and why
     the gamma had to come first.
  3. Copy the dark atlas, then remap ONLY the ground surfaces onto the light
     palette: dark_palette[i] -> light_palette[i].  Everything else ships byte
     for byte as drawn.

     THE SPLIT IS THE POINT, and it replaced a whole-atlas remap on 2026-07-24
     at the owner's direction ("just please, stop inverting the tiles").
     Measured over the 1141 manifest cells: 1096 are transparent
     sprites/objects and only 45 are full-cell opaque surfaces.  Sprites are
     already drawn in DARK tones -- the snaga orc at cell (7,2) averages L 0.25
     -- so as drawn, on the L 0.73 parchment void, they read at Weber 0.66,
     BETTER than the 0.47 they got when the whole plate was inverted.
     Recolouring them was actively making them worse.

     The exception is the ground itself.  floor, grass and road are opaque and
     near-black as drawn (L 0.08-0.09).  They are not objects resting on the
     map, they ARE the map's surface, so leaving them as drawn gives a
     near-black field with a light border -- the same "the map stayed exactly as
     dark as it started" failure described in the display-lightmode-fn patch and
     DEC-2026-07-23-pinned-light-dark-toggle.  Those get lifted; nothing else
     does.  Currently 27 cells qualify.

     NOTE what this costs: the old claim that the remap is "exact and lossless
     because the dark atlas is exactly the 21 locked colours" now holds only for
     the lifted subset.  It is still true there -- the build snap still forces
     those cells onto the palette -- but it is no longer a statement about the
     whole plate.
  4. Emit it INTO dist/<dir>/ as build.light_atlas_name(m) -- beside the dark
     plate, inside the tileset directory -- plus light.txt (the void tone, see
     below) and palettes/{dark,light}.json for inspection.

Why beside the dark plate and not in a directory of its own: the runtime finds
it by name in the loaded graphics mode's own directory (the
HITHER-LANDS:display-lightmode-atlas patch), and install.sh copies the tileset
directory wholesale.  Anywhere else and the plate would build correctly and then
never be installed, which is exactly what it did before 2026-07-24 -- the map
stayed dark through every toggle because the only art that could have re-themed
it was sitting in dist/ and nothing shipped it.

The two halves of light mode use two DIFFERENT transforms, deliberately:
  - the atlas (here) inverts HLS lightness with a gamma, keeping hue and
    saturation, because it is remapping 21 known palette colours and can afford
    to be exact;
  - the 32-colour text/UI table (hl_light_of in the C patch) uses an additive
    luminance shift, because it must guarantee pure black <-> pure white for
    legible text, which a hue-preserving transform does not.

They are not the same function, and as of GAMMA = 2.4 they no longer even agree
on the void.  Until 2026-07-24 they did -- #171310 landed within one unit either
way -- and this file used to say so and emit nothing.  The gamma broke that tie:
the text transform puts the void at #f0ece9 (L 0.93) while the atlas puts it at
#dbd2cb (L 0.83), so unlit and unknown grids would render BRIGHTER than lit
ground, which is backwards.

Hence step 4's light.txt.  The void is emitted from HERE, by the same function
that builds the plate, and the runtime reads it beside anim.txt
(hl_load_light_void, in the display-lightmode-fwd patch) instead of re-deriving
it.  Reimplementing this transform in C was the obvious alternative and is the
wrong one: it would put the locked transform in two languages, which is exactly
the drift that caused the mismatch being fixed here.  A tileset with no
light.txt -- every stock one, or an install predating this -- falls back to
hl_light_of() and behaves as it did before.

Needs numpy on top of build.py's Pillow. build.py calls this best-effort, so a
tree without numpy still builds a working dark tileset -- it just prints
"light: skipped" and the runtime falls through to the dark plate, since the
display-lightmode-atlas patch only swaps a file it can actually find.
"""

import colorsys
import json
import pathlib
import sys

import numpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build as B  # noqa: E402  reuse load_palette + ROOT


# CONTRAST. Weighting on the inverted lightness: darkens the ink relative to the
# paper. 1.0 is a plain inversion and washes the set out (see the module
# docstring); 2.4 is the ratified value. Raising it costs warm-accent saturation
# -- 3.0 renders the clay roof brown rather than terracotta.
GAMMA = 2.4

# COMFORT. Uniform scale on the whole light palette: darkens paper and ink
# together, so Weber contrast is IDENTICAL at every value. 1.0 leaves the
# near-white paper GAMMA alone produces; 0.88 is the ratified value. This is a
# glare control ONLY -- it can never fix a contrast problem, because scaling
# both sides of a ratio does not change it.
LEVEL = 0.88

# WHICH CELLS GET LIFTED AT ALL. A cell is treated as ground -- the map's own
# surface, which must be light in light mode -- only when it fills its cell
# (nothing shows through) AND is too dark as drawn to serve as a light-mode
# background. Everything else is a thing sitting ON the ground and ships exactly
# as drawn. These are measured per cell at build time rather than listed, so
# adding or redrawing a tile reclassifies it automatically.
SURFACE_ALPHA = 0.99      # opaque fraction: a full-cell surface
SURFACE_LIGHTNESS = 0.20  # mean HLS lightness: too dark to be light-mode ground


def light_of(rgb):
    """Locked luminance transform: keep hue+saturation, invert lightness."""
    r, g, b = (c / 255.0 for c in rgb)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    l2 = max(0.0, min(1.0, ((1.0 - l) ** GAMMA) * LEVEL))
    r2, g2, b2 = colorsys.hls_to_rgb(h, l2, s)
    return tuple(round(c * 255) for c in (r2, g2, b2))


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def build_light_atlas(m):
    from PIL import Image

    dark_cols = B.load_palette()
    if not dark_cols:
        print("light: no palette.json -- cannot build a pinned light variant")
        return
    light_cols = [light_of(c) for c in dark_cols]

    # persist both palettes so the pinned relationship is inspectable
    pal_dir = B.ROOT / "palettes"
    pal_dir.mkdir(exist_ok=True)
    dark_src = json.loads((B.ROOT / "palette.json").read_text())
    (pal_dir / "dark.json").write_text(
        json.dumps(dark_src, indent=2) + "\n")
    (pal_dir / "light.json").write_text(json.dumps({
        "name": "Hither Lands (light)",
        "_comment": (f"GENERATED by tools/build_light_atlas.py as a locked "
                     f"luminance transform (L' = ((1 - L)^{GAMMA}) * {LEVEL}, "
                     f"hue/sat kept) of palette.json. GAMMA {GAMMA} sets "
                     f"contrast, LEVEL {LEVEL} sets overall lightness and "
                     f"changes no contrast. Do not hand-edit; edit "
                     f"palette.json and regenerate so the two stay pinned."),
        "colors": [_hex(c) for c in light_cols],
    }, indent=2) + "\n")

    ts = m["tileset"]
    dark_atlas = B.ROOT / "dist" / ts["directory"] / ts["atlas"]
    if not dark_atlas.exists():
        print(f"light: dark atlas {dark_atlas} missing -- run the tile build "
              "first; skipping")
        return
    img = Image.open(dark_atlas).convert("RGBA")
    W, H = img.size

    # The light plate STARTS as a byte-for-byte copy of the dark one, and only
    # the ground surfaces are lifted out of it (see the module docstring). Every
    # sprite therefore ships exactly as drawn.
    arr = numpy.array(img)
    T = m["tileset"]["tile_size"]

    def cell_stats(row, col):
        """Opaque fraction and mean HLS lightness of one atlas cell.

        L = (max+min)/2 per pixel is exactly colorsys' lightness, so this agrees
        with light_of() without paying for a per-pixel Python conversion.
        """
        cell = arr[row * T:(row + 1) * T, col * T:(col + 1) * T]
        a = cell[..., 3]
        opq = float((a != 0).mean())
        px = cell[..., :3][a != 0]
        if px.size == 0:
            return opq, 1.0
        mx = px.max(axis=-1).astype(numpy.float32)
        mn = px.min(axis=-1).astype(numpy.float32)
        return opq, float(((mx + mn) / 2).mean() / 255.0)

    def lift(row, col):
        """Remap one cell's pixels onto the light palette, in place."""
        cell = arr[row * T:(row + 1) * T, col * T:(col + 1) * T]
        rgb = cell[..., :3]
        out_rgb = rgb.copy()
        hit_any = numpy.zeros(rgb.shape[:2], dtype=bool)
        for dark_c, light_c in zip(dark_cols, light_cols):
            hit = numpy.all(rgb == numpy.array(dark_c, dtype=numpy.uint8),
                            axis=-1)
            out_rgb[hit] = light_c
            hit_any |= hit
        rgb[...] = out_rgb
        return int(((cell[..., 3] != 0) & ~hit_any).sum())

    lifted = unmapped = 0
    total = len(m["tiles"])
    for t in m["tiles"]:
        row, col = t["row"], t["col"]
        opq, mean_l = cell_stats(row, col)
        if opq < SURFACE_ALPHA or mean_l >= SURFACE_LIGHTNESS:
            continue
        # Animated tiles occupy col..col+len(frames)-1 on their row. Classify on
        # the BASE cell and lift every frame with it, or the animation flickers
        # between a lifted and an unlifted frame.
        for k in range(max(1, len(t.get("frames") or []))):
            unmapped += lift(row, col + k)
        lifted += 1

    out = dark_atlas.parent / B.light_atlas_name(m)
    Image.fromarray(arr).save(out)

    # The light void tone, emitted beside the plate. The runtime cannot re-derive
    # it: its own hl_light_of() is the text transform, which no longer agrees
    # with this one (module docstring). Emitting it from the function that owns
    # the transform is what keeps the two pinned; a C reimplementation would not.
    dark_void = ts.get("dark_colour", "#171310")
    light_void = light_of(
        tuple(int(dark_void.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
    (out.parent / "light.txt").write_text(
        "# File: light.txt\n"
        "# Generated by tools/build_light_atlas.py -- do not hand-edit.\n"
        "# void:<#rrggbb>  the light-mode tone for COLOUR_DARK (the prf's\n"
        "# color:0), matched to this tileset's -light plate.\n"
        f"\nvoid:{_hex(light_void)}\n")

    print(f"light: {out.relative_to(B.ROOT)} "
          f"({W}x{H}, {lifted} of {total} tiles lifted, "
          f"{unmapped} px off-palette), gamma {GAMMA} level {LEVEL}, "
          f"void {dark_void} -> {_hex(light_void)}")
    return {"dark": dark_cols, "light": light_cols, "unmapped": unmapped}


if __name__ == "__main__":
    manifest = json.loads((B.ROOT / "manifest.json").read_text())
    build_light_atlas(manifest)
