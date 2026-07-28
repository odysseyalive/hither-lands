<#
.SYNOPSIS
    Install the built tileset into an FAangband source tree, then compile it.
    The Windows PowerShell twin of install.sh -- same seven steps, same order,
    same guarantees.

.DESCRIPTION
    Builds the atlas and prf files from manifest.json + source-tiles/, copies
    them into <FaDir>\lib\tiles\, registers the tileset in list.txt and the
    build system, applies the C source patches, then runs the build command
    this tree's own configuration calls for and prints how to start the game.

    Installs into the SOURCE tree (not an installed prefix) on purpose:
    FAangband's own `make install` then deploys it alongside the stock
    tilesets, and the registration survives future `make install` runs.

    There is no gender option. Both genders ship in the one player-sprite prf,
    and the character's own choice at character generation picks between them:
    the HITHER-LANDS:pgender-* patches applied in step 6 add a birth menu stage
    and a $GENDER pref variable that the prf's conditional lines read.

.PARAMETER FaDir
    Path to the FAangband source tree. Defaults to ..\FAangband beside this
    repo, then $HOME\lab\FAangband.

.PARAMETER Size
    Tile resolution: 32, 64 (default, from manifest.json) or 128. Source tiles
    are 1024px native, so 64 and 128 carry real detail; 32 is a lightweight
    fallback. The whole tileset rebuilds at that size and the list.txt
    registration is written to match.

.PARAMETER Yes
    Acknowledge the step-1 local-changes notice without prompting, for
    non-interactive runs. Without it, a tree carrying changes this installer
    did not make asks "Proceed with installation, Y/n?" and stops if the host
    is non-interactive -- the acknowledgement is the point, so it is never
    assumed.

.EXAMPLE
    .\install.ps1 ..\FAangband

.EXAMPLE
    .\install.ps1 ..\FAangband -Size 64 -Yes

.NOTES
    Requires: PowerShell 5.1+ (Windows PowerShell or PowerShell 7), Python 3.6+
    with Pillow, and a `make` FAangband can build with -- MSYS2/MinGW is the
    usual source of both make and the SDL2 headers. Without make on PATH the
    script still installs everything and prints the build command to run.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$FaDir,

    [ValidateSet('32', '64', '128')]
    [string]$Size,

    [switch]$Yes
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$UpstreamUrl = 'https://github.com/NickMcConnell/FAangband.git'
$TotalSteps = 7

function Write-Step([int]$n, [string]$text) { Write-Host ("[{0}/{1}] {2}" -f $n, $TotalSteps, $text) }
function Write-Detail([string]$text) { Write-Host "      $text" }
# Plain stderr + exit 1, not Write-Error: an installer's failure should read as
# one sentence a person can act on, not as a PowerShell error record quoting
# the line of script that raised it -- and this way the exit code is certain.
function Fail([string]$text) { [Console]::Error.WriteLine("error: $text"); exit 1 }

# --- interpreter ------------------------------------------------------------
# There is no `python3` on a stock Windows install: the launcher is `py -3`,
# and a Microsoft Store or venv install answers to `python`. Probe rather than
# hardcode, and prove the interpreter is 3.6+ with Pillow before the build
# rather than after several minutes of it.
function Resolve-Python {
    $candidates = @(
        @{ Exe = 'py';      Pre = @('-3') },
        @{ Exe = 'python3'; Pre = @() },
        @{ Exe = 'python';  Pre = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        $pre = @($c.Pre)
        & $c.Exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 6) else 1)" 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        return $c
    }
    Fail "no Python 3.6+ found. Install it from python.org (tick 'Add python.exe to PATH'), then: py -3 -m pip install Pillow"
}

function Invoke-Python {
    # Called without assigning the result, so python's own output streams
    # straight to the console instead of being captured as a return value.
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $pyArgs = @($script:Py.Pre) + $Arguments
    & $script:Py.Exe @pyArgs
    if ($LASTEXITCODE -ne 0) { Fail "python exited $LASTEXITCODE" }
}

