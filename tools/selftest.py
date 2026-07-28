#!/usr/bin/env python3
"""Fast pre-landing checks for the parts of this repo nothing else proves.

    python3 tools/selftest.py [FA_DIR]        # exit 0 = all checks passed

Runs in seconds, renders nothing, and writes nothing outside a temp directory.
It is a pre-landing gate for a human or a CI job, deliberately NOT wired into
install.sh: an installing user should not be blocked by a developer check, and
build.py already fails fast on the two things that would actually break their
install (it validates the help text before it renders a single tile).

WHAT THIS CANNOT DO, and why it is not a gap:

  - It does not compile FAangband. Anchors locating says nothing about whether
    the tree builds, so a `make -C <FA_DIR>` stays a separate, mandatory step
    (never-regress checklist item 3) -- it needs a toolchain, minutes, and a
    tree this script must not mutate.
  - It does not render the atlas or look at a pixel. Every tile invariant
    (duplicate cell, cell beyond 0x7F, block/animation conflicts) is enforced
    by build.py itself, in the loop that does the pasting. Re-implementing
    those checks here would create a second copy to drift out of step -- the
    build IS that test.
  - It does not run install.ps1. Nothing on a non-Windows host can. Check 4
    compares the two installers structurally instead, which catches the
    realistic failure (they drift apart) rather than pretending to catch the
    unrealistic one (PowerShell mis-executes).
  - It does not look at the game on screen. Tiles rendering correctly is a
    /fa-playtest question.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

FAIL = []
NOTES = []


def check(name):
    """Decorator: print a heading, catch failures.

    The contract for a checked function is: return None to pass, or a non-empty
    string describing the failure. Anything not-None is a failure -- tested that
    way rather than for truthiness so a check that returns "" cannot report a
    silent pass, which is the exact shape of bug this file exists to catch.
    """
    def wrap(fn):
        def run(*a, **kw):
            print(f"  {name} ... ", end="", flush=True)
            try:
                detail = fn(*a, **kw)
            except Exception as e:                      # a broken check is a failure
                print("FAIL")
                FAIL.append(f"{name}: {type(e).__name__}: {e}")
                return False
            if detail is not None:
                print(f"FAIL\n      {detail}")
                FAIL.append(f"{name}: {detail}")
                return False
            print("ok")
            return True
        return run
    return wrap


def fa_dir(argv):
    """The FAangband tree to test against: argv, $HL_FA_DIR, or beside us."""
    for cand in (argv[1] if len(argv) > 1 else None,
                 os.environ.get("HL_FA_DIR"),
                 ROOT.parent / "FAangband"):
        if cand and Path(cand, "src/ui-game.c").is_file():
            return Path(cand)
    return None


def git(fa, *args):
    return subprocess.run(["git", "-C", str(fa), *args],
                          capture_output=True, text=True)


# --------------------------------------------------------------------------
# 1 + 2. The help validators, in BOTH tree states.
#
# This is the check that exists because of 2026-07-25. build.py validates every
# {key:...} help token against the live <FA_DIR>/src/ui-game.c, but install.sh
# builds before it patches -- so on a fresh clone the build validates against a
# tree our own patches have not reached, and every token naming a command our
# song-cmd-* patches rename ("Sing a song") is reported as unknown. It shipped
# because a developer's tree is ALWAYS already patched from the last install: a
# patched tree passes whether or not the bug exists.
#
# So the fixture is the pristine file straight out of the FAangband tree's git
# object store, at the pinned baseline commit -- the exact state a fresh clone
# is in, materialised without touching the working tree.
# --------------------------------------------------------------------------
def pristine_tree(fa, commit, dest):
    """Materialise the files the help validators read, unpatched, into dest."""
    wanted = ["src/ui-game.c", "lib/customize/pref.prf"]
    for rel in wanted:
        r = git(fa, "show", f"{commit}:{rel}")
        if r.returncode != 0:
            return f"cannot read {rel} at {commit}: {r.stderr.strip()}"
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        # open(), not write_text(newline=): that argument is 3.10+ and this
        # project supports 3.6 -- the same reason build.py has write_lf().
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(r.stdout)
    return None


def run_help_validators(tree):
    """build.py's help pass against `tree`, into a temp dir. Returns None or the error."""
    import build
    with tempfile.TemporaryDirectory() as out:
        old = os.environ.get("HL_FA_DIR")
        os.environ["HL_FA_DIR"] = str(tree)
        try:
            # Swallow build.py's own chatter -- its progress bar goes to stderr
            # and its summary to stdout, and neither is this report's verdict,
            # which arrives as the SystemExit caught below.
            with open(os.devnull, "w") as null, redirect_stdout(null), redirect_stderr(null):
                build.build_help(json.loads((ROOT / "manifest.json").read_text()),
                                 outdir=out)
        except SystemExit as e:                  # build_help reports by exiting
            return str(e)
        finally:
            if old is None:
                os.environ.pop("HL_FA_DIR", None)
            else:
                os.environ["HL_FA_DIR"] = old
    return None


