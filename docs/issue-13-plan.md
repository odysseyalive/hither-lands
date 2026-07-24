# Issue #13 ("Doco feedback") — remediation plan

**Source:** https://github.com/odysseyalive/hither-lands/issues/13
**Status (2026-07-23):** design decisions RESOLVED. **Skill layer COMPLETE** across game-docs,
tileset, hither-lands-dev, tile-index and the route index. **Help content COMPLETE** for D5, D7,
D7-bis and D10 (plus the directive-#9 "spellcraft" cleanup). Remaining: tile ART (D6 doors/roofs,
D9 light UI values), the PDF emitter code, the C patches (D1/D2/D3, `town-roof-*`,
`display-lightmode-*`), and Package A's in-game verification — which is human-gated because the
SDL2 frontend cannot be driven reliably by automation.
**Shareable before/after artifact:** https://claude.ai/code/artifact/f3b8b794-6180-414e-bf6d-258541b6fd90
(source HTML staged in the session scratchpad; to update, redeploy that file in-session, or from another
session pass this URL to the `Artifact` tool as `url`. Flip each card's `data-status` planned→progress→done
as packages land; the meter recomputes itself. Deliberately text-only — no before/after imagery.)
**Nature:** this is a program of adjustments to the Hither Lands **skills** (`.claude/skills/*`,
git-ignored) plus the project code they drive (`patches/`, `manifest.json`, `tools/`,
`help-source/`, `source-tiles/`). It is ~100% hither-lands project work; skill-builder is only
the editing vehicle, not a framework change.

This file is the never-regress through-line for the work: it carries forward *why* each decision
was made so the next session builds on it rather than re-deriving it. Keep it updated as packages
land.

## Two cross-cutting root causes

1. **`game-docs sync` verifies topic *presence*, never *correctness* against patch behavior.**
   This is why D4 (stale gender help) slipped and why D5/D7/D10 could drift silently. Fixing the
   sync check matters as much as the individual doc fixes.
2. **No skill has a repeatable help-viewer / cross-session-persistence verification step.**
   D1/D2/D3 shipped *despite* the existing ledger pattern `PAT-2026-07-22-display-patches-are-global`
   because `fa-playtest` scenarios only cover the map — never the help browser or pref persistence.

## Discoveries → resolved decisions

| # | Discovery (reporter's words, condensed) | Verdict / decision |
|---|---|---|
| D1 | "A" plate vanishes after leaving `index.txt` and returning | CONFIRMED: `help_tile_load` called once outside the display loop; `show_file` recursion overwrites the single global plate buffer. Fix: reload plates on redraw / after recursive return. |
| D2 | "O" plate in `races.txt` renders wider than tall | PARTIAL: `help-tile-scale` pins 1×1 into a non-square text cell; may also be the D3 leak. Fix: aspect-corrected plate span via `help-tiles.idx`; resolve after D3. |
| D3 | Tile-size menu resets to 7×3 instead of user's 4×4 between sessions | CONFIRMED defect: `display-default-tile-scale` reads live `tile_width==1` as "no user choice," but our own `help-tile-scale`/`GRAPHICS_NONE` zero it — mutual undermining `db6eb4d` didn't cover. Fix: gate on config-file *absence*; stop `help-tile-scale` mutating the persisted global; NEVER-REGRESS clause: display globals are persisted user state, never scratch. |
| D4 | `birth.txt` says gender set at install; build never asks | NOT a live bug — reporter quotes pre-`f1d5a36` text; source already says birth-time, pgender installed. Real drift is in game-docs' own grounding (`reference.md` still says "install-time", omits `pgender-*` row) + the sync presence-only gap. |
| D5 | `stores.txt` cites numbers but tiles hide them | Fixed on two fronts: D6 numbered doors make numbers visible on the map again; plus a game-docs plate-ordinal authoring convention + sync lint + `stores.txt` rewrite. |
| D6 | Store tiles too similar; wants clearer stores | REDESIGN (owner): stores → single **numbered+emblem door tiles** (adam-bolt model); town buildings get **roofs**. FA has no roof feat and `FEAT_PERM` is shared with the dungeon, so town-only roofs need a C patch. Decision: **doors + town-roofs together**, numeral+emblem doors. |
| D7 | `magic.txt` gap: equipment effects on casting? | Answerable: heavy armor cuts max SP (`player-calcs.c:1604-1672`); gloves are free (no FA glove-casting penalty). Fix: `build magic` paragraph + open-reader-questions register. |
| D8 | Want auto-generated PDF help with images | Decision: new game-docs `pdf`/`export` mode — **full-featured**, **one standard-keyset PDF**, **committed under `docs/`**. Tier-1 auto (build.py) + Tier-2 on-demand screenshots. Never embed `library/*.pdf` (copyright). Resolve `install.sh:79` help-carry drift. |
| D9 | Wants a light-mode choice | Decision (owner-refined): **runtime keybinding toggle**, **Phase 1 + Phase 2**, palettes **pinned**, **no new art**. Phase 1 = 32-color table flip (SDL2 live-refresh seam). Phase 2 = second atlas re-snapped from the same source art via a locked luminance transform of the dark palette. D3-safe persistence via a dedicated `light-mode:1` line (no overloaded sentinel). |
| D10 | Lone spoiler pair looks odd | Decision: **consolidated spoiler appendix** ("Appendix VI: Of Matters Best Discovered") + topic-warrant policy; move `shapes-spoiler` there. |

