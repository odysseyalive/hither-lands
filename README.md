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

On Windows, the equivalents come from [MSYS2](https://www.msys2.org/) plus a
python.org install — see [Windows notes](#windows-notes). The Quick Start below
is written in Linux/macOS shell; step 5 gives the PowerShell form of each
command.

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

### 5. Install the tileset, and build the game

There are two installers — the same seven steps, one per platform. Use the one
for your system:

| Platform | Script |
|---|---|
| Linux, macOS | `install.sh` |
| Windows | `install.ps1` |

```sh
cd ../hither-lands
```

**Linux / macOS:**

```sh
./install.sh ../FAangband
```

**Windows** (PowerShell 5.1 or 7, from an MSYS2/MinGW-capable environment —
see [Windows notes](#windows-notes) below):

```powershell
.\install.ps1 ..\FAangband
```

Either script builds the atlas from source tiles, copies it into `lib/tiles/`,
registers the tileset in the build system, applies the C source patches the
tileset needs (see step 6 for what they add), **and then compiles FAangband
for you** — running `make install` or plain `make`, whichever your tree's own
configuration calls for. It finishes by printing the exact command that starts
the game.

Before touching anything, the script checks the FAangband tree for local
changes it did not make itself. If it finds any, it prints them, recommends
stashing them and pulling the latest official source, and asks
`Proceed with installation, Y/n?` — nothing happens until you answer. Pass
`--yes` (`-Yes` in PowerShell) to acknowledge that up front in a script.

Use `--size` to select the tile resolution — `32`, `64` (default), or `128`:

```sh
./install.sh ../FAangband --size 64
```

(In PowerShell the same option is `-Size 64`.)

The source tiles are ~1024px native, so `64` and `128` render with real added
detail rather than upscaling. The whole set rebuilds at the chosen size and the
`list.txt` registration is written to match — no engine change is needed, since
FAangband reads each graphics mode's tile dimensions from its registration.

> **Note on `--size 128`:** the atlas grows quadratically and exceeds the 8192px
> texture limit on some GPUs, where it may silently fail to load in the SDL2
> frontend. `build.py` prints a warning when this happens. `32` and `64` are
> well within limits.

This process takes a while — there are over 1,400 tiles to integrate.

### 6. What the installer just compiled in

Step 5 ran the build itself, so there is no separate `make` to remember. Which
command it ran depends on how you configured the tree in step 4, and the
difference is not cosmetic:

- **`--prefix=$HOME/.local`** (the Quick Start) → `make -C ../FAangband install`.
  The compiled binary looks for its data **only** in
  `~/.local/share/faangband/`; that path is baked in at configure time and it
  never reads the source tree's `lib/`. The `install` target both compiles the
  game and deploys the data, this tileset included. A plain `make` would
  compile but deploy nothing, so the game would find no tiles — or, on a first
  build, no data at all.
- **`--with-no-install`** → plain `make -C ../FAangband`. That build mode reads
  tiles straight out of the source tree the installer just wrote into, and
  `make install` is wrong for it.
- **a prefix needing root** (`/usr/local`) → the installer compiles but stops
  short of deploying, and prints the `sudo make … install` line for you to run.

Re-running the installer after any tileset change is therefore the whole
procedure: it redeploys the rebuilt tiles *and* recompiles the additions it
patches into the game's code. Most are graphics-only:

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

> The installer reads your tree's build mode from `mk/extra.mk` (falling back
> to `config.log`), so it never has to guess. If the tree isn't configured yet
> it says so, prints the two configure recipes, and skips the build — configure
> once, run the installer again, and it takes over from there.

### 7. Run

The installer prints the exact command for your build at the end of its run.
With the Quick Start's configure that is:

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

## Windows notes

`install.ps1` is the Windows twin of `install.sh` — the same seven steps in the
same order — but the surrounding toolchain differs:

- **Get a build environment.** [MSYS2](https://www.msys2.org/) is the path of
  least resistance: from its MinGW64 shell, install the toolchain plus SDL2
  (`pacman -S mingw-w64-x86_64-toolchain mingw-w64-x86_64-SDL2 mingw-w64-x86_64-SDL2_ttf mingw-w64-x86_64-SDL2_image make autoconf automake`),
  then run FAangband's steps 3–4 there (`./autogen.sh`, `./configure --enable-sdl2`).
  `install.ps1` finds `make` on `PATH` and runs the build itself; without one it
  installs everything and prints the build command for you to run in that shell.
- **Python is `py -3` on Windows**, not `python3`. The script probes `py -3`,
  `python3` and `python` in that order and checks Pillow up front, so a missing
  `pip install Pillow` fails in a second rather than after a long build.
- **Run it from the repo root**, and if PowerShell refuses to run a local
  script, either `Unblock-File .\install.ps1` or launch it as
  `powershell -ExecutionPolicy Bypass -File .\install.ps1 ..\FAangband`.
- **Frontend choice matters for two features.** A `--enable-win` build uses
  FAangband's native Windows frontend, which draws this tileset fine, but
  *animated tiles* and the *display defaults* are patches into `main-sdl2.c` —
  they exist only in the SDL2 frontend. Build with `--enable-sdl2` and run
  `faangband.exe -msdl2` for the complete feature set.
- **A Visual Studio build** (`src\win\vs2019`) is not driven from this script.
  Run `install.ps1` to write the tiles and patch the sources, then rebuild in
  the IDE.

## Troubleshooting

**A rebuilt tileset looks unchanged in-game (e.g. `--size 128` looks identical
to `--size 64`).** Almost always you are launching a *different* binary than the
one this tree builds. `install.sh` writes into the source tree's `lib/tiles/`,
and a `--with-no-install` build reads exactly that (`${PWD}/lib/`). But a
separately *installed* binary — e.g. one built with `--prefix=$HOME/.local` and
`make install`, sitting in `~/.local/bin/faangband` — reads its **own** copy
under `~/.local/share/faangband/tiles/` and never sees your rebuild. Fixes:

- If you followed the Quick Start (`--prefix=$HOME/.local`), re-run
  `install.sh ../FAangband` after every tileset change — it ends with
  `make install`, and both the installed `faangband` and the in-place
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
- `tools/selftest.py` — the pre-landing checks: help validators against both an
  unpatched and a patched tree, anchor status, installer-twin drift, shell
  portability, LF-safe writers. Seconds; renders nothing.
- `install.sh` — builds the tileset, copies it into an FAangband source tree,
  registers it in `list.txt` and `Makefile`, applies the C source patches, then
  compiles the game with the command that tree's configuration calls for.
- `install.ps1` — the Windows PowerShell twin of `install.sh`: same seven steps,
  same order, same guarantees. Keep the two in step when either changes.
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
python3 tools/selftest.py <fa-tree>                     # fast pre-landing checks (seconds)
python3 patches/apply_patches.py <fa-tree> --baseline   # upstream drift report
python3 patches/apply_patches.py <fa-tree> --status     # + anchor states, no writes
python3 patches/apply_patches.py <fa-tree> --repin      # advance the pin after a re-author
```

`selftest.py` is the closest thing this repo has to a test suite. It renders nothing and
writes nothing outside a temp directory, and it checks the things that have actually broken:
the help validators against an **unpatched** tree (the fresh-clone state, materialised from
the FAangband tree's git objects — a developer's own tree is always already patched, which is
how that class of bug ships), the same validators against the patched tree, every patch
anchor, that `install.sh` and `install.ps1` still declare the same steps, that `install.sh`
uses no GNU-only construct that would break on macOS, and that `build.py` writes its
generated files with explicit LF endings so a Windows build cannot put a stray CR inside a
makefile. It deliberately does **not** compile FAangband or render the atlas — a full
`make -C <fa-tree>` remains a separate, required step.

## Adding Tiles

1. Generate or draw a tile into `source-tiles/<category>/<name>.png`.
   AI renders use a solid magenta (`#FF00FF`) background; set `"chroma": true`
   on the manifest entry to key it out at build time.
2. Add a manifest entry with an **unused** grid cell (never move existing
   tiles — grid positions are baked into prf coordinates) and the entity
   mapping lines, e.g. `feat:<name>:*`, `monster:<name>`,
   `object:<tval>:<name>`.
3. Run `./install.sh <fa-tree>` (`.\install.ps1 <fa-tree>` on Windows) — it
   rebuilds, reinstalls and recompiles in one pass. Unmapped entities fall back
   to ASCII, so coverage grows incrementally.

Entity names come from FAangband's gamedata files
(`lib/gamedata/terrain.txt`, `monster.txt`, `object.txt`). The atlas grid
maxes at 128x128 (prf coordinates are single bytes from 0x80).

## License

MIT
