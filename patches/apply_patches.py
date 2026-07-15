#!/usr/bin/env python3
"""Anchor-based, idempotent C-source patcher for the FAangband tree.

Authored/maintained by the /fa-codepatch skill. Patches are located in the
source by a literal content anchor (re-derived every run, never a stored line
number) and made idempotent by a sentinel marker comment that the applier
checks for before inserting. Mirrors the grep-guard discipline in install.sh.

Usage:
    python3 apply_patches.py <FA_DIR> [--status]

Exit codes:
    0  every patch applied or already present (or, with --status, scan done)
    1  a patch's anchor is MISSING or AMBIGUOUS -- a human must re-author it
        (no edits are made when any patch fails to locate cleanly)

Patch record fields (patches.json):
    id        unique short id
    file      path relative to FA_DIR
    anchor    literal substring that must occur EXACTLY ONCE in the live file
    where     "after" | "before" | "replace"
    sentinel  marker string; if already present in the file, the patch is skipped
    payload   text to insert (after/before the anchor) or to replace the anchor with
    note      human description
"""
import json
import os
import sys

STATUS_ONLY = "--status" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
FA_DIR = args[0] if args else os.path.expanduser("~/lab/FAangband")
HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "patches.json")) as fh:
    DATA = json.load(fh)

RED, GRN, YEL, DIM, RST = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


def classify(rec, text):
    """Return (state, position) without mutating. position is a char index or None."""
    if rec["sentinel"] in text:
        return ("ALREADY", None)
    anchor = rec["anchor"]
    count = text.count(anchor)
    if count == 0:
        return ("MISSING", None)
    if count > 1:
        return ("AMBIGUOUS", None)
    return ("READY", text.index(anchor))


def splice(rec, text, idx):
    anchor = rec["anchor"]
    where = rec["where"]
    if where == "after":
        cut = idx + len(anchor)
        return text[:cut] + rec["payload"] + text[cut:]
    if where == "before":
        return text[:idx] + rec["payload"] + text[idx:]
    if where == "replace":
        return text[:idx] + rec["payload"] + text[idx + len(anchor):]
    raise ValueError(f"{rec['id']}: bad 'where' value {where!r}")


def main():
    patches = DATA["patches"]

    # Group records by file, preserving patches.json order within each file.
    # Both passes iterate this same grouping so pass-1's classification and
    # pass-2's application run the identical cumulative sequence.
    by_file = {}
    for rec in patches:
        by_file.setdefault(rec["file"], []).append(rec)

    # Pass 1: classify CUMULATIVELY -- exactly as pass 2 applies. A record may
    # legitimately anchor on an earlier sibling's injected sentinel/payload (a
    # chained anchor); classifying against the raw file would wrongly report it
    # MISSING. So we splice each READY record into an IN-MEMORY copy as we go --
    # never to disk -- so a later chained anchor sees its sibling, mirroring what
    # pass 2 does. Abort before ANY write if a record is genuinely
    # MISSING/AMBIGUOUS -- never half-patch then compile. The simulated text is
    # discarded; pass 2 re-reads each file from disk.
    state_by_id = {}
    failed = False
    for relpath, recs in by_file.items():
        path = os.path.join(FA_DIR, relpath)
        if not os.path.isfile(path):
            for rec in recs:
                state_by_id[rec["id"]] = "MISSINGFILE"
            failed = True
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for rec in recs:
            state, pos = classify(rec, text)
            state_by_id[rec["id"]] = state
            if state == "READY":
                text = splice(rec, text, pos)   # in-memory dry run; discarded
            elif state in ("MISSING", "AMBIGUOUS"):
                failed = True

    # Report in patches.json order (stable, matches historical output).
    for rec in patches:
        state = state_by_id[rec["id"]]
        if state == "MISSINGFILE":
            print(f"{RED}MISSING FILE{RST} {rec['id']}: {rec['file']} not found")
            continue
        colour = {"ALREADY": DIM, "READY": GRN, "MISSING": RED, "AMBIGUOUS": RED}[state]
        print(f"{colour}{state:<9}{RST} {rec['id']:<22} {DIM}{rec['file']}{RST}")

    if failed:
        print(f"\n{RED}ABORTED{RST}: one or more anchors could not be located "
              f"uniquely. Upstream moved them -- re-author via "
              f"`/fa-codepatch author`. No files were modified.")
        return 1

    if STATUS_ONLY:
        print(f"\n{DIM}status only -- no changes written{RST}")
        return 0

    # Pass 2: apply READY patches. Reuse the same file grouping; each insert
    # re-locates its anchor against the freshly-updated text (cumulative), and
    # the final pass-2 abort below stays as a defensive guard.
    applied = 0
    for relpath, recs in by_file.items():
        path = os.path.join(FA_DIR, relpath)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        changed = False
        for rec in recs:
            state, pos = classify(rec, text)
            if state == "ALREADY":
                continue
            if state != "READY":
                # Re-check after a sibling edit; a clean abort already happened
                # in pass 1, so this only guards against an edit invalidating a
                # later anchor in the same file.
                print(f"{RED}ANCHOR LOST{RST} {rec['id']} after a sibling edit "
                      f"({state}). Aborting {relpath}; re-author the patch.")
                return 1
            text = splice(rec, text, pos)
            changed = True
            applied += 1
            print(f"{GRN}APPLIED  {RST} {rec['id']}")
        if changed:
            tmp = path + ".hlpatch.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)

    already = sum(1 for s in state_by_id.values() if s == "ALREADY")
    print(f"\n{GRN}done{RST}: {applied} applied, {already} already present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
