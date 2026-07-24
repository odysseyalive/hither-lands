#!/usr/bin/env python3
"""Export the Hither Lands in-game help as an illustrated PDF (issue #13 D8).

A THIRD render target off the same single source as the in-game text
(`help-source/`), so the PDF can never drift from the game's help by being
written separately.  Tier 1 only: plain text plus embedded TILE ART cropped
from the built atlas -- fully deterministic, no running game required, so this
runs as part of `build.py`.  In-game screenshots and bespoke geography plates
are Tier 2 and are added on demand, not here.

Standard keyset only.  A `{key:...}` token is dynamic in-game and cannot live
in a static file, so a footer names the keyset and points roguelike-keyset
players to the in-game help.  Copyrighted `library/*.pdf` sources are never
embedded -- illustrations come only from our own atlas art.

Output: docs/hither-lands-help.pdf  (committed, so it ships and diffs in git).

Requires reportlab + Pillow; degrades with a clear notice if reportlab is
absent, so a Pillow-only environment still builds the atlas.
"""

import io
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build as B  # noqa: E402  reuse marker parsing, keyset load, atlas contract

PDF_OUT = B.ROOT / "docs" / "hither-lands-help.pdf"

# Topics that are the roguelike-keyset twins of a standard topic; the standard
# PDF omits them (their content is the same, only the keyset labels differ).
ROGUELIKE_TWINS = {"r_index.txt", "r_comm.txt"}


def _reading_order(src):
    """Narrative order from index.txt's menu, then any leftover topics."""
    order = []
    idx = src / "index.txt"
    if idx.exists():
        for m in re.finditer(r"menu:: \[.\] ([a-z0-9_]+\.txt)", idx.read_text()):
            if m.group(1) not in order:
                order.append(m.group(1))
    present = {p.name for p in src.glob("*.txt")}
    ordered = [t for t in order if t in present and t not in ROGUELIKE_TWINS]
    rest = sorted(present - set(ordered) - ROGUELIKE_TWINS - {"index.txt"})
    return ["index.txt"] + ordered + rest


def _resolve_line(line, cells, cmds, slot):
    """Return (text, plates) for one source line, mirroring build_help.

    text   -- the line as a reader sees it (tile markers -> fallback glyph,
              key tokens -> the keyset character).
    plates -- list of (column, row, col, bw, bh): where a tile is drawn and
              which atlas cell block it is.  build_help forbids a key token and
              a tile plate on one line, so the two resolutions never interact.
    """
    plates = []
    out = []
    pos = 0
    col = 0
    for mk in B.TILE_MARKER.finditer(line):
        seg = line[pos:mk.start()]
        out.append(seg)
        col += len(seg)
        entity = mk.group(1).strip()
        cell = cells.get(entity)
        if cell is not None:
            row, tcol = cell[0], cell[1]
            bw, bh = (cell[2], cell[3]) if len(cell) > 2 else (1, 1)
            plates.append((col, row, tcol, bw, bh))
        out.append(mk.group(2))          # the fallback glyph
        col += 1
        pos = mk.end()
    out.append(line[pos:])
    text = "".join(out)
    # key tokens: expand to the chosen keyset's single character
    text = B.KEY_MARKER.sub(
        lambda k: (cmds.get(k.group(1), ("?", "?"))[slot] or "?"), text)
    return text, plates


