# matiec fuer Windows bauen und paketieren (matiec-pin.json).
#
#   powershell -ExecutionPolicy Bypass -File tools/windows/build_matiec.ps1 -Out dist\matiec
#
# Dieselbe Strategie wie bei gappa, und aus demselben Grund: die devShell baut
# matiec auf Linux und macOS selbst (flake.nix packages.matiec), auf Windows gab
# es nichts. OpenPLC liefert zwar ein matiec fuer Windows mit - das war der
# Hinweis, dass es dort baut - aber dessen Binaerdatei zu uebernehmen hiesse,
# einen ANDEREN Uebersetzer zu fahren als auf den anderen Plattformen.
#
# Werkzeugspezifisch ist hier nur: welche Quelle, welcher Compileraufruf, welche
# Rauchprobe, und was ins Paket gehoert (anders als gappa ist das nicht nur eine
# Binaerdatei, sondern iec2c.exe PLUS lib/). Alles, was nicht abweichen darf,
# kommt aus win_package.ps1.
#
# Laeuft unter Windows PowerShell 5.1.
param(
    [string]$Out = "dist\matiec",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "win_package.ps1")

$root = (Resolve-Path (Join-Path $here "..\..")).Path
$pin  = Get-Content (Join-Path $root "matiec-pin.json") -Raw | ConvertFrom-Json
$b    = $pin.windows_build

$rev     = $pin.revision
$kurz    = $rev.Substring(0,7)
$srcName = ($pin.source.PSObject.Properties | Select-Object -First 1).Name
$srcMeta = $pin.source.$srcName
$msys    = "C:\msys64"
$bash    = Join-Path $msys "usr\bin\bash.exe"
# Version zuerst, Revision dahinter. matiec meldet fuer jede Revision dieselbe
# Version (0.1), also benennt sie allein kein Paket eindeutig.
$base    = "matiec-$($pin.version)-$kurz-win_amd64"

Write-Output "[matiec] Pin: Revision $kurz, Upstream-Projekt $($pin.upstream_project)"
if (-not (Test-Path $bash)) {
    throw "MSYS2 fehlt ($bash). tools/windows/provision.ps1 installiert es aus deps.winget.json."
}

Write-Output "[1/7] pacman aus deps.msys2.txt"
Install-MsysPackages -Bash $bash -ListFile (Join-Path $here "deps.msys2.txt")

Write-Output "[2/7] Quelle: $srcName"
$work = Join-Path $root "build\matiec"
$tar  = Get-PinnedSource -SrcMeta $srcMeta -Name $srcName -WorkDir $work

Write-Output "[3/7] autoreconf + configure + make (MSYSTEM=MINGW64)"
Invoke-Native { & $bash (ConvertTo-MsysPath (Join-Path $here "build_matiec.sh")) `
                        (ConvertTo-MsysPath $tar) ((ConvertTo-MsysPath $work) + "/tree") } |
    ForEach-Object { Write-Output "       $_" }
if ($LASTEXITCODE -ne 0) { throw "build_matiec.sh exit $LASTEXITCODE" }

$tree = (Get-ChildItem (Join-Path $work "tree") -Directory | Select-Object -First 1).FullName
$exe  = Join-Path $tree $b.payload.binary
if (-not (Test-Path $exe)) { throw "$($b.payload.binary) fehlt nach dem Bau" }

Write-Output "[4/7] zusammenstellen"
$stage = Join-Path $root "$Out\stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item $exe $stage
# Anders als bei gappa ist die Binaerdatei nicht das ganze Werkzeug: MATIEC_DIR
# muss lib/ieclib.txt enthalten, sonst uebersetzt iec2c keine Standardfunktion.
Copy-Item (Join-Path $tree $b.payload.data_dir) (Join-Path $stage $b.payload.data_dir) -Recurse
if (-not (Test-Path (Join-Path $stage "$($b.payload.data_dir)\ieclib.txt"))) {
    throw "lib/ieclib.txt fehlt im Paket - MATIEC_DIR waere unbrauchbar"
}

$linked = Get-Content (Join-Path $work "tree\dlls.txt") | Where-Object { $_.Trim() }
$prov   = Get-DllProvenance -Bash $bash -ProbeScript (Join-Path $here "provenance.sh") -Dlls $linked
Copy-RuntimeDlls -Linked $linked -Declared $b.runtime_dlls -Prov $prov -MsysRoot $msys -Stage $stage

Write-Output "[5/7] Lizenztexte und Herkunftsnachweis"
Copy-LicenceTexts -Build $b -Stage $stage -SourceTree $tree `
                  -RepoLicenceDir (Join-Path $here "licenses") -MsysRoot $msys
Write-NoticeAndSources -Pin $pin -Prov $prov -Stage $stage -ToolName "matiec" `
    -Bezeichnung "matiec $($pin.version) ($kurz)" -SrcMeta $srcMeta `
    -Rezept "tools/windows/build_matiec.ps1 und tools/windows/build_matiec.sh"

Write-Output "[6/7] Rauchtest (aus dem Paket heraus, ohne MSYS2 im PATH)"
$smoke = Join-Path $here "matiec-smoke"
$probe = Join-Path $root "$Out\smoke"
if (Test-Path $probe) { Remove-Item $probe -Recurse -Force }
New-Item -ItemType Directory -Force -Path $probe | Out-Null
$staged = Join-Path $stage $b.payload.binary
$env:PATH = "$env:SystemRoot\system32;$env:SystemRoot"

# NICHT $out nennen: PowerShell-Variablennamen unterscheiden keine Gross- und
# Kleinschreibung, und $Out ist der Parameter mit dem Ausgabeverzeichnis. Der
# erste Lauf ueberschrieb ihn mit der Uebersetzerausgabe und suchte danach ein
# Zip unter C:\...\POUS.c - der Fehler erschien erst eine Stufe spaeter.
$iecOut = Invoke-Native { & $staged "-I" (Join-Path $stage $b.payload.data_dir) "-T" $probe (Join-Path $smoke "counter.st") } | Out-String
if ($LASTEXITCODE -ne 0) { throw "counter.st haette uebersetzen muessen, exit $LASTEXITCODE`n$iecOut" }
# Der Exitcode allein waere zu wenig: ein Uebersetzer, der nichts schreibt,
# meldet auch 0. Also die ERZEUGTEN Dateien pruefen.
foreach ($f in @("POUS.c", "POUS.h", "LOCATED_VARIABLES.h", "VARIABLES.csv",
                 "Config0.c", "Config0.h", "Res0.c")) {
    if (-not (Test-Path (Join-Path $probe $f))) { throw "iec2c erzeugte $f nicht" }
}
$pous = Get-Content (Join-Path $probe "POUS.c") -Raw
if ($pous -notmatch "PROG0") { throw "POUS.c enthaelt das uebersetzte Programm nicht" }
Write-Output "       counter.st -> 7 Dateien, POUS.c traegt PROG0"

Write-Output "[7/7] packen"
$outDir = Join-Path $root $Out
New-ToolPackage -Stage $stage -OutDir $outDir -BaseName $base `
    -SourceTarball $tar -SourceName $srcName `
    -IssFile (Join-Path $here "tool.iss") `
    -IssDefines @{ ToolName = "matiec"; ToolVersion = "$($pin.version).$kurz"; BaseName = $base
                   ToolId = "{{2E5C8A41-6D3F-4B92-A7C0-1F84D9E35B62}"
                   StageDir = $stage; OutDir = $outDir } `
    -SkipInstaller:$SkipInstaller
Write-Output "[matiec] fertig in $outDir"