@check("help validators against an UNPATCHED tree")
def check_help_unpatched(fa, commit):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        err = pristine_tree(fa, commit, tmp)
        if err:
            return err
        err = run_help_validators(tmp)
        if err:
            return (err.replace("\n", "\n      ") +
                    "\n      (this is the fresh-clone state -- a check that reads the live"
                    "\n      tree must derive our own renames from patches.json)")
    return None


@check("help validators against the PATCHED tree")
def check_help_patched(fa):
    return run_help_validators(fa)


# --------------------------------------------------------------------------
# 3. Patch anchors. Read-only; --status writes nothing.
# --------------------------------------------------------------------------
@check("patch anchors all READY or ALREADY")
def check_anchors(fa):
    # Baseline drift is reported as a NOTE, never a failure: upstream moving is
    # normal and calls for the review in docs/never-regress.md, not for a red
    # light. A broken ANCHOR is the failure.
    b = subprocess.run([sys.executable, str(ROOT / "patches/apply_patches.py"),
                        str(fa), "--baseline"], capture_output=True, text=True)
    if "DRIFT" in (b.stdout + b.stderr).upper():
        NOTES.append("upstream has moved since the pinned baseline -- read the "
                     "drift report (apply_patches.py <FA_DIR> --baseline) before "
                     "trusting anchors that still match")

    r = subprocess.run([sys.executable, str(ROOT / "patches/apply_patches.py"),
                        str(fa), "--status"], capture_output=True, text=True)
    if r.returncode != 0:
        bad = [ln.strip() for ln in (r.stdout + r.stderr).splitlines()
               if "MISSING" in ln or "AMBIGUOUS" in ln]
        return "; ".join(bad[:6]) or f"apply_patches --status exited {r.returncode}"
    return None


# --------------------------------------------------------------------------
# 4. The two installers must stay one behaviour.
#
# install.ps1 cannot be executed here, and install.sh cannot be executed on the
# platform install.ps1 serves, so neither is ever exercised where the other
# runs. Comparing their step sequences is the one check that actually catches
# how they fail in practice: someone edits one and forgets the other.
# --------------------------------------------------------------------------
# Leading whitespace and either quote style, because a step announced inside an
# `if` is still a step and PowerShell needs double quotes wherever it
# interpolates. A step number appears more than once on purpose (the sized and
# unsized build branches announce the same step), so collect every wording per
# number and compare the SETS -- taking "the first one" would make the check
# depend on which branch each file happens to write first, and fail spuriously
# the day someone swaps them.
SH_STEP = re.compile(r'^\s*step (\d+) ["\']([^"\']+)', re.M)
PS_STEP = re.compile(r'^\s*Write-Step (\d+) ["\']([^"\']+)', re.M)


def normalise(text):
    """Strip the trailing ellipsis and the trivia the two shells must differ in:
    path separators, and the case of a variable name ($SIZE vs $Size)."""
    return text.split(" ...")[0].lower().replace("/", "\\")


def steps_by_number(pairs):
    out = {}
    for n, text in pairs:
        out.setdefault(int(n), set()).add(normalise(text))
    return out


@check("install.sh and install.ps1 declare the same steps")
def check_installer_twins():
    sh = (ROOT / "install.sh").read_text()
    ps1 = ROOT / "install.ps1"
    if not ps1.is_file():
        return "install.ps1 is missing -- the Windows twin is part of the pair"
    ps = ps1.read_text()

    sh_total = re.search(r"^TOTAL_STEPS=(\d+)", sh, re.M)
    ps_total = re.search(r"^\$TotalSteps = (\d+)", ps, re.M)
    if not sh_total or not ps_total:
        return "cannot find TOTAL_STEPS / $TotalSteps"
    if sh_total.group(1) != ps_total.group(1):
        return f"declared step count differs: sh={sh_total.group(1)} ps1={ps_total.group(1)}"

    a = steps_by_number(SH_STEP.findall(sh))
    b = steps_by_number(PS_STEP.findall(ps))
    total = int(sh_total.group(1))
    if sorted(a) != list(range(1, total + 1)):
        return f"install.sh announces steps {sorted(a)} but TOTAL_STEPS={total}"
    if sorted(b) != list(range(1, total + 1)):
        return f"install.ps1 announces steps {sorted(b)} but $TotalSteps={total}"
    for n in sorted(a):
        if a[n] != b[n]:
            return (f"step {n} differs: sh={sorted(a[n])} ps1={sorted(b[n])}")
    return None


