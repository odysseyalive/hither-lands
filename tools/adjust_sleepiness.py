#!/usr/bin/env python3
"""Adjust monster sleepiness values for the Hither Lands ecosystem.

Animals, townsfolk and player-race creatures get reduced sleepiness; EVIL,
UNDEAD and DEMON creatures keep their original values, since sleep is the
primary balancing mechanic for them.

Note that this is deliberate even though nearly all animals are now hostile
(the eco-neutral-spawn patch only spares depth-0 critters and the skittish
crow / giant white mouse): a wide-awake fauna layer is the intended feel.
Sleepiness 0 is also what activates FAangband's day/night rule -- the
is_night() +20-turn branch at mon-make.c:1881 is the *else* of
`if (race->sleep)`, so a non-zero value opts a race out of it entirely.
That branch only fires outdoors (is_night() is `!is_daytime() && outside()`),
so fauna are always awake in caves.

Usage:
    python3 tools/adjust_sleepiness.py <FA_DIR>
    python3 tools/adjust_sleepiness.py <FA_DIR> --dry-run
"""
import os
import sys

SENTINEL = "# HITHER-LANDS:eco-sleepiness applied"


def load_base_flags(fa_dir):
    path = os.path.join(fa_dir, "lib", "gamedata", "monster_base.txt")
    bases = {}
    current = None
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("name:"):
                current = line[5:]
                bases[current] = set()
            elif line.startswith("flags:") and current:
                bases[current].update(
                    f.strip() for f in line[6:].split("|")
                )
    return bases


def classify(name, base_name, mon_flags, base_flags):
    all_flags = mon_flags | base_flags
    if "UNDEAD" in all_flags or "DEMON" in all_flags:
        return "hostile"
    if "EVIL" in all_flags and "ANIMAL" not in all_flags:
        return "hostile"
    if "EVIL" in all_flags and "ANIMAL" in all_flags:
        return "evil_animal"
    if base_name == "townsfolk":
        return "townsfolk"
    if "PLAYER" in all_flags:
        return "player_race"
    if "ANIMAL" in all_flags and "TERRITORIAL" in all_flags:
        return "fauna_territorial"
    if "ANIMAL" in all_flags:
        return "fauna"
    if "NEVER_MOVE" in all_flags:
        return "sessile"
    return "other"


def new_sleepiness(category, old_val):
    if category in ("fauna", "fauna_territorial"):
        return 0
    if category in ("townsfolk", "player_race"):
        return min(old_val, 5)
    if category == "evil_animal":
        return min(old_val, max(5, old_val // 2))
    # sessile, hostile and other keep their upstream values -- sleep is the
    # balancing mechanic for everything that isn't fauna.
    return old_val


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    fa_dir = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    monster_path = os.path.join(fa_dir, "lib", "gamedata", "monster.txt")
    if not os.path.exists(monster_path):
        print(f"Error: {monster_path} not found")
        sys.exit(1)

    with open(monster_path) as f:
        text = f.read()

    if SENTINEL in text:
        print("Sleepiness already adjusted (sentinel found). Skipping.")
        sys.exit(0)

    bases = load_base_flags(fa_dir)
    lines = text.split("\n")
    changes = []

    # Pass 1: collect all per-monster data (flags appear AFTER sleepiness in the file)
    monsters = []
    current = None
    for i, line in enumerate(lines):
        if line.startswith("name:"):
            current = {"name": line[5:], "base": "", "flags": set(), "sleep_line": None, "sleep_val": None}
            monsters.append(current)
        elif current and line.startswith("base:"):
            current["base"] = line[5:]
        elif current and line.startswith("flags:"):
            current["flags"].update(f.strip() for f in line[6:].split("|"))
        elif current and line.startswith("sleepiness:"):
            current["sleep_line"] = i
            current["sleep_val"] = int(line[11:])

    # Pass 2: classify with complete flags and rewrite sleepiness lines
    rewrites = {}
    for mon in monsters:
        if mon["sleep_line"] is None:
            continue
        base_flags = bases.get(mon["base"], set())
        cat = classify(mon["name"], mon["base"], mon["flags"], base_flags)
        new_val = new_sleepiness(cat, mon["sleep_val"])
        if new_val != mon["sleep_val"]:
            rewrites[mon["sleep_line"]] = new_val
            changes.append(
                f"  {mon['name']:45s}  {cat:20s}  {mon['sleep_val']:>3d} -> {new_val:>3d}"
            )

    out = []
    for i, line in enumerate(lines):
        if i in rewrites:
            out.append(f"sleepiness:{rewrites[i]}")
        else:
            out.append(line)

    out.append(SENTINEL)

    if changes:
        print(f"{'DRY RUN: ' if dry_run else ''}Adjusting {len(changes)} monsters:")
        for c in changes:
            print(c)
    else:
        print("No changes needed.")
        sys.exit(0)

    if not dry_run:
        with open(monster_path, "w") as f:
            f.write("\n".join(out))
        print(f"\nWritten to {monster_path}")
    else:
        print("\nDry run -- no changes written.")


if __name__ == "__main__":
    main()