# --- text files -------------------------------------------------------------
# Every file this script rewrites is read by make or by the C engine, never by
# a person: lib\tiles\Makefile, list.txt, lib\help\Makefile. PowerShell's own
# Set-Content would write CRLF, and a stray CR inside a make variable becomes
# part of a filename. So read and write through .NET with explicit LF and no
# BOM. (tools\build.py writes its own output the same way, via write_lf().)
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
function Read-TextLf([string]$path) { [IO.File]::ReadAllText($path).Replace("`r`n", "`n") }
function Write-TextLf([string]$path, [string]$text) { [IO.File]::WriteAllText($path, $text.Replace("`r`n", "`n"), $Utf8NoBom) }

# --- resolve the target tree ------------------------------------------------
if (-not $FaDir) {
    foreach ($cand in @((Join-Path (Split-Path -Parent $Here) 'FAangband'), (Join-Path $HOME 'lab\FAangband'))) {
        if (Test-Path (Join-Path $cand 'lib\tiles\list.txt')) { $FaDir = $cand; break }
    }
    if (-not $FaDir) { Fail "no FAangband tree found beside this repo or at `$HOME\lab\FAangband -- pass the path: .\install.ps1 ..\FAangband" }
}
if (-not (Test-Path -LiteralPath $FaDir)) { Fail "FAangband tree not found: $FaDir" }
$FaDir = (Resolve-Path -LiteralPath $FaDir).Path
$TilesDir = Join-Path $FaDir 'lib\tiles'
if (-not (Test-Path (Join-Path $TilesDir 'list.txt'))) {
    Fail "$TilesDir\list.txt not found -- is $FaDir an FAangband tree?"
}

$Py = Resolve-Python
Invoke-Python -Arguments @('-c', 'import PIL')  # fails loudly here, not mid-build

# Optional dependencies: warn upfront so the user knows before the long build,
# not minutes later when the step silently skips.
$optMissing = @()
$pyCheck = @($Py.Pre) + @('-c', 'import numpy')
& $Py.Exe @pyCheck 2>$null
if ($LASTEXITCODE -ne 0) { $optMissing += '  - numpy: enables the light-mode atlas (pip install numpy)' }
$pyCheck = @($Py.Pre) + @('-c', 'import reportlab')
& $Py.Exe @pyCheck 2>$null
if ($LASTEXITCODE -ne 0) { $optMissing += '  - reportlab: enables PDF help export (pip install reportlab)' }
if ($optMissing) {
    Write-Host 'note: optional dependencies not installed (the atlas build is unaffected):'
    $optMissing | ForEach-Object { Write-Host $_ }
    Write-Host ''
}

$dirNameArgs = @($Py.Pre) + @('-c', "import json; print(json.load(open(r'$Here\manifest.json'))['tileset']['directory'])")
$DirName = (& $Py.Exe @dirNameArgs | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or -not $DirName) { Fail "could not read tileset.directory from manifest.json" }
$DirName = $DirName.Trim()
$Dist = Join-Path $Here "dist\$DirName"

