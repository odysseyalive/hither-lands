#!/usr/bin/env python3
"""Anchor-based, idempotent C-source patcher for the FAangband tree.

Authored/maintained by the /fa-codepatch skill. Patches are located in the
source by a literal content anchor (re-derived every run, never a stored line
number) and made idempotent by a sentinel marker comment that the applier
checks for before inserting. Mirrors the grep-guard discipline in install.sh.

Usage:
    python3 apply_patches.py <FA_DIR> [--status | --baseline | --repin]

    (no flag)   report baseline drift, then classify and apply
    --status    report baseline drift, then classify only -- no writes
    --baseline  report baseline drift only; does not classify anchors (use --status
                for anchor states, or the patch-anchor-auditor agent to re-author)
    --repin     advance the baseline pin to the tree's HEAD, if it is provable there.
                Does NOT apply patches -- it only moves the pin.

    The three flags are mutually exclusive.

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

Top-level patches.json keys: version, note, upstream (the baseline pin), patches.

NEVER-REGRESS BASELINE
    `upstream` pins the exact FAangband commit every anchor was proven against. Every
    run compares the target tree's HEAD to that pin and, on drift, reports which ANCHORED
    files upstream touched in between -- naming the at-risk patch groups BEFORE anchors
    are attempted, so re-authoring is a planned step rather than a surprise abort. This
    catches the one failure anchors CANNOT self-detect: an upstream change ADJACENT to an
    anchor, where semantics move but the anchor still matches. (A `replace` patch is
    self-guarding by contrast -- its anchor IS the replaced region, so an upstream edit
    inside it forces MISSING.)

    The pin advances only through --repin, which appends to `upstream.history` so the
    baseline is always walkable backwards, and which refuses unless the new baseline is
    genuinely PROVABLE: the tree must carry git metadata, must not be behind or diverged
    from the current pin, must still contain the old pin (so the move is auditable), and
    every anchor must locate uniquely in HEAD's own blobs. That last check is the load-
    bearing one -- the working-tree classification CANNOT stand in for it, because
    classify() short-circuits on the sentinel, so on a tree install.sh already patched
    every record reports ALREADY while proving nothing about anchor validity. --repin
    writes ONLY under `upstream`; `patches` is hand-maintained and never machine-touched
    (skill invariant 5), asserted before the write.
"""
import datetime
import json
import os
import subprocess
import sys

KNOWN_FLAGS = {"--status", "--baseline", "--repin"}
# Gate on a single dash: `-h` would otherwise fall through to args and become FA_DIR.
_unknown = [a for a in sys.argv[1:] if a.startswith("-") and a not in KNOWN_FLAGS]
if _unknown:
    sys.exit(f"unknown flag(s): {' '.join(_unknown)}; "
             f"expected one of {' '.join(sorted(KNOWN_FLAGS))}")

# The modes are mutually exclusive, as the usage line claims. Without this,
# `--status --repin` writes to disk under a flag documented as read-only, and
# `--baseline --repin` returns early and silently ignores the re-pin.
_modes = [f for f in sorted(KNOWN_FLAGS) if f in sys.argv]
if len(_modes) > 1:
    sys.exit(f"flags are mutually exclusive: {' '.join(_modes)}")

STATUS_ONLY = "--status" in sys.argv
BASELINE_ONLY = "--baseline" in sys.argv
REPIN = "--repin" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("-")]
FA_DIR = args[0] if args else os.path.expanduser("~/lab/FAangband")
HERE = os.path.dirname(os.path.abspath(__file__))
PATCHES_JSON = os.path.join(HERE, "patches.json")

with open(PATCHES_JSON, encoding="utf-8") as fh:
    ORIGINAL_JSON = fh.read()
DATA = json.loads(ORIGINAL_JSON)

RED, GRN, YEL, DIM, RST = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


