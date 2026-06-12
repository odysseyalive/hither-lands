#!/usr/bin/env python3
"""Draw placeholder source tiles for every entry in manifest.json.

These are deliberately crude PIL drawings whose only job is to validate the
atlas -> prf -> install -> in-game pipeline before real (AI-generated) art
exists. Each placeholder is visually distinct so terrain is identifiable at
32px in game. Real art replaces these files in source-tiles/ one by one;
this script never overwrites an existing file.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 512  # source render size


def base(color):
    img = Image.new("RGBA", (S, S), color)
    return img, ImageDraw.Draw(img)


def floor_img():
    img, d = base((62, 56, 50, 255))
    for x, y in [(100, 140), (300, 80), (420, 300), (180, 400), (350, 440)]:
        d.ellipse([x, y, x + 24, y + 24], fill=(45, 40, 36, 255))
    return img


def draw_unknown():
    img, _ = base((10, 10, 14, 255))
    return img


def draw_wall():
    img, d = base((112, 112, 118, 255))
    for y in range(0, S, 128):
        d.line([(0, y), (S, y)], fill=(70, 70, 76, 255), width=14)
        off = 128 if (y // 128) % 2 else 0
        for x in range(off, S, 256):
            d.line([(x, y), (x, y + 128)], fill=(70, 70, 76, 255), width=14)
    return img


def draw_door(open_):
    img = floor_img()
    d = ImageDraw.Draw(img)
    if open_:
        d.rectangle([80, 40, 432, 472], outline=(130, 86, 40, 255), width=40)
    else:
        d.rectangle([110, 40, 402, 472], fill=(130, 86, 40, 255))
        d.ellipse([330, 230, 370, 270], fill=(220, 190, 90, 255))
    return img


def draw_stair(up):
    img = floor_img()
    d = ImageDraw.Draw(img)
    pts = [(400, 90), (140, 256), (400, 422)] if up else [(112, 90), (372, 256), (112, 422)]
    d.line(pts, fill=(230, 230, 235, 255), width=70, joint="curve")
    return img


def draw_rubble():
    img = floor_img()
    d = ImageDraw.Draw(img)
    for x, y, r in [(150, 200, 90), (300, 280, 110), (240, 130, 70), (380, 160, 60)]:
        d.ellipse([x - r, y - r, x + r, y + r], fill=(130, 130, 136, 255))
    return img


def draw_grass():
    img, d = base((58, 118, 48, 255))
    for x in range(30, S, 80):
        d.line([(x, 420), (x + 20, 300)], fill=(90, 170, 70, 255), width=12)
    return img


def draw_road():
    img, d = base((142, 122, 92, 255))
    d.ellipse([120, 180, 200, 240], fill=(118, 100, 74, 255))
    d.ellipse([320, 320, 410, 380], fill=(118, 100, 74, 255))
    return img


def draw_trees():
    img, d = base((58, 118, 48, 255))
    d.polygon([(256, 50), (90, 380), (422, 380)], fill=(26, 70, 30, 255))
    d.rectangle([226, 380, 286, 470], fill=(96, 64, 30, 255))
    return img


def draw_water():
    img, d = base((40, 80, 170, 255))
    for y in range(100, S, 130):
        d.arc([60, y, 250, y + 80], 200, 340, fill=(120, 170, 230, 255), width=18)
        d.arc([280, y + 40, 470, y + 120], 200, 340, fill=(120, 170, 230, 255), width=18)
    return img


def draw_lava():
    img, d = base((180, 50, 10, 255))
    for x, y, r in [(160, 160, 100), (360, 300, 120), (220, 400, 70)]:
        d.ellipse([x - r, y - r, x + r, y + r], fill=(250, 170, 30, 255))
    return img


def draw_sand():
    img, d = base((205, 178, 120, 255))
    for y in (160, 320):
        d.arc([60, y, 460, y + 160], 180, 360, fill=(178, 150, 95, 255), width=16)
    return img


def draw_empty():
    img, d = base((16, 10, 30, 255))
    d.ellipse([200, 200, 312, 312], fill=(36, 24, 64, 255))
    return img


def draw_player():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([176, 60, 336, 220], outline=(245, 245, 245, 255), width=44)
    d.line([(256, 220), (256, 380)], fill=(245, 245, 245, 255), width=44)
    d.line([(150, 290), (362, 290)], fill=(245, 245, 245, 255), width=40)
    d.line([(256, 380), (170, 480)], fill=(245, 245, 245, 255), width=40)
    d.line([(256, 380), (342, 480)], fill=(245, 245, 245, 255), width=40)
    return img


DRAWERS = {
    "terrain/unknown.png": draw_unknown,
    "terrain/floor.png": floor_img,
    "terrain/wall-granite.png": draw_wall,
    "terrain/door-closed.png": lambda: draw_door(False),
    "terrain/door-open.png": lambda: draw_door(True),
    "terrain/stair-up.png": lambda: draw_stair(True),
    "terrain/stair-down.png": lambda: draw_stair(False),
    "terrain/rubble.png": draw_rubble,
    "terrain/grass.png": draw_grass,
    "terrain/road.png": draw_road,
    "terrain/trees.png": draw_trees,
    "terrain/water.png": draw_water,
    "terrain/lava.png": draw_lava,
    "terrain/sand.png": draw_sand,
    "terrain/empty.png": draw_empty,
    "player/player.png": draw_player,
}


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    made = skipped = 0
    for t in manifest["tiles"]:
        rel = t["source"]
        out = ROOT / "source-tiles" / rel
        if out.exists():
            skipped += 1
            continue
        drawer = DRAWERS.get(rel)
        if drawer is None:
            print(f"no placeholder drawer for {rel} -- provide real art")
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        drawer().save(out)
        made += 1
    print(f"placeholders: {made} drawn, {skipped} already present")


if __name__ == "__main__":
    main()