# --------------------------------------------------------------------------
# 5. Shell portability. Each of these is a GNU extension that fails on
# macOS/BSD -- and the grep \b case fails SILENTLY, answering "not registered"
# every run and appending a duplicate SUBDIRS entry each time.
# --------------------------------------------------------------------------
GNUISMS = [
    (re.compile(r"(?<!\w)sed\s+(-i(?!\w)|--in-place)"),
     "sed -i (BSD sed requires a suffix argument)"),
    (re.compile(r"\$\(\s*mktemp\s*\)"),
     "mktemp without a template (BSD mktemp requires one)"),
    # Any grep, not only -E: GNU honours \b in basic regexes too, so a BRE
    # spelling would slip past a pattern that insisted on the -E flag.
    (re.compile(r"(?<!\w)grep\b[^|\n]*\\b"),
     r"\b in a grep pattern (GNU-only word boundary; fails open on BSD)"),
    (re.compile(r"(?<!\w)readlink\s+-f"),
     "readlink -f (not on macOS before coreutils)"),
    (re.compile(r"grep\s+-[a-zA-Z]*P"),
     "grep -P (no PCRE in BSD grep)"),
]


@check("install.sh is free of GNU-only constructs")
def check_portability():
    bad = []
    for n, line in enumerate((ROOT / "install.sh").read_text().splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue                              # the header names them on purpose
        for rx, why in GNUISMS:
            if rx.search(line):
                bad.append(f"line {n}: {why}")
    return "; ".join(bad) or None


# --------------------------------------------------------------------------
# 6. Generated files must be written with an explicit LF. Path.write_text()
# opens in text mode, so on Windows it emits CRLF -- and a stray CR inside the
# generated lib/tiles/Makefile becomes part of a filename, while one inside
# anim.txt becomes part of a frame count. Both are read as data, not rejected.
# --------------------------------------------------------------------------
@check("build.py writes generated files through write_lf")
def check_lf_writers():
    # Parsed, not grepped: the docstring that EXPLAINS why write_text is wrong
    # names it, and a check that cannot tell a call from prose about a call
    # would fail on its own documentation.
    import ast
    tree = ast.parse((ROOT / "tools/build.py").read_text())
    bad = sorted(node.lineno for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and node.func.attr == "write_text")
    return ("use write_lf() instead at line(s) "
            + ", ".join(str(n) for n in bad)) if bad else None


# --------------------------------------------------------------------------
# 7. The generated Makefile must reference only files that actually exist.
#
# This is the check that exists because of 2026-07-27 (issue #17). build.py
# emits a Makefile whose DATA line lists every file `make install` should
# deploy. If a best-effort step (light atlas, animation) skips but its output
# is listed unconditionally, the build reports success and `make install` fails
# on the user's machine with "install: No such file or directory". build.py
# now has its own post-emit guard, but selftest catches a regression even when
# the developer does not rebuild before committing.
# --------------------------------------------------------------------------
@check("generated Makefile DATA files all exist in dist")
def check_makefile_data():
    m = json.loads((ROOT / "manifest.json").read_text())
    outdir = ROOT / "dist" / m["tileset"]["directory"]
    mf = outdir / "Makefile"
    if not mf.is_file():
        NOTES.append("dist/ not built -- skipping Makefile DATA check "
                     "(run build.py to enable)")
        return None
    match = re.search(r"^DATA\s*=\s*(.+)$", mf.read_text(), re.M)
    if not match:
        return "no DATA line found in generated Makefile"
    missing = [f for f in match.group(1).split()
               if not (outdir / f).is_file()]
    if missing:
        return (f"Makefile DATA lists files not in {outdir.relative_to(ROOT)}: "
                + " ".join(missing))
    return None


def main():
    fa = fa_dir(sys.argv)
    if not fa:
        sys.exit("selftest: no FAangband tree found -- pass one: "
                 "python3 tools/selftest.py <FA_DIR>")
    pins = json.loads((ROOT / "patches/patches.json").read_text())
    commit = pins.get("upstream", {}).get("commit", "HEAD")
    if git(fa, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        NOTES.append(f"pinned baseline {commit[:9]} is not in {fa} -- "
                     "the unpatched fixture falls back to HEAD")
        commit = "HEAD"

    print(f"selftest: {fa}  (unpatched fixture from {commit[:9]})")
    check_help_unpatched(fa, commit)
    check_help_patched(fa)
    check_anchors(fa)
    check_installer_twins()
    check_portability()
    check_lf_writers()
    check_makefile_data()

    for note in NOTES:
        print(f"  note: {note}")
    if FAIL:
        print(f"\n{len(FAIL)} check(s) FAILED:")
        for f in FAIL:
            print(f"  - {f}")
        print("\nStill required by hand: a full `make -C <FA_DIR>` "
              "(never-regress checklist item 3).")
        return 1
    print("\nall checks passed. Still required by hand: a full "
          "`make -C <FA_DIR>` -- anchors locating says nothing about "
          "whether the tree builds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