def git(*argv, raw=False):
    """Run git in FA_DIR; return stdout, or None if it fails / isn't a repo.

    The ""-vs-None distinction is load-bearing: a command that succeeds with no output
    (`merge-base --is-ancestor`, `cat-file -e`) yields "", which is falsy but NOT None.
    Callers testing those must use `is not None`, never truthiness.

    raw=True skips the strip(), which is mandatory for FILE CONTENT (`git show HEAD:f`):
    anchors are literal substrings that routinely end in "\\n", and stripping a blob's
    trailing newline makes an end-of-file anchor fail to match for no real reason.
    """
    try:
        out = subprocess.run(("git", "-C", FA_DIR) + argv, capture_output=True,
                             text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout if raw else out.stdout.strip()


def baseline_status(by_file):
    """Compute drift between the pinned upstream commit and the tree's HEAD. Pure.

    Returns a record; prints nothing, so the safety signals it derives (`ahead`,
    `pin_present`, `pristine`) reach repin() instead of dying in a print statement.
    `state` is one of: no-git, no-pin, ok, pin-absent, drift.
    """
    pin = DATA.get("upstream", {})
    pinned = pin.get("commit")
    head = git("rev-parse", "HEAD")
    st = {"pin": pin, "pinned": pinned, "head": head, "ahead": False,
          "behind": False, "pin_present": False, "touched": [], "span": None,
          "pristine": False}

    if head is None:
        st["state"] = "no-git"
        return st
    # A tree install.sh has already patched is NOT pristine -- its files no longer match
    # the commit HEAD names, so anchors cannot be proven against them.
    st["pristine"] = git("status", "--porcelain") == ""
    if not pinned:
        st["state"] = "no-pin"
        return st
    if head == pinned:
        st["state"] = "ok"
        return st

    st["state"] = "drift"
    if git("cat-file", "-e", pinned + "^{commit}") is None:
        return st                                  # pin_present stays False
    st["pin_present"] = True
    st["ahead"] = git("merge-base", "--is-ancestor", pinned, head) is not None
    st["behind"] = git("merge-base", "--is-ancestor", head, pinned) is not None

    lo, hi = (pinned, head) if st["ahead"] else (head, pinned)
    if not (st["ahead"] or st["behind"]):
        st["span"] = f"{pinned}...{head}"          # diverged: symmetric difference
    else:
        st["span"] = f"{lo}..{hi}"
    log = git("log", "--name-only", "--pretty=format:", st["span"], "--", *sorted(by_file))
    st["touched"] = sorted({ln for ln in (log or "").splitlines() if ln.strip()})
    return st


def report_baseline(st, by_file):
    """Print the drift report. Formatting only -- all decisions live in baseline_status.

    Advisory, never fatal: a drifted tree may still patch cleanly, and the two-pass
    classifier stays the authority on whether it does. The value added here is naming
    which patch groups upstream put at risk.
    """
    pinned, head, pin = st["pinned"], st["head"], st["pin"]

    if st["state"] == "no-git":
        print(f"{DIM}baseline: no git metadata in {FA_DIR} -- drift not evaluated"
              f"{' (pinned ' + pinned[:9] + ')' if pinned else ''}{RST}\n")
        return
    if st["state"] == "no-pin":
        print(f"{YEL}NO BASELINE{RST}: patches.json has no upstream.commit pin. "
              f"Run --repin against a pristine tree to establish one.\n")
        return
    if st["state"] == "ok":
        print(f"{GRN}baseline OK{RST} {DIM}upstream at pinned {pinned[:9]} "
              f"({pin.get('date', '?')}){RST}\n")
        return

    print(f"{YEL}BASELINE DRIFT{RST}: tree HEAD {head[:9]} != pinned {pinned[:9]} "
          f"({pin.get('date', '?')})")
    if not st["pin_present"]:
        print(f"{YEL}  the pinned commit is not present in this tree{RST} -- "
              f"`git -C {FA_DIR} fetch` to compare, or this is a different clone.\n")
        return
    if not st["ahead"]:
        which = "BEHIND" if st["behind"] else "DIVERGED from"
        print(f"{YEL}  this tree is {which} the baseline{RST} -- --repin is refused "
              f"here; it would move the baseline onto ground the anchors were never "
              f"proven against.")

    short = "..".join(p[:9] for p in st["span"].replace("...", "..").split(".."))
    if not st["touched"]:
        print(f"{GRN}  no anchored file differs across the range{RST} -- drift is "
              f"confined to files we never patch."
              f"{' Safe to --repin after a clean run.' if st['ahead'] else ''}\n")
        return

    print(f"{YEL}  {len(st['touched'])} anchored file(s) differ across {short} -- "
          f"these patch groups are AT RISK:{RST}")
    for path in st["touched"]:
        ids = [rec["id"] for rec in by_file.get(path, [])]
        groups = sorted({i.rsplit("-", 1)[0] if "-" in i else i for i in ids})
        print(f"    {path:<34} {DIM}{len(ids)} patch(es): {', '.join(groups)}{RST}")
    print(f"{DIM}  Review each with: git -C {FA_DIR} log -p {st['span']} -- <file>{RST}")
    print(f"{DIM}  An anchor that still matches is NOT proof of correctness when the "
          f"code around it moved. Anchor states: --status{RST}\n")


def prove_against_upstream(by_file):
    """Re-prove every anchor against the PRISTINE upstream blobs at HEAD.

    This is the whole point of the pin, and it cannot be delegated to the working-tree
    classification in main(): `classify` short-circuits on the sentinel, so on a tree
    install.sh has already patched, all 83 records report ALREADY -- proving the tree was
    patched and NOTHING about whether the anchors still locate. `replace` records are
    worse: applying them destroys their own anchor, so it can never be re-found in a
    patched file. Reading `git show HEAD:<file>` sidesteps both.

    Uses the same cumulative in-memory splice as pass 1, so a record legitimately
    anchoring on an earlier sibling's payload still resolves. Returns a list of
    (id, state) failures -- empty means every anchor is proven at HEAD.
    """
    failures = []
    for relpath, recs in by_file.items():
        text = git("show", f"HEAD:{relpath}", raw=True)
        if text is None:
            failures.extend((rec["id"], "NOBLOB") for rec in recs)
            continue
        for rec in recs:
            # Upstream blobs carry no sentinels, so classify() always reaches the anchor.
            state, pos = classify(rec, text)
            if state == "READY":
                text = splice(rec, text, pos)
            else:
                failures.append((rec["id"], state))
    return failures


def repin(st, by_file):
    """Advance the baseline pin. Only ever mutates DATA['upstream'].

    Refuses unless the new baseline is actually provable: the tree must have git
    metadata, must not be behind/diverged from the current pin, must contain the old pin
    (so the move is auditable), and every anchor must locate uniquely against HEAD's own
    blobs. A pin that outruns its proof is worse than no pin.
    """
    head = st["head"]
    if head is None:
        print(f"\n{RED}REPIN REFUSED{RST}: no git metadata in {FA_DIR}.")
        return 1

    pin = DATA.setdefault("upstream", {})
    if pin.get("commit") == head:
        print(f"\n{DIM}pin already at {head[:9]} -- nothing to advance.{RST}")
        return 0
    if st["state"] == "drift" and not st["pin_present"]:
        print(f"\n{RED}REPIN REFUSED{RST}: the current pin {st['pinned'][:9]} is not in "
              f"this tree, so the move from it cannot be audited. `git -C {FA_DIR} fetch` "
              f"first, or re-pin from the clone the baseline came from.")
        return 1
    if st["state"] == "drift" and not st["ahead"]:
        which = "behind" if st["behind"] else "diverged from"
        print(f"\n{RED}REPIN REFUSED{RST}: this tree is {which} the pinned baseline "
              f"{st['pinned'][:9]}. Advancing here moves the baseline onto ground the "
              f"anchors were never proven against.")
        return 1

    failures = prove_against_upstream(by_file)
    if failures:
        print(f"\n{RED}REPIN REFUSED{RST}: {len(failures)} anchor(s) do not locate "
              f"uniquely in HEAD's own blobs -- the working tree classifying clean only "
              f"proves it was already patched. Re-author these first:")
        for pid, state in failures:
            print(f"    {RED}{state:<9}{RST} {pid}")
        return 1

    today = datetime.date.today().isoformat()
    cdate = git("log", "-1", "--format=%cs") or today
    pin["commit"] = head
    # Fall back to the existing value, never to "" -- a transient git failure must not
    # silently erase good metadata.
    pin["describe"] = git("describe", "--tags", "--always") or pin.get("describe", "")
    pin["subject"] = git("log", "-1", "--format=%s") or pin.get("subject", "")
    pin["date"] = cdate
    pin["verified"] = today
    # history is every baseline, newest last -- history[-1] IS the current pin.
    pin.setdefault("history", []).append({
        "commit": head,
        "date": cdate,
        "verified": today,
        "patches": len(DATA["patches"]),
        "note": f"Re-pinned after all {len(DATA['patches'])} anchors were re-proven "
                f"against this commit's own blobs.",
    })

    # indent=2 + default separators/ensure_ascii + trailing newline currently round-trips
    # this file byte-identically, so the diff shows only the `upstream` lines that
    # changed. That is a property of the file, not a guarantee -- one hand-added non-ASCII
    # character or a reflowed hand-edit would make this rewrite the whole 75k document,
    # burying the pin change among reformatted anchor payloads. Assert it, don't assume.
    if json.dumps(json.loads(ORIGINAL_JSON), indent=2) + "\n" != ORIGINAL_JSON:
        print(f"\n{RED}REPIN REFUSED{RST}: patches.json no longer round-trips "
              f"byte-stably -- a hand-edit introduced non-ASCII or different formatting, "
              f"so this rewrite would reflow the whole file and bury the pin change among "
              f"reformatted anchor payloads. Re-pin by hand, or normalise the file first.")
        return 1
    rendered = json.dumps(DATA, indent=2) + "\n"
    # Invariant 5: `patches` is hand-maintained and never machine-written. Assert it here
    # so a future edit to this function cannot quietly break it.
    if json.loads(rendered)["patches"] != json.loads(ORIGINAL_JSON)["patches"]:
        print(f"\n{RED}REPIN REFUSED{RST}: the rewrite would alter `patches` -- "
              f"--repin writes only under `upstream`.")
        return 1

    tmp = PATCHES_JSON + ".repin.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        os.replace(tmp, PATCHES_JSON)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"\n{GRN}REPINNED{RST} baseline -> {head[:9]} ({cdate}). "
          f"history now has {len(pin['history'])} entr(ies).")
    print(f"{DIM}Commit patches.json with the re-authored anchors in the SAME change.{RST}")
    return 0


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
    # pass-2's application run the identical cumulative sequence. The baseline
    # report and --repin's upstream-blob proof reuse it too.
    by_file = {}
    for rec in patches:
        by_file.setdefault(rec["file"], []).append(rec)

    # Baseline first: an upstream that moved is announced BEFORE anchors are attempted,
    # so a re-author is a planned step rather than a surprise abort mid-install.
    baseline = baseline_status(by_file)
    report_baseline(baseline, by_file)
    if BASELINE_ONLY:
        return 0

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
        if REPIN:
            print(f"\n{RED}REPIN REFUSED{RST}: the pin may never advance past a broken "
                  f"anchor. Re-author the records below first, then --repin.")
        print(f"\n{RED}ABORTED{RST}: one or more anchors could not be located "
              f"uniquely. Upstream moved them -- re-author via "
              f"`/fa-codepatch author`. No files were modified.")
        return 1

    # The working tree classifying clean is necessary but NOT sufficient -- repin()
    # re-proves every anchor against HEAD's own blobs, because ALREADY says only that
    # the tree was patched.
    if REPIN:
        return repin(baseline, by_file)

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