# --- 1. preflight -----------------------------------------------------------
# Two kinds of local change live in the target tree and they mean opposite
# things. Our own installs edit tracked files -- every patches.json target,
# plus lib\help\, lib\tiles\ and the sleepiness pass over monster.txt -- so a
# tree installed into before is ALWAYS dirty, and treating that as a warning
# would nag on every re-run and hard-stop every non-interactive one. A change
# to any OTHER file is a real unknown: it is what makes an anchor ambiguous, or
# a conflict on the next upstream pull. So classify, then ask only about the
# unknowns. (Upstream having MOVED is a separate question, answered by the
# baseline-drift report apply_patches.py prints in step 6.)
Write-Step 1 'Checking the FAangband tree for local changes ...'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Detail 'git not found -- skipping the local-changes check'
} else {
    $null = & git -C $FaDir rev-parse --git-dir 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Detail "$FaDir is not a git repository -- skipping the local-changes check"
    } else {
        $dirty = @(& git -C $FaDir status --porcelain --untracked-files=no | Where-Object { $_ })
        if (-not $dirty) {
            Write-Detail 'clean'
        } else {
            # Paths this installer itself writes. Derived from patches.json
            # rather than listed here, so a new patch group never silently
            # reclassifies as a foreign edit.
            $ours = @('lib/gamedata/monster.txt')   # tools/adjust_sleepiness.py
            $patchesJson = Join-Path $Here 'patches\patches.json'
            if (Test-Path $patchesJson) {
                $ours += @((Get-Content -Raw -LiteralPath $patchesJson | ConvertFrom-Json).patches |
                    Where-Object { $_.PSObject.Properties.Name -contains 'file' -and $_.file } |
                    ForEach-Object { $_.file })
            }
            $ours = @($ours | Sort-Object -Unique)

            $foreign = @()
            foreach ($line in $dirty) {
                # Rename lines read "R  old -> new"; keep the destination path.
                $p = $line.Substring(3).Trim('"')
                if ($p -match ' -> ') { $p = ($p -split ' -> ')[-1].Trim('"') }
                if ($p -like 'lib/help/*' -or $p -like 'lib/tiles/*') { continue }
                if ($ours -contains $p) { continue }
                $foreign += $p
            }

            if ($foreign.Count -eq 0) {
                Write-Detail 'dirty, but every change is one this installer makes'
                Write-Detail '(previous install: patched C sources, tiles, help, gamedata).'
                Write-Detail 'To install against pristine upstream instead, stash and pull first.'
            } else {
                $origin = & git -C $FaDir remote get-url origin 2>$null
                if ($LASTEXITCODE -ne 0 -or -not $origin) { $origin = $UpstreamUrl }
                Write-Host ''
                Write-Host "  NOTICE: $FaDir carries $($foreign.Count) local change(s) this installer did not make:"
                $foreign | Select-Object -First 20 | ForEach-Object { Write-Host "      $_" }
                if ($foreign.Count -gt 20) { Write-Host "      ... and $($foreign.Count - 20) more" }
                Write-Host @"

  Those changes should be stashed and the latest code pulled from the official
  FAangband repository before installing, so the C patches apply to a tree we
  know:

      git -C "$FaDir" stash push --include-untracked
      git -C "$FaDir" pull --ff-only $origin

  Then re-run this script; step 6 reapplies our patches from scratch.
"@
                Write-Host ''
                if ($Yes) {
                    Write-Host '  -Yes given -- proceeding without asking.'
                } elseif ($Host.UI.RawUI -and [Environment]::UserInteractive) {
                    $ack = Read-Host '  Proceed with installation, Y/n'
                    if ($ack -and $ack -notmatch '^(y|yes)$') {
                        Write-Host '  Aborted -- nothing was changed.'
                        exit 1
                    }
                } else {
                    Fail "the FAangband tree has local changes we did not make, and this host is not interactive. Stash them, or re-run with -Yes to proceed."
                }
                Write-Host ''
            }
        }
    }
}

# --- 2. build ---------------------------------------------------------------
if ($Size) {
    Write-Step 2 "Building tileset at ${Size}x${Size} (tools/build.py) ..."
    Invoke-Python -Arguments @("$Here\tools\build.py", '--size', $Size)
} else {
    Write-Step 2 'Building tileset (tools/build.py) ...'
    Invoke-Python -Arguments @("$Here\tools\build.py")
}
# Catch the exit-0-but-no-output case (e.g. manifest tileset.directory not
# matching what build.py wrote); a non-zero build.py already threw above.
if (-not (Test-Path $Dist)) { Fail "build did not produce $Dist (directory-name mismatch?)" }

# --- 3. copy ----------------------------------------------------------------
Write-Step 3 "Copying tileset '$DirName' -> $TilesDir ..."
$target = Join-Path $TilesDir $DirName
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Copy-Item -Recurse -Force $Dist $target