## Work packages by skill

### A · `fa-playtest` — verification capability (do FIRST; evidence before change)
- [ ] New `help-view` diagnostic mode: `?` → index→submenu→back; screenshot plates; log `tile_width/height` at plate draw. (D1/D2/D3)
- [ ] Persistence-regression check: diff `-duser` `sdl2init.txt` before/after a launch; assert unchanged when the user changed nothing. (D3, D9)
- [ ] Confirm D4 is only the reporter's stale tree: rebuild + verify the Male/Female birth stage renders.
- [ ] (Provides Tier-2 screenshots for D8.)

### B · `awareness-ledger` — capture the why (before edits) — **DONE 2026-07-23**
- [x] `INC-2026-07-23-tile-scale-sentinel-poisoned` — `tile_width==1` is not a reliable "no choice" sentinel; `help-tile-scale` poisons it. Status **active**: fix planned, NOT applied. (D3)
- [x] `DEC-2026-07-23-stores-as-doors-town-roofs` — no roof feat; `FEAT_PERM` rectangles + numbered door grid; stores→doors, town-only roofs need a C patch. (D6)
- [x] `DEC-2026-07-23-pinned-light-dark-toggle` — runtime toggle, pinned palettes, no new art, D3-safe `light-mode:` persistence. (D9)
- [x] `PAT-2026-07-23-docs-sync-presence-not-correctness` — sync verified presence, never correctness. (D4)
- [x] `ledger/index.md` regenerated — first incident record; Decisions 4→6, Patterns 5→6.

### C · `game-docs` — docs content + sync upgrade + pdf mode + spoiler restructure
- [x] **DONE 2026-07-23** Fix `reference.md` coverage map: `pgender-*` row added; the wrong
      "install-time gender note" removed from the `prace-*` row. Also added the four groups that
      had NO row at all (`pgender-*`, `help-tile-*`, `help-key-*`, `display-*`) — 10 logical groups
      across 88 patches now all covered — and a new **behaviour-fact column** that records what each
      group makes true for the player, as the lint target. (D4)
- [x] **DONE 2026-07-23** Strengthen `sync`: added step **3a group-presence** (every `patches.json`
      group must have a coverage-map row) and step **5a behaviour-contradiction** (grep covering
      topics for prose asserting the opposite of the behaviour fact; "a topic that merely exists is
      not passing"). Both in `SKILL.md` § Workflow: sync and `reference.md` § Sync checklist 2a/2b.
      Directive sidecar re-verified: all 9 hashes unchanged. (D4 class — closes the root cause in
      `PAT-2026-07-23-docs-sync-presence-not-correctness`)
- [x] **SKILL DONE 2026-07-23** D5 convention + lint: `reference.md` § Tile plates gained the
      hidden-navigation-token rule (refer by NAME when a plate paints over the digit the prose
      navigates by), with a scoped corollary that number-references become legal again once the
      D6 door tiles make the numeral visible. Sync gained lint **2c**.
- [x] **CONTENT DONE 2026-07-23** `stores.txt` rewritten: "The first door and the fifth… The
      seventh" became "The General Store and the Alchemist… The Black Market" (doors 1/5/7 verified
      against `terrain.txt` `graphics:N`), reflowed inside the 79-column limit.
- [x] **SKILL DONE 2026-07-23** D7 register: `reference.md` § Open reader questions created and
      seeded with the answer researched from source (heavy armour cuts max SP via `calc_mana`,
      `player-calcs.c:1604-1672`; **gloves do NOT hinder casting in FA** — no `cumber_glove`
      mechanic exists), plus a second OPEN row flagging that the fail-rate claim is UNVERIFIED and
      must be re-checked against `player-spell.c` before any positive statement. Surfaced by
      `status`, linted by sync **2d**.
