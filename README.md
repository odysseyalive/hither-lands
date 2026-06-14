# Hither Lands

A 32x32 AI-generated graphical tileset for
[FAangband](https://github.com/NickMcConnell/FAangband) (First Age Angband),
a single-player roguelike. Over **1,400 tiles** covering fauna, terrain,
objects, player variants, and shapechange forms — all palette-locked to a
warm earthy "Hither Lands" theme and snapped to a 21-color master palette
at build time for visual cohesion. Art is generated via Gemini
(nanobanana-mcp) and built from `manifest.json`.

## Requirements

- **Git**
- **Python 3.6+** with [Pillow](https://python-pillow.org/) (`pip install Pillow`)
- **autoconf / automake** (to bootstrap FAangband's build system)
- **GCC** (or another C99 compiler)
- **ncurses** development headers (e.g. `libncurses-dev` / `ncurses-devel`)
- **SDL2** development headers for the graphical frontend
  (e.g. `libsdl2-dev`, `sdl2-ttf`, `sdl2-image` — or your distro's equivalents)
- **make**

## Quick Start

### 1. Clone FAangband

```sh
git clone https://github.com/NickMcConnell/FAangband.git
```

### 2. Clone this tileset repo

```sh
git clone https://github.com/odysseyalive/hither-lands.git
```

### 3. Bootstrap and configure FAangband

```sh
cd FAangband
./autogen.sh
./configure --with-no-install --enable-sdl2
```

`--with-no-install` runs the game in-place (data stays in the source tree).
`--enable-sdl2` builds the graphical frontend that renders tiles.

### 4. Install the tileset into the FAangband source tree

```sh
cd ../hither-lands
./install.sh ../FAangband
```

This builds the atlas from source tiles, copies it into `lib/tiles/`,
registers the tileset in the build system, and applies any C source patches
(e.g. shapechange tile display). The `--gender male|female` flag selects
player sprite gender (default: male). This process takes a while, so be patient.
There are over 1,400 tiles to integrate!

### 5. Build FAangband

```sh
make -C ../FAangband
```

### 6. Run

```sh
../FAangband/src/faangband -msdl2
```

Select **Hither Lands** in the graphics options menu (`=` > Graphics).

Tiles render only in the SDL2 (or X11) frontend, never in curses (`-mgcu`).

## Layout

- `manifest.json` — single source of truth: tileset metadata plus one entry
  per tile (source image, atlas grid position, game entities it maps).
- `source-tiles/` — one PNG per tile at render size (~512px), named by entity.
  Committed, because AI generation is not reproducible.
- `palette.json` — the locked 21-color theme palette. `build.py` snaps every
  tile to these colors at build time. Edit this to re-theme the whole set
  without regenerating art.
- `tools/build.py` — composites the 32x32 atlas PNG, the `graf-*.prf` mapping
  file, and build-system files into `dist/`.
- `tools/make_placeholders.py` — draws placeholder tiles for manifest entries
  with no source image yet (never overwrites real art).
- `install.sh` — builds the tileset, copies it into an FAangband source tree,
  registers it in `list.txt` and `Makefile`, and applies C source patches.
- `patches/` — anchor-based, idempotent C source patches delivered via
  `install.sh` (e.g. shapechange tile display system).

## Adding Tiles

1. Generate or draw a tile into `source-tiles/<category>/<name>.png`.
   AI renders use a solid magenta (`#FF00FF`) background; set `"chroma": true`
   on the manifest entry to key it out at build time.
2. Add a manifest entry with an **unused** grid cell (never move existing
   tiles — grid positions are baked into prf coordinates) and the entity
   mapping lines, e.g. `feat:<name>:*`, `monster:<name>`,
   `object:<tval>:<name>`.
3. Run `./install.sh <fa-tree>` and `make -C <fa-tree>` to rebuild.
   Unmapped entities fall back to ASCII, so coverage grows incrementally.

Entity names come from FAangband's gamedata files
(`lib/gamedata/terrain.txt`, `monster.txt`, `object.txt`). The atlas grid
maxes at 128x128 (prf coordinates are single bytes from 0x80).

## License

TODO: pick a license for the generated art before publishing.
