# hither-lands

A 32x32 graphical tileset for [FAangband](https://github.com/NickMcConnell/FAangband),
distributed as a separate repo that installs into an FAangband source tree.
Tile art is AI-generated (Gemini via nanobanana-mcp); the atlas, prf mapping
file, and build-system registration are all generated from `manifest.json`.

## Layout

- `manifest.json` — single source of truth: tileset metadata plus one entry
  per tile (source image, atlas grid position, list of game entities it maps).
- `source-tiles/` — the "source code": one PNG per tile at render size
  (512px), named by entity. Committed, because AI generation is not
  reproducible.
- `tools/build.py` — composites `dist/<dir>/` from the manifest: the 32x32
  atlas PNG, the `graf-*.prf` (entity -> 0x80+row : 0x80+col), a buildsys
  Makefile, and the `list.txt` stanza.
- `tools/make_placeholders.py` — draws crude placeholder tiles for any
  manifest entry with no source image yet (never overwrites real art).
- `install.sh [fa-tree]` — copies `dist/` into the FAangband source tree and
  idempotently registers the tileset in `lib/tiles/list.txt` and the tiles
  `Makefile`; FAangband's `make install` then deploys it.

## Pipeline

```sh
tools/make_placeholders.py      # or drop real renders into source-tiles/
tools/build.py
./install.sh ~/lab/FAangband
make -C ~/lab/FAangband install
faangband -msdl2                # pick "FAangband AI Tiles" in graphics options
```

Tiles render only in the SDL2 (or X11) front-end — never in curses (`-mgcu`).

## Adding tiles

1. Generate or draw the render into `source-tiles/<category>/<slug>.png`.
   AI renders can't carry an alpha channel: generate on solid magenta
   (255,0,255) and set `"chroma": true` on the manifest entry to key it out.
2. Add a manifest entry with an **unused** grid cell (never move existing
   tiles — grid positions are the prf contract) and the entity lines it maps,
   e.g. `feat:<name>:<torch|los|lit|dark|*>`, `monster:<name>`,
   `object:<tval>:<sval-name>`, `monster:<player>`.
3. Rebuild + reinstall (pipeline above). Unmapped entities fall back to their
   ASCII glyphs, so coverage can grow incrementally.

Entity names come from the FAangband gamedata files
(`lib/gamedata/terrain.txt`, `monster.txt`, `object.txt`); the grid maxes out
at 128x128 tiles (prf coordinates are single bytes from 0x80).

## Generation style notes

Keep one locked style prefix for every prompt (e.g. "32x32-readable pixel-art
roguelike sprite, 3/4 top-down view, dark fantasy palette, centered subject,
solid magenta background"), and prefer editing from an approved reference tile
over fresh generations so families of tiles stay coherent. Validate
readability in game early — art that works at 512px is often mud at 32px.

## License

TODO: pick a license for the generated art before publishing.