- [x] **CONTENT DONE 2026-07-23** `magic.txt` § Casting gained the armour paragraph (max SP falls
      one per ten units of excess weight; allowance widest for Blackguard, narrowest for Mage and
      Necromancer; Armor Proficiency widens it) and the gloves paragraph stating plainly that no
      glove here dulls a caster. Register row moved to **CLOSED**.
- [x] **CONTENT DONE 2026-07-23** D7-bis voice bridge landed in `magic.txt` § Casting: "Song and
      spell are one thing here, told two ways," naming the on-screen terms (cast, spell points)
      so a reader meeting *song* in public write-ups can map it to the UI.
- [ ] D7-bis (voice bridge): in `magic.txt`, state plainly what the song vernacular refers to — that what the
      lore calls *song* is what the game's own screens call spellcasting and spell points — so a reader meeting
      "song" in our public write-ups is never left guessing how it maps to the UI. Extends the 2026-07-23
      song-vernacular directive (`game-docs` directive #8, public-facing scope) into the help as a CLARIFICATION
      only: FAangband's on-screen terminology is still never rewritten, and the standing "do not confuse people"
      directive governs. Land this in the same `build magic` pass as D7.
- [x] **SKILL DONE 2026-07-23** D10: `guide` restructured to the consolidated **Appendix VI "Of
      Matters Best Discovered"** (menu letter `v`, one gate) replacing per-topic `-spoiler` twins;
      the chapter table and `SKILL.md` steps 4/4a updated, and a **topic-warrant** rule added so
      "does skin-changing deserve its own entry?" is answerable by rule (verdict: yes, it is a
      patch feature).
- [x] **CONTENT DONE 2026-07-23** The move itself: `shapes-spoiler.txt` relocated from letter (p)
      in "Counsel for the Road" to **(v) Appendix VI: Of Matters Best Discovered** in BOTH
      `index.txt` and `r_index.txt` (the pair lands together per the Keyset Coverage Gate); letter
      (p) freed; `shapes.txt`'s closing pointer re-aimed at the appendix. With one spoiler file the
      appendix IS that file; promote it to a hub sub-index when a second spoiler lands.
- [x] **CONTENT DONE 2026-07-23** Directive #9 applied to existing prose: the magic chapter title
      "Of Song and **Spellcraft**" (the D&D compound the user flagged) became **"Of Song and
      Spell"** in both index files and in `magic.txt` itself, underline re-measured 21→16. The two
      remaining in-prose uses (`races.txt`, `classes.txt`) became **sorcery**, which is
      Tolkien-attested. Zero occurrences of "spellcraft" remain in `help-source/`.
- [x] **SKILL DONE 2026-07-23** D8: new **`pdf` mode** authored (Tier 1 deterministic text+tile-art
      from `build.py`; Tier 2 on-demand screenshots; one standard-keyset PDF committed to `docs/`;
      delegations to fa-playtest/tileset/lore/text-eval; hard copyright floor forbidding any
      `library/*.pdf` content). Registered in frontmatter + Usage.
- [x] **CODE DONE + VISUALLY VERIFIED 2026-07-23** D8 emitter: `tools/build_pdf.py` written and
      wired into `build.py` main (Tier-1 auto, best-effort/skip-if-no-reportlab). Produces
      `docs/hither-lands-help.pdf` — **60 pages, 1.1 MB**, narrative reading order from the index
      menu, standard keyset (roguelike footer pointer), illuminated-capital drop caps AND single-cell
      tile icons both embedded from the atlas. Rendered pages to PNG and eyeballed: title "A", the
      "O" of stores, and the six shop icons all render correctly; copyright floor honoured (atlas art
      only). Reuses `build.py`'s marker parse / keyset loader / atlas contract, so it can't drift.
- [ ] Coordinate with E/D2: `help-tiles.idx` carries per-plate width/height span.

### D · `tileset` — art-direction conventions + art
- [x] **SKILL DONE 2026-07-23** D6 town convention: prompt-templates town scaffold rewritten to
      single-cell **doorways with baked numeral + facade emblem** (plus tileable roof/wall recipe),
      adam-bolt named as structural reference; art-direction gained **§8 Related-set
      distinctiveness**; validation gained **HARD check 7** and — critically — a **carve-out on
      check 5**, which forbade embedded text and would otherwise have rejected every numbered door.
- [x] **SKILL DONE 2026-07-23** D9 guidance: art-direction **§9 Light-theme palette** — no sprite is
      redrawn for light mode (the light atlas is a locked luminance transform of the same art), dark
      selective outlines are KEPT because they read cleanly on a light ground, and the real task is
      the 32-colour UI theme, not sprites.
- [x] **CODE DONE + VERIFIED 2026-07-23** D9 pinned light atlas: `tools/build_light_atlas.py`
      computes the light palette as a **locked luminance transform** of `palette.json`
      (`L' = 1 - L`, hue/sat kept), writes `palettes/{dark,light}.json`, and remaps the built dark
      atlas 1:1 (`dark[i] → light[i]`) into `dist/fa-ai-light/64x64.png`. Verified: 0 off-palette
      pixels (exact remap), mean luminance **76.8 → 188.1**, warm ground → warm parchment with amber
      accents preserved and dark outlines intact (eyeballed a shop-tile crop — coherent, not muddy).
      Wired into `build.py` (best-effort). Zero source art redrawn, per the pinned design.
- [x] **ART DONE + 64px-VERIFIED 2026-07-23** D6 store doors: all **9 numeral+emblem door tiles**
      generated via `/tileset` (nanobanana pro) and landed in place over the look-alike buildings
      (`source-tiles/town/{shop-general,shop-armoury,shop-weapon,shop-bookseller,shop-alchemy,shop-magic,shop-black-market,home,merchant}.png`;
      buildings backed up to scratchpad + git history). Each is a doorway (not a building) with a
      facade-scale emblem (barrel/shield/crossed-swords/book/potion/orb+star/barred-slot/hearth/awning)
      and a **bold numeral 1–9 on a pale plaque** — the plaque recipe cleared the predicted
      numeral-at-64px legibility risk. Montaged all 9 at 64px: mutually distinguishable by silhouette
      + emblem + numeral (D6 solved) and every number legible (D5 reinforced). All corners
      magenta-keyable. In-place swap ⇒ **no manifest change needed** (same filenames/cells/`maps`).
      **VERIFIED END-TO-END 2026-07-23:** full `build.py` rebuilt the atlas (1392 tiles, palette
      snapped, exit 0); cropped the snapped shop row straight from `dist/fa-ai/64x64.png` — all 9
      doors survive the 21-colour snap AND the 64px cell size with numerals still legible and shops
      still mutually distinct. The same build regenerated the PDF (now shows the doors) and the light
      atlas, exercising all new `build.py` wiring in one clean pass.
- [ ] Roof tile(s) + town wall tile (the `town-roof-*` half of D6 — still to art + patch).
- [ ] Define the actual 32-colour light UI values (text legibility pass) — pairs with the C patch below.

### E · `hither-lands-dev` — C patches, manifest remap, build.py
- [x] **AUTHORED + COMPILES 2026-07-23** D1: new `help-tile-reload` patch group in `patches.json`
      — reloads the current file's plates at the top of the help display loop, so a return from a
      recursive `show_file` restores the parent's plates. Applied cleanly (`apply_patches`: 10
      applied, 79 already present, no missing anchors) and **`make` exits 0, no warnings**. Confirmed
      in-source at `ui-help.c:394`. *Still needs Package-A in-game confirmation before commit.*