# In-game documentation: the guide topics plus the tile-plate index that the
# help-tile patches read. Built into dist\help by tools/build.py, which resolves
# {tile:...} markers -- never install help-source\ directly.
$HelpSrc = Join-Path $Here 'dist\help'
if (Test-Path $HelpSrc) {
    $helpDst = Join-Path $FaDir 'lib\help'
    $helpFiles = @(Get-ChildItem -Path $HelpSrc -File | Where-Object { $_.Extension -eq '.txt' -or $_.Name -eq 'help-tiles.idx' })
    foreach ($f in $helpFiles) { Copy-Item -Force $f.FullName $helpDst }
    $helpMk = Join-Path $helpDst 'Makefile'
    if (Test-Path $helpMk) {
        $mk = Read-TextLf $helpMk
        $before = $mk
        foreach ($f in $helpFiles) {
            if ($mk -notmatch [regex]::Escape($f.Name)) {
                $mk = $mk -replace '(?m)^DATA = ', ("DATA = " + $f.Name + " ")
            }
        }
        # Only write when something was actually added: rewriting an unchanged
        # file would still normalise its line endings, which on Windows shows up
        # as the whole Makefile modified for no reason.
        if ($mk -ne $before) { Write-TextLf $helpMk $mk }
    }
    Write-Host "  installed $($helpFiles.Count) help files"
}

# --- 4. register in lib\tiles\Makefile --------------------------------------
Write-Step 4 'Registering in lib\tiles\Makefile ...'
$tilesMkPath = Join-Path $TilesDir 'Makefile'
$tilesMk = Read-TextLf $tilesMkPath
$subdirs = ($tilesMk -split "`n" | Where-Object { $_ -match '^SUBDIRS' } | Select-Object -First 1)
if ($subdirs -and (" " + ($subdirs -replace '^[^=]*=[ \t]*', '') + " ") -like "* $DirName *") {
    Write-Detail 'already registered'
} else {
    $tilesMk = $tilesMk -replace '(?m)^(SUBDIRS = .*)$', ('$1 ' + $DirName)
    Write-TextLf $tilesMkPath $tilesMk
    Write-Detail "added '$DirName' to SUBDIRS"
}

# --- 5. register in lib\tiles\list.txt --------------------------------------
Write-Step 5 'Registering in lib\tiles\list.txt ...'
$listPath = Join-Path $TilesDir 'list.txt'
$list = Read-TextLf $listPath
$stanza = Read-TextLf (Join-Path $Here 'dist\list-stanza.txt')
if ($list -notmatch "(?m)^directory:$([regex]::Escape($DirName))`$") {
    $serials = @([regex]::Matches($list, '(?m)^name:(\d+):') | ForEach-Object { [int]$_.Groups[1].Value })
    $serial = 1
    if ($serials.Count -gt 0) { $serial = ($serials | Measure-Object -Maximum).Maximum + 1 }
    if (-not $list.EndsWith("`n")) { $list += "`n" }
    Write-TextLf $listPath ($list + "`n" + ($stanza -replace '@SERIAL@', $serial))
    Write-Detail "added with serial $serial"
} else {
    # Already registered -- refresh the size:/atlas line in case -Size (or the
    # manifest) changed it, so the registration matches the atlas we just built.
    $newSize = (($stanza -split "`n") | Where-Object { $_ -match '^size:' } | Select-Object -First 1)
    $out = New-Object System.Collections.Generic.List[string]
    $inDir = $false
    foreach ($line in ($list -split "`n")) {
        if ($line -eq "directory:$DirName") { $out.Add($line); $inDir = $true; continue }
        if ($inDir -and $line -match '^size:') { $out.Add($newSize); $inDir = $false; continue }
        $out.Add($line)
    }
    Write-TextLf $listPath ($out -join "`n")
    Write-Detail "already registered -- updated $newSize"
}

# --- 6. C source patches ----------------------------------------------------
Write-Step 6 'Applying C source patches ...'
if (Test-Path (Join-Path $Here 'patches\apply_patches.py')) {
    Invoke-Python -Arguments @("$Here\patches\apply_patches.py", $FaDir)
} else {
    Write-Detail 'no patches\ -- skipped'
}

# 6b. Retune monster sleepiness for the ecosystem patches (idempotent -- the
#     script appends its own sentinel to monster.txt and no-ops if present).
if ((Test-Path (Join-Path $Here 'tools\adjust_sleepiness.py')) -and (Test-Path (Join-Path $FaDir 'lib\gamedata\monster.txt'))) {
    Invoke-Python -Arguments @("$Here\tools\adjust_sleepiness.py", $FaDir)
} else {
    Write-Detail 'no adjust_sleepiness.py or gamedata -- skipped'
}

