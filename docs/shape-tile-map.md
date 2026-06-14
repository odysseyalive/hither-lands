# Shape Tile Mapping

Reference for the shapechange tile system. Maps each player shape from
`lib/gamedata/shape.txt` to its tile atlas coordinates.

The "normal" shape uses the standard player race/class/gender tile.

## Coordinate Reference

| Shape | Row | Col | d_attr | d_char | Source |
|-------|-----|-----|--------|--------|--------|
| fox | 109 | 0 | 0xed | 0x80 | NEW (shapes/fox.png) |
| bear cub | 109 | 1 | 0xed | 0x81 | NEW (shapes/bear-cub.png) |
| eagle | 109 | 2 | 0xed | 0x82 | NEW (shapes/eagle.png) |
| shining dragon | 109 | 3 | 0xed | 0x83 | NEW (shapes/dragon-shining.png) |
| law dragon | 109 | 4 | 0xed | 0x84 | NEW (shapes/dragon-law.png) |
| bear | 68 | 0 | 0xc4 | 0x80 | reuse: grizzly bear |
| great bear | 68 | 0 | 0xc4 | 0x80 | reuse: grizzly bear |
| bat | 65 | 1 | 0xc1 | 0x81 | reuse: brown bat |
| warg | 69 | 12 | 0xc5 | 0x8c | reuse: warg-single |
| vampire | 72 | 14 | 0xc8 | 0x8e | reuse: vampire-single |
| werewolf | 72 | 12 | 0xc8 | 0x8c | reuse: warg-werewolf |
| Pukel-man | 15 | 5 | 0x8f | 0x85 | reuse: golem/pukelman |
| black dragon | 71 | 4 | 0xc7 | 0x84 | reuse: dragon-black-single |
| blue dragon | 71 | 5 | 0xc7 | 0x85 | reuse: dragon-blue-single |
| red dragon | 71 | 6 | 0xc7 | 0x86 | reuse: dragon-red-single |
| white dragon | 71 | 7 | 0xc7 | 0x87 | reuse: dragon-white-single |
| green dragon | 71 | 8 | 0xc7 | 0x88 | reuse: dragon-green-single |
| gold dragon | 71 | 9 | 0xc7 | 0x89 | reuse: dragon-gold-single |
| multi-hued dragon | 71 | 10 | 0xc7 | 0x8a | reuse: dragon-multi-single |
| chaos dragon | 74 | 9 | 0xca | 0x89 | reuse: dragon-chaos |
| balance dragon | 52 | 1 | 0xb4 | 0x81 | reuse: dragon-ancient |
| power dragon | 53 | 1 | 0xb5 | 0x81 | reuse: flying-dragon-boss |

## Code Integration Points

These coordinates get baked into `shape.txt` as `d_attr`/`d_char` fields
(Phase 4 adds the struct fields + parsers). The C code swaps
`monster_x_attr[0]`/`monster_x_char[0]` on shapechange and restores on revert.

Key files to modify (Phase 4):
- `src/player.h` — add `d_attr`/`d_char` to `struct player_shape`
- `src/init.c` — parser for new shape.txt fields
- `src/effect-handler-general.c` — swap tile in SHAPECHANGE handler
- `src/player-util.c` — restore tile in `player_resume_normal_shape()`
- `src/ui-map.c` — shape-aware rendering (optional if swap approach used)
- `src/ui-prefs.c` — add `$GENDER` variable (separate bug fix)
- `lib/gamedata/shape.txt` — add d_attr/d_char lines for each shape