- [x] **AUTHORED + COMPILES 2026-07-23** D3: `display-default-tile-scale` payload rewritten to gate
      the 7×3 default on **config-file absence** (`!file_exists(g_app.config_file)`, mirroring the
      proven `display-default-tileset` pattern) instead of the poisonable `tile_width==1` sentinel.
      Reverted `main-sdl2.c` to the pinned baseline and reapplied all patches with the new payload;
      the old sentinel is gone (`grep` = 0), `make` exits 0, no warnings. Note: `help-tile-scale`
      needs no change — help is modal, so its restore always runs; the real trigger was the
      graphics disable/re-enable cycle, which the config-absence gate fully covers.
      *Still needs Package-A in-game confirmation before commit.* (`sentinel` unchanged, per invariant.)
- [ ] D2: aspect-corrected plate span (with `help-tiles.idx`). Resolve after D3.
- [x] **AUTHORED + COMPILES 2026-07-23** D9 Phase-1 runtime toggle: new `display-lightmode-*` group
      (fwd / fn / key) in `patches.json`. **F9** flips the 32-entry `angband_color_table` between the
      loaded dark theme and a light theme derived by a hue-preserving luminance inversion, then
      `init_colors` + `Term_redraw`. Intercepted on the raw SDL scancode before the Angband key map,
      so it collides with no keyset. **Defaults OFF, applied only by the explicit toggle, never
      auto-forced** (never-regress; the hook is isolated in `handle_key`, not the shared grid path).
      Applied clean (3 applied, 89 present), **`main-sdl2.c` compiles, full link exit 0, no warnings**,
      96/96 anchors prove clean. **Transform VERIFIED** against FA's default 32-colour table: the
      first (multiplicative) version left the pure-black void black and text black (contrast 0,
      invisible) — caught statically and replaced with an additive luminance shift (void→white,
      text→black, contrast 255). **Cross-session PERSISTENCE added + compiles:** a dedicated
      `light-mode:` line in `sdl2init.txt` (dump/read/apply, latched on startup), D3-safe by
      construction. Only Package-A in-game confirm and the optional Phase-2 atlas-swap-on-toggle
      remain. `palettes/{dark,light}.json` emitted by build_light_atlas.py.
