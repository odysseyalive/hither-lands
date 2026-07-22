# The prime directive: never regress

*Committed to the repo on purpose.* `CLAUDE.md` and `.claude/` are git-ignored here, so this
file is the copy that survives a fresh clone. It is the contract every change to Hither Lands
is held to.

## The directive

Upstream FAangband does not know this project exists and will not accommodate it. Every
feature here is held in place by information *we* recorded — nothing external protects it.
So, above convenience and above speed:

> **Every change must carry forward enough information that the next change builds on it
> rather than breaks it. No change to our code may break previously-completed work, whatever
> we change and whatever FAangband changes upstream.**

## Why this project needs it stated

Hither Lands is not an application. It is ~1,400 tiles plus 83 anchor-based C patches spliced
into 22 files of somebody else's actively-developed roguelike. Three properties make silent
regression the default failure mode rather than an unusual one:

1. **Upstream moves without warning.** An anchor that located uniquely last month may be gone,
   duplicated, or — worst — still matching while the code around it changed meaning.
2. **Most failures do not raise an error.** A `maps` line pointing at a renamed entity does
   not fail the build; the entity quietly falls back to ASCII. A moved cell does not fail the
   build; every prf line baked against the old coordinate quietly points at the wrong art.
3. **Reasoning is not recoverable from the diff.** A patch payload shows *what* was done. Why
   that anchor, why that ordering, what upstream behavior it depends on — none of it is in the
   file, and none of it can be re-derived a year later.

## What the directive obliges

### The baseline pin

`patches/patches.json` carries an `upstream` block pinning the exact FAangband commit every
anchor was **proven** against, plus a `history` of every prior baseline (newest last).

```sh
python3 patches/apply_patches.py <FA_DIR> --baseline   # drift report only
python3 patches/apply_patches.py <FA_DIR> --status     # + anchor states, no writes
python3 patches/apply_patches.py <FA_DIR> --repin      # advance the pin
```

Every run — including the one `install.sh` performs — prints the baseline state *before*
classifying anchors, so an upstream that moved is announced ahead of the attempt rather than
discovered as a mid-install abort. On drift, the report lists which **anchored** files changed
in the range and maps them back to the patch groups at risk.

**A pin may never advance past a broken anchor** — a pin that outruns its proof is worse
than no pin at all. So `--repin` refuses unless the new baseline is genuinely provable:

- the tree carries git metadata;
- it is not behind or diverged from the current pin (advancing there would move the
  baseline onto ground the anchors were never checked against);
- the *old* pin is still present in the tree, so the move is auditable;
- **every anchor locates uniquely in HEAD's own blobs** (`git show HEAD:<file>`), verified
  with the same cumulative splice pass-1 uses, so chained anchors still resolve.

That last check is the load-bearing one, and it is why `--repin` does not simply reuse the
normal anchor classification. Classification short-circuits on the sentinel: on a tree
`install.sh` has already patched, all 83 records report `ALREADY`, which proves the tree was
patched and proves *nothing* about whether the anchors still locate. Seventeen `replace`
records are worse still — applying one destroys its own anchor, so it can never be re-found
in a patched file at all. Reading the pristine upstream blob sidesteps both.

`--repin` writes only under `upstream`, never `patches` (asserted before the write, along
with the file's byte-stable round-trip so the diff stays reviewable), and it does not apply
patches. The pin advance belongs in the **same commit** as the re-authored anchors — a commit
that repairs anchors without moving the pin leaves the repo claiming a baseline it no longer
matches.

### A still-matching anchor is not proof of correctness

Anchors detect code that *moved or duplicated*. They cannot detect an upstream change
**adjacent** to an anchor, where surrounding semantics shift while the anchor text still occurs
exactly once. That is the only silent-regression path in the patch design, and the drift report
is the only thing that surfaces it. When the report names a file, **every** patch in that file
is suspect — not only the ones that broke.

`where: "replace"` is the exception, and it is safe: its anchor *is* the replaced region
(`text[:idx] + payload + text[idx+len(anchor):]`), so an upstream edit inside it breaks the
match and forces a `MISSING` abort. Replace patches cannot silently swallow an upstream fix.

### Cells and maps are append-only

Atlas cell (row, col) → `attr = 0x80+row`, `char = 0x80+col`, baked into every prf line and
into `docs/shape-tile-map.md`. Moving an existing tile's coordinates regresses every consumer
at once, and nothing errors. Removing or retargeting a `maps` line drops that entity to ASCII,
and nothing errors. Add at unused cells; verify entity names against the target tree's
`lib/gamedata/*.txt` before landing.

### The reasoning goes in the ledger

Non-obvious decisions, root causes, and upstream interactions get an awareness-ledger record
(`.claude/skills/awareness-ledger/ledger/`). A decision that only a live conversation explains
has already regressed.

## Before landing any change

1. `--baseline` clean, or its drift report read and acted on.
2. `--status` all `READY`/`ALREADY`.
3. Full `make -C <FA_DIR>` — anchors locating says nothing about whether the tree builds.
4. No previously-mapped entity lost its tile; no existing cell moved.
5. The pin advanced (`--repin`) if anchors were re-authored, in the same commit.
6. The *why* recorded wherever the diff cannot show it.
