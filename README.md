# Hither Lands

A 64x64 AI-generated graphical tileset for
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

### 3. Bootstrap FAangband

```sh
cd FAangband
```

```sh
./autogen.sh
```

### 4. Configure FAangband with SDL2

```sh
./configure --prefix=$HOME/.local --bindir=$HOME/.local/bin --enable-sdl2
```

- `--prefix=$HOME/.local` installs into your home directory instead of a system
  path, so **no `sudo` is needed**. `make install` then deploys the game's data —
  tiles, fonts, gamedata — to `~/.local/share/faangband/`, which is where the
  installed game reads it at runtime.
- `--bindir=$HOME/.local/bin` puts the `faangband` binary on your `PATH`. This
  prefix's default is `~/.local/games`, which usually isn't on `PATH`;
  `~/.local/bin` normally is, so afterward you can just run `faangband`.
- `--enable-sdl2` builds the SDL2 graphical frontend that renders the tiles.
  Without it you only get the curses/text frontend, which shows ASCII, not tiles.

### 5. Install the tileset into the FAangband source tree

```sh
cd ../hither-lands
```

```sh
./install.sh ../FAangband
```

This builds the atlas from source tiles, copies it into `lib/tiles/`,
registers the tileset in the build system, and applies the C source patches
the tileset needs (see step 6 for what they add).

Use `--size` to select the tile resolution — `32`, `64` (default), or `128`:

```sh
./install.sh ../FAangband --size 64
```

The source tiles are ~1024px native, so `64` and `128` render with real added
detail rather than upscaling. The whole set rebuilds at the chosen size and the
`list.txt` registration is written to match — no engine change is needed, since
FAangband reads each graphics mode's tile dimensions from its registration.

> **Note on `--size 128`:** the atlas grows quadratically and exceeds the 8192px
> texture limit on some GPUs, where it may silently fail to load in the SDL2
> frontend. `build.py` prints a warning when this happens. `32` and `64` are
> well within limits.

This process takes a while — there are over 1,400 tiles to integrate.

### 6. Build and deploy FAangband

```sh
make -C ../FAangband install
```

The `install` target matters. With the `--prefix=$HOME/.local` configure from
step 4, the compiled binary looks for its data **only** in
`~/.local/share/faangband/` — the path is baked in at configure time, and it
never reads the source tree's `lib/`. `make install` both compiles the game and
deploys the game data, including this tileset, to that directory. A plain
`make` compiles but deploys nothing, so the game won't find the tiles (or, on a
first build, any data at all).

**Re-run `make -C ../FAangband install` after every `install.sh`**, for two
reasons: it redeploys the rebuilt tiles, and it recompiles the additions
`install.sh` patches into the game's code. Most are graphics-only:

- **animated tiles** — torches flicker, water ripples.
- **shapeshift sprites** — your character shows a matching picture when it
  transforms into another form.
- **per-race monster sprites** — player-race monsters get their own art
  instead of one shared sprite.
- **a sprite-gender step in character generation**, plus the birth option that
  backs it.
- **tiles and keypresses drawn inside the in-game help browser**, and larger
  default font/tile sizes to suit them.

Two of them do change how the game plays, by design:

- **allies** — a command and UI for recruiting and directing friendly monsters.
- **the faction ecosystem** — some creatures spawn neutral rather than hostile,
  fauna behave less like uniform monsters, packs and territorial races stay near
  where they spawned, and a struck creature can rally its group to its aid.

> If you instead configured with `--with-no-install`, the rule flips: run a
> plain `make -C ../FAangband` and skip `install` — that build mode reads tiles
> straight from this source tree's `lib/`. Either way, `install.sh` detects
> your tree's build mode from `config.log` and prints the correct follow-up
> command at the end of its run.

### 7. Run

```sh
faangband -msdl2
```

Step 4 put the installed binary on your `PATH` (`~/.local/bin`), so this runs
the game with the deployed data. (`../FAangband/src/faangband -msdl2` also
works with this configure — it reads the same installed data — but only after
`make install` has deployed it.)

The game starts in ASCII — tiles are off until you select a tileset, and the
selector is in the SDL2 window's own menu bar, **not** the in-game `=` options
menu. **First start (or load) a character and get into the game world** — the
tile-set entries are greyed out at the title screen, during character
creation, and inside menus; the engine only allows switching at the main
command prompt. Then click **Menu** in the bar at the top of the game window,
then **FAangband** (the first entry — the main window), then **Tiles** >
**Set**, and pick **Hither Lands**. The selection is remembered across sessions.