- [ ] D6 Part A: remap 9 store feats → door art in place on (3,0)–(3,8); Merchant its own tile.
- [ ] D6 Part B: `town-roof-*` C patch (town-context `FEAT_PERM`→roof) + roof/wall tiles at new appended cells.
- [x] **SKILL DONE 2026-07-23** Discipline encoded in workflow (f): shared-display-path guard, and a
      MANDATORY handoff — a patch group that changes player-facing behaviour updates the `/game-docs`
      coverage map **and its behaviour fact** and runs `sync` in the SAME change. Plus **invariant 10**
      (display globals are persisted user state; never gate a default on a live global you also write;
      a guard is not a fix) and **invariant 4** reworded to permit registered palette variants.

### F · `tile-index` + `route`
- [x] **SKILL DONE 2026-07-23** `tile-index` workflow `index` gained step 4, a **reporting-only**
      confusable-set check (never blocking, per its own invariant 1) that judges look-alikes at 64px
      after the palette snap — the two channels that erase the cues you would judge on source art.
- [x] **DONE 2026-07-23** `route index` refreshed (scoped): `/game-docs` row now advertises the `pdf`
      mode and the gated-appendix guide; per-skill detail refreshed for `/tileset`,
      `/hither-lands-dev`, `/tile-index`. Verified: index modes match live frontmatter byte-for-byte,
      no stale "spoiler-pair" text remains, all 10 catalog rows intact, 9 directive hashes unchanged.
- [ ] Regenerate tile coverage after the D6 remap; assert no store feat silently dropped to ASCII.

## Build verification (2026-07-23)

`python3 tools/build.py` was run against the content edits and **caught a real defect**: the
rewritten `stores.txt:56` rendered **77 columns**, over the limit. Reflowed and re-verified via a
help-only re-emit (`build.build_help(manifest)`), which now reports **24 topics, 2022 tile plates,
49 key tokens, no errors**. All edits confirmed present in the EMITTED `dist/help/` files, the
illuminated-capital underline re-aligned (21→16), letter (p) freed in both index files, and zero
occurrences of "spellcraft" anywhere in emitted help.

**Lesson recorded into `game-docs/reference.md`:** there are TWO limits and they are easy to
conflate — rendered **line width ≤ 76** (checked after plates collapse and key tokens expand, in
BOTH keysets) versus **plate column ≤ 79**. Authoring prose to 79 overflows by one or two columns
every time; that is exactly how the defect above was introduced.

## Execution order
1. **A** — fa-playtest verification → reproduce D1/D2/D3, confirm D4 stale-tree.
2. **B** — ledger records.
3. **C** — game-docs grounding + sync upgrade (D4).
4. **E** — C-patches D1/D3 → verify (A) → D2.
5. **D** — tileset conventions + art (D6 doors/roofs, D9 light theme).
6. **E** — D6 remap + `town-roof-*` + `display-lightmode-*` + build.py → rebuild/install → verify each (A).
7. **C** — D5/D7/D10 content + D8 pdf mode.
8. **F** — tile-index regen + route index refresh + final ledger updates.

## Standing gates (never-regress)
- Every C-patch group: unique single-occurrence anchor, unique sentinel, full `make`, `--repin` in the same commit; two-pass classify-before-write.
- Cells/maps are append-only: never move a store/roof cell; retire building art by swapping `source` in place, add roof/wall tiles at unused cells only.
- Any display-* patch touching `tile_width/height/use_graphics/graphics.id` or the color table treats them as persisted user state, never scratch, and must answer PAT-2026-07-22's two questions.
- No `library/*.pdf` content embedded in the exported PDF (copyright).
