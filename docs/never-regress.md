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

Hither Lands is not an application. It is ~1,400 tiles plus 110 anchor-based patches spliced
into 28 files of somebody else's actively-developed roguelike (all C source but two, which
patch `lib/gamedata/`). Three properties make silent regression the default failure mode
rather than an unusual one:

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
`install.sh` has already patched, all 110 records report `ALREADY`, which proves the tree was
patched and proves *nothing* about whether the anchors still locate. Twenty-nine `replace`
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

### The build may not read a tree the patches have not reached yet

`install.sh` builds at step 2 and applies patches at step 6. So any build-time check that
reads the live FAangband tree is reading a tree **our own patches have not touched yet**. If a
patch renames a string that check validates against, the build validates against a world that
does not exist until four steps later, and it fails on every clean tree.

This bit on 2026-07-25. One commit rewrote `help-source/` to reference commands by their new
descriptions (`{key:Sing a song}`) *and* added the `song-cmd-*` patches that create those
descriptions. `build.py` validated the tokens against the live `ui-game.c`, which still said
"Cast a spell", and `install.sh` aborted in its build step. It had passed review only because the
author's tree was still patched from a previous install; the first `git reset --hard` exposed
it, and a bare `python3 tools/build.py` failed the same way.

**Rule: when a patch changes a string that anything under `tools/` reads, greps, or validates,
that tool must derive the string from `patches.json` — the same single source of truth that
performs the rename — never from the live tree alone.** The overlay ships in the same change
as the patch. `load_keysets()` in `tools/build.py` is the worked example: it reads the live
source first (so genuine upstream drift is still caught, which is the whole point of the
check), then removes what a `where: "replace"` record consumes and adds what its payload
introduces. That is correct in both tree states, because on an already-patched tree the added
rows are present anyway and the anchors are already gone.

Note what this failure is *not*. Every anchor matched, `--status` said `READY`, `--baseline`
said clean. The patch machinery was working perfectly, and every drift instrument reported
healthy while the build could not run. Verify against an **unpatched** tree — a patched tree
passes whether or not the bug exists, which is precisely why it shipped.

**That verification is now mechanical.** `tools/selftest.py` materialises the files these
validators read straight out of the FAangband tree's git object store, at the pinned baseline
commit, into a temp directory — a fresh clone's exact state, without touching anyone's working
tree — and runs the help pass against it. It runs the same pass against the live *patched*
tree too, because a check that is only correct in one state is the bug it is meant to catch.
Run against `bda9d9a^` it reports the four `'Sing a song'` lines and passes the patched tree,
which is this incident reproduced on demand.

The same day's second lesson: these validators used to run **last** in `build.py`, after the
~15-minute atlas render, so the cheapest check in the file reported its verdict at the most
expensive possible moment. They now run first. A check that is cheap to run is worth nothing
if it is scheduled behind an expensive one that does not depend on it.

### A patch group's blast radius is not its name

Before landing a patch that edits a shared string, find every consumer; the group's name will
understate its reach. `song-realm-arcane` reads as "the arcane realm only", and its
`spell-noun` change is indeed per-realm — but the selection prompt beside it is built in
`ui-spell.c` as `"%s which %s?"` from a **hardcoded** verb plus that per-realm noun. Changing
the verb at the call site changed it for *every* realm at once: a Priest now reads "Sing which
prayer?", a Druid "Sing which verse?". That was intended here, and it is written into the
`/game-docs` coverage map so a later topic cannot quietly contradict it. It would have been a
regression had nobody looked.

### Two installers, one behaviour

There are two entry points into the same seven steps — `install.sh` (Linux/macOS) and
`install.ps1` (Windows) — and only one of them can be run here. Nothing tests the other; a
change to one silently makes the platforms disagree, and the person who finds out is a user
on the platform the author does not have.

**Rule: a change to `install.sh` lands with the matching change to `install.ps1`, in the same
commit.** Keep the step numbers, the step names and the printed text aligned so the two can be
read side by side — that diffability is the only test the pair has.

Two portability traps are worth naming because both fail silently rather than loudly:

- **GNU-only shell constructs.** `sed -i` (BSD requires a suffix argument), template-less
  `mktemp` (BSD requires a template), and `\b` in a `grep` pattern (a GNU extension) are all
  fine on Linux and broken on macOS. The last is the dangerous one: on macOS the `\b` guard
  simply never matches, so the "already registered?" check answers *no* every time and appends
  a duplicate `SUBDIRS` entry on every run. Prefer POSIX spellings or shell-level `case`
  matching.
- **Text written on Windows.** Python's text mode translates `\n` to `\r\n` there, so anything
  `tools/` generates for `make` or for the C readers must be written with an explicit LF
  (`write_lf()` in `build.py`) — a stray CR lands *inside* a filename in the generated
  `lib/tiles/Makefile` and inside a frame count in `anim.txt`, and both are read as data
  rather than rejected as errors. Files edited *in place* in the FA tree are the opposite case
  and keep the platform's own convention.

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

0. `python3 tools/selftest.py <FA_DIR>` — seconds, renders nothing. It runs the help
   validators against an **unpatched** fixture materialised from the FAangband tree's git
   objects at the pinned commit (items 6 and 3 of this list, mechanised), plus the anchor
   status, the installer-twin comparison, and the two lint rules below. It does **not**
   compile anything, so it replaces no item here — it only means you stop *finding out* by
   hand.
1. `--baseline` clean, or its drift report read and acted on.
2. `--status` all `READY`/`ALREADY`.
3. Full `make -C <FA_DIR>` — anchors locating says nothing about whether the tree builds.
4. No previously-mapped entity lost its tile; no existing cell moved.
5. The pin advanced (`--repin`) if anchors were re-authored, in the same commit.
6. If a patch renamed a string any `tools/` check reads, that check derives it from
   `patches.json`, and the build was proven against an **unpatched** tree.
7. The *why* recorded wherever the diff cannot show it.
8. If `install.sh` changed, `install.ps1` changed with it — same steps, same order, same text.