Then set the tile size under **Tiles** > **Size** (also only available once
tiles are on and you're at the command prompt). On a patched tree the size
already defaults to **width 7 / height 3** when tiles are switched on, so the
rest of this section is tuning rather than required setup. Tiles are stretched
to fill `font cell × multiplier` on screen, and terminal fonts are about twice as tall
as they are wide, so **keep the width multiplier at roughly 2× the height
multiplier** or the square tiles render squashed. With the default `10x20`
font, **width 6 / height 3** hits both marks: square tiles at close to their
native 64px detail. The target is a destination cell of roughly 64px:
`font width × width multiplier` should equal `font height × height multiplier`,
landing near 64.

The **font** is set under **Menu** > **FAangband** > **Font** > **Name** and
couples directly to tile size, so pick the pair together. The bundled bitmap
fonts (`5x8x.fon` … `16x24x.fon`) are fixed-size; only the `16x16xw.woff`
vector font responds to **Font** > **Size**. A comfortable readable combo:
**`12x24x.fon` with tiles at 6×3** (72×72 px tiles, square). Other square
pairings: `8x16` at 8×4 (64px), `16x24` at 3×2 (48px). All of these choices
persist in the frontend's `sdl2init.txt` in its user directory, so they're
one-time setup.

Tiles render only in the SDL2 (or X11) frontend, never in curses (`-mgcu`).

## Troubleshooting

**A rebuilt tileset looks unchanged in-game (e.g. `--size 128` looks identical
to `--size 64`).** Almost always you are launching a *different* binary than the
one this tree builds. `install.sh` writes into the source tree's `lib/tiles/`,
and a `--with-no-install` build reads exactly that (`${PWD}/lib/`). But a
separately *installed* binary — e.g. one built with `--prefix=$HOME/.local` and
`make install`, sitting in `~/.local/bin/faangband` — reads its **own** copy
under `~/.local/share/faangband/tiles/` and never sees your rebuild. Fixes:

- If you followed the Quick Start (`--prefix=$HOME/.local`), re-run
  `install.sh ../FAangband` **and** `make -C ../FAangband install` after every
  tileset change — both the installed `faangband` and the in-place
  `src/faangband` read the deployed copy under `~/.local/share/faangband/`; or
- If your tree is configured `--with-no-install`, run the in-place binary,
  `../FAangband/src/faangband`, after a plain `make` — that build mode reads
  this tree's `lib/tiles/` directly. Build location and run location must match.

To confirm what's actually deployed, compare the registration and atlas the game
reads:

```sh
grep -A4 '^directory:fa-ai' <data-dir>/tiles/list.txt   # size: line = active resolution
```

**Higher `--size` shows no extra detail.** Tiles are scaled to their on-screen
cell at draw time — `font_cell × tile_multiplier` pixels. If that destination is
small (a small font, tile multiplier 1), a 128px tile is downscaled to the same
on-screen size as a 64px or even 32px one, so they look the same. To actually see
the added detail, enlarge the font and/or raise the tile multiplier (Tiles →
Size in the SDL2 menu) so tiles render at roughly their native pixel size. At
ordinary zoom, **64 (the default) is the sweet spot**; `128` only pays off when
tiles are drawn large (big font, hi-DPI) and otherwise just costs ~4× the memory.

## Layout

- `manifest.json` — single source of truth: tileset metadata plus one entry
  per tile (source image, atlas grid position, game entities it maps).
- `source-tiles/` — one PNG per tile at render size (~1024px), named by entity.
  Committed, because AI generation is not reproducible.
- `palette.json` — the locked 21-color theme palette. `build.py` snaps every
  tile to these colors at build time. Edit this to re-theme the whole set
  without regenerating art.
- `tools/build.py` — composites the atlas PNG (64x64 by default; `--size`
  selects 32 or 128), the `graf-*.prf` mapping file, and build-system files
  into `dist/`.
- `tools/make_placeholders.py` — draws placeholder tiles for manifest entries
  with no source image yet (never overwrites real art).
- `install.sh` — builds the tileset, copies it into an FAangband source tree,
  registers it in `list.txt` and `Makefile`, and applies C source patches.
- `patches/` — anchor-based, idempotent C source patches delivered via
  `install.sh`, grouped by id prefix: `shape-*` (shapechange sprites),
  `tile-anim-*` (animation), `prace-*` (per-race monster sprites), `pgender-*`
  (birth-time sprite gender), `help-*`/`display-*` (help-browser tiles and
  display defaults), `ally-*`/`recruit-*` (ally system), `eco-*` (faction
  ecosystem). `patches.json` also pins the upstream FAangband commit every
  anchor was proven against; every run reports drift against it before touching
  anchors.
- `docs/never-regress.md` — **the prime directive**: what every change owes the
  next one, and how the baseline pin enforces it. Read before changing patches,
  the manifest, or the build pipeline.

## Contributing / Maintaining

This project patches a repository that does not know it exists. Read
[`docs/never-regress.md`](docs/never-regress.md) first — it explains the baseline
pin, why a still-matching anchor is not proof of correctness, and the checklist
every change is held to.

```sh
python3 patches/apply_patches.py <fa-tree> --baseline   # upstream drift report
python3 patches/apply_patches.py <fa-tree> --status     # + anchor states, no writes
python3 patches/apply_patches.py <fa-tree> --repin      # advance the pin after a re-author
```

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

MIT