Write-Host "Installed '$DirName' into $TilesDir (registered in list.txt + Makefile)."
Write-Host ''

# --- 7. compile -------------------------------------------------------------
# WHICH build command is correct depends on how this tree was configured, and
# getting it wrong is silent: `make install` is wrong for a run-in-place tree,
# while a plain `make` leaves a prefixed install still reading its old deployed
# data. mk\extra.mk is configure's own answer to that question (NOINSTALL /
# ENABLEWIN / prefix / bindir, already expanded), so read it rather than
# re-deriving the mode from the configure command line.
#
# On Windows the usual configuration is MSYS2 with --enable-win, which sets
# ENABLEWIN=yes: that build's `install` target is a no-op by design (see
# mk/buildsys.mk), so the game runs in place out of the source tree and a plain
# `make` is the whole story.
Write-Step 7 'Compiling FAangband ...'
$extraMk = Join-Path $FaDir 'mk\extra.mk'
$cfgLog = Join-Path $FaDir 'config.log'

function Get-MkVar([string]$name) {
    # [ \t]*, never \s*: in .NET \s matches the newline too, so on an empty
    # assignment ("NOINSTALL = ") a \s*(.*) pattern runs on into the NEXT line
    # and returns its value instead of the empty string it should.
    if (-not (Test-Path $extraMk)) { return '' }
    $m = [regex]::Matches((Read-TextLf $extraMk), "(?m)^$([regex]::Escape($name))[ \t]*\??=[ \t]*(.*)$")
    if ($m.Count -eq 0) { return '' }
    return $m[$m.Count - 1].Groups[1].Value.Trim()
}
function Get-CfgVar([string]$name) {
    if (-not (Test-Path $cfgLog)) { return '' }
    $m = [regex]::Matches((Read-TextLf $cfgLog), "(?m)^$([regex]::Escape($name))='(.*)'$")
    if ($m.Count -eq 0) { return '' }
    return $m[$m.Count - 1].Groups[1].Value
}

$makeCmd = $null
foreach ($m in @('make', 'mingw32-make', 'gmake')) {
    if (Get-Command $m -ErrorAction SilentlyContinue) { $makeCmd = $m; break }
}

if (-not (Test-Path $extraMk) -and -not (Test-Path $cfgLog)) {
    Write-Host @"
      FAangband is NOT configured yet (no $extraMk), so it was NOT compiled.
      The tileset is installed into the tree; configure and build to see it.

      In an MSYS2 MinGW64 shell, from $FaDir :
          ./autogen.sh
          ./configure --enable-win --enable-sdl2
          make
      then run: $FaDir\src\faangband.exe

      Re-run this script afterwards and it will do the build for you.
      (A Visual Studio build uses src\win\vs2019 instead and is not driven from
      here -- rebuild it in the IDE after this script has patched the sources.)
"@
    exit 0
}

$noInstall = Get-MkVar 'NOINSTALL'
$enableWin = Get-MkVar 'ENABLEWIN'
$prefix = Get-MkVar 'prefix'
$bindir = Get-MkVar 'bindir'
$dataDir = Get-MkVar 'libdatadir'

if (Test-Path $cfgLog) {
    # Fallback / cross-check. A run-in-place tree is identified by NOINSTALL
    # above, but if extra.mk is missing or was hand-edited, the configure line
    # is the only other record of it -- and installing into such a tree is the
    # one build mistake this project must never make.
    $cfgLine = ([regex]::Matches((Read-TextLf $cfgLog), '(?m)^  \$ (.*configure.*)$') | Select-Object -First 1)
    if ($cfgLine -and $cfgLine.Groups[1].Value -match '--with-no-install') { $noInstall = 'yes' }
    if (-not $prefix) { $prefix = Get-CfgVar 'prefix' }
    if (-not $bindir) {
        # autoconf records these unexpanded -- bindir='${exec_prefix}/bin'.
        $execPrefix = Get-CfgVar 'exec_prefix'
        if (-not $execPrefix) { $execPrefix = '${prefix}' }
        $execPrefix = $execPrefix.Replace('${prefix}', $prefix)
        $bindir = (Get-CfgVar 'bindir').Replace('${exec_prefix}', $execPrefix).Replace('${prefix}', $prefix)
    }
}
if (-not $prefix) { $prefix = '/usr/local' }
if (-not $bindir) { $bindir = "$prefix/bin" }
if (-not $dataDir) { $dataDir = "$prefix/share/faangband" }