def build_pdf(m, keyset="standard"):
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.utils import ImageReader
    except ImportError:
        print("pdf: reportlab not installed -- skipping PDF export "
              "(pip install reportlab); the atlas build is unaffected")
        return
    from PIL import Image

    src = B.ROOT / "help-source"
    if not src.is_dir():
        print("pdf: no help-source/ -- nothing to export")
        return

    ts = m["tileset"]
    atlas_path = B.ROOT / "dist" / ts["directory"] / ts["atlas"]
    if not atlas_path.exists():
        print(f"pdf: atlas {atlas_path} missing -- run the tile build first; "
              "skipping PDF")
        return
    atlas = Image.open(atlas_path).convert("RGBA")
    TSZ = ts["tile_size"]

    # entity/help-name -> atlas cell (row, col[, bw, bh]); same map build_help uses
    cells = {}
    for t in m["tiles"]:
        for e in t.get("maps", []):
            cells[e] = (t["row"], t["col"])
        if t.get("help"):
            cells[t["help"]] = (t["row"], t["col"]) + B.block_of(t)

    fa = B.fa_tree()
    cmds, _shadowed = B.load_keysets(fa) if fa else ({}, set())
    slot = 0 if keyset == "standard" else 1

    # --- page / type metrics -------------------------------------------------
    PW, PH = letter
    MARGIN = 54
    usable_w = PW - 2 * MARGIN
    FONT = "Courier"
    # size so 76 monospace columns fit the usable width
    char_w = usable_w / 78.0
    size = char_w / 0.6            # Courier advance is 0.6 em
    line_h = size * 1.35
    top = PH - MARGIN
    bottom = MARGIN + line_h * 2  # room for the footer

    c = canvas.Canvas(str(PDF_OUT), pagesize=letter)
    c.setTitle("Hither Lands -- In-Game Help")
    c.setAuthor("Hither Lands tileset for FAangband")

    tile_cache = {}

    def tile_reader(row, col, bw, bh):
        key = (row, col, bw, bh)
        r = tile_cache.get(key)
        if r is None:
            box = (col * TSZ, row * TSZ, (col + bw) * TSZ, (row + bh) * TSZ)
            crop = atlas.crop(box)
            r = ImageReader(crop)
            tile_cache[key] = r
        return r

    def footer():
        c.setFont(FONT, size * 0.85)
        c.setFillGray(0.45)
        c.drawString(MARGIN, MARGIN,
                     "Hither Lands in-game help - standard keyset.  "
                     "Roguelike-keyset players: see the in-game help (?) for "
                     "your own bindings.")
        c.setFillGray(0.0)
        c.setFont(FONT, size)

    y = [top]

    def newpage():
        footer()
        c.showPage()
        c.setFont(FONT, size)
        y[0] = top

    c.setFont(FONT, size)

    for topic in _reading_order(src):
        path = src / topic
        raw = path.read_text().rstrip("\n").split("\n")
        # start each topic on a fresh page
        if y[0] < top:
            newpage()
        skipping = False
        for line in raw:
            line = line.rstrip("\r")
            # mirror the browser's RST skip: '.. ' directive + block never drawn
            if skipping:
                if not line.strip():
                    skipping = False
                continue
            if line.startswith(".. "):
                skipping = True
                continue

            if y[0] < bottom:
                newpage()

            text, plates = _resolve_line(line, cells, cmds, slot)
            # blank out the glyph columns a plate covers, then draw the art over them
            covered = set()
            for (col, row, tcol, bw, bh) in plates:
                for cc in range(bw):
                    covered.add(col + cc)
            shown = "".join(" " if i in covered else ch
                            for i, ch in enumerate(text))
            c.setFont(FONT, size)
            c.setFillGray(0.0)
            c.drawString(MARGIN, y[0], shown)

            for (col, row, tcol, bw, bh) in plates:
                reader = tile_reader(row, tcol, bw, bh)
                if bw == 1 and bh == 1:
                    # single icon: a square a little taller than the line,
                    # centred on its glyph column (tables leave space around it)
                    s = line_h * 1.25
                    x = MARGIN + col * char_w + char_w / 2 - s / 2
                    yy = y[0] - (s - size) / 2
                    c.drawImage(reader, x, yy, s, s, mask="auto")
                else:
                    # block capital: fill the bw x bh cells the author reserved
                    w = bw * char_w
                    h = bh * line_h
                    x = MARGIN + col * char_w
                    yy = y[0] + line_h - h            # grows downward from this line
                    c.drawImage(reader, x, yy, w, h, mask="auto")

            y[0] -= line_h

    footer()
    c.showPage()
    c.save()
    size_kb = PDF_OUT.stat().st_size / 1024
    print(f"pdf: {PDF_OUT.relative_to(B.ROOT)} "
          f"({size_kb:.0f} KB, standard keyset, tile art embedded)")


if __name__ == "__main__":
    import json
    manifest = json.loads((B.ROOT / "manifest.json").read_text())
    build_pdf(manifest)