# Sets $script:BuiltOk rather than returning it: a PowerShell function returns
# everything it writes to the success stream, so returning a value here would
# swallow make's entire output into the return value instead of showing it.
$script:BuiltOk = $false
function Invoke-Make {
    param([string[]]$MakeArgs = @())
    if (-not $makeCmd) {
        Write-Host '      no make on PATH (install MSYS2/MinGW, or run this from its shell).'
        Write-Host '      The tileset IS installed. Finish the build yourself with:'
        Write-Host ''
        Write-Host ("          make -C `"$FaDir`" " + ($MakeArgs -join ' ')).TrimEnd()
        Write-Host ''
        return
    }
    Write-Host ("      Running: $makeCmd -C `"$FaDir`" " + ($MakeArgs -join ' ')).TrimEnd()
    Write-Host ''
    & $makeCmd -C $FaDir @MakeArgs
    if ($LASTEXITCODE -ne 0) {
        # Never let a compile failure read as an install failure: steps 1-6
        # have already succeeded, and re-running this script (a long tile
        # rebuild) fixes nothing.
        Write-Host ''
        Fail ("the FAangband build failed. The tileset IS installed into $FaDir -- " +
              "fix the build error above and re-run just '$makeCmd -C `"$FaDir`" " + ($MakeArgs -join ' ') + "', not .\install.ps1.")
    }
    $script:BuiltOk = $true
}

# $IsWindows exists only in PowerShell 6+; $env:OS is set on every Windows host
# back to 5.1, which is the floor this script supports.
$exeSuffix = if ($env:OS -eq 'Windows_NT') { '.exe' } else { '' }
# A --enable-win build IS the frontend (main-win.c draws the tiles itself), so
# it takes no -m flag; anything else here is the SDL2 frontend.
$frontend = if ($enableWin -eq 'yes') { '' } else { ' -msdl2' }

if ($noInstall -eq 'yes' -or $enableWin -eq 'yes') {
    Write-Detail 'Build mode: run in place (no install step).'
    Invoke-Make
    $runCmd = "`"$FaDir\src\faangband$exeSuffix`"$frontend"
    $note = @"
This build mode reads tiles straight out of $TilesDir\.
  A shortcut or a faangband.exe somewhere else may be a separately INSTALLED
  copy reading different data -- it will not show these tiles. Point it at
  $FaDir\src\faangband$exeSuffix instead.
"@
} elseif ($prefix -eq '/usr/local') {
    Write-Detail "Build mode: install into $prefix, which needs root to deploy."
    Write-Detail 'Compiling only.'
    Invoke-Make
    $runCmd = "faangband$exeSuffix$frontend"
    $note = @"
The tiles are NOT deployed yet -- '$prefix' needs root. Finish with:

      sudo make -C "$FaDir" install
"@
} else {
    Write-Detail "Build mode: install into $prefix."
    Invoke-Make @('install')
    $runCmd = "faangband$exeSuffix$frontend"
    $note = @"
Tiles and gamedata are deployed to $dataDir, the binary to $bindir/.
  If that directory is not on your PATH, run "$bindir/faangband$exeSuffix"$frontend instead.
"@
}

if ($script:BuiltOk) {
    Write-Host @"

Done. Run the game with:

    $runCmd

  $note
  Tiles are off until you switch them on: start or load a character first, then
  use the game window's own menu bar -- Menu > FAangband > Tiles > Set > Hither
  Lands. They never render in the curses frontend (-mgcu).
"@
}
