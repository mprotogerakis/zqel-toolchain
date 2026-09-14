# Gappa fuer Windows bauen und paketieren (gappa-pin.json).
#
#   powershell -ExecutionPolicy Bypass -File tools/windows/build_gappa.ps1 -Out dist\gappa
#
# Windows ist die einzige Plattform, auf der die devShell kein gappa liefert
# (gemessen 2026-09-13: Linux und macOS aarch64 haben `gappa 1.4.0` auf dem
# PATH), und es gibt dort auch nichts Fertiges - MSYS2 kennt 15725 Pakete und
# kein gappa, Upstream veroeffentlicht nur Quell-Tarballs.
#
# Was hier steht, ist der WERKZEUGSPEZIFISCHE Teil: welche Quelle, welcher
# Compileraufruf, welche Rauchprobe. Alles, was nicht abweichen darf - DLLs
# gegen den Pin, Lizenztexte, Herkunftsnachweis, Paket und Installer - kommt aus
# win_package.ps1.
#
# Laeuft unter Windows PowerShell 5.1; der Workflow ruft es so auf.
param(
    [string]$Out = "dist\gappa",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "win_package.ps1")

$root = (Resolve-Path (Join-Path $here "..\..")).Path
$pin  = Get-Content (Join-Path $root "gappa-pin.json") -Raw | ConvertFrom-Json
$b    = $pin.windows_build

$version = $pin.version
$srcName = ($pin.source.PSObject.Properties | Select-Object -First 1).Name
$srcMeta = $pin.source.$srcName
$msys    = "C:\msys64"
$bash    = Join-Path $msys "usr\bin\bash.exe"
$base    = "gappa-$version-win_amd64"

Write-Output "[gappa] Pin: $version ($($pin.upstream_tag)), Upstream-Projekt $($pin.upstream_project)"
if (-not (Test-Path $bash)) {
    throw "MSYS2 fehlt ($bash). tools/windows/provision.ps1 installiert es aus deps.winget.json."
}

Write-Output "[1/7] pacman aus deps.msys2.txt"
Install-MsysPackages -Bash $bash -ListFile (Join-Path $here "deps.msys2.txt")

Write-Output "[2/7] Quelle: $srcName"
$work = Join-Path $root "build\gappa"
$tar  = Get-PinnedSource -SrcMeta $srcMeta -Name $srcName -WorkDir $work

Write-Output "[3/7] configure + remake (MSYSTEM=MINGW64)"
Invoke-Native { & $bash (ConvertTo-MsysPath (Join-Path $here "build_gappa.sh")) `
                        (ConvertTo-MsysPath $tar) ((ConvertTo-MsysPath $work) + "/tree") } |
    ForEach-Object { Write-Output "       $_" }
if ($LASTEXITCODE -ne 0) { throw "build_gappa.sh exit $LASTEXITCODE" }

$tree = (Get-ChildItem (Join-Path $work "tree") -Directory | Select-Object -First 1).FullName
$exe  = Join-Path $tree "src\gappa.exe"
if (-not (Test-Path $exe)) { throw "gappa.exe fehlt nach dem Bau" }

Write-Output "[4/7] zusammenstellen"
$stage = Join-Path $root "$Out\stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item $exe $stage

$linked = Get-Content (Join-Path $work "tree\dlls.txt") | Where-Object { $_.Trim() }
$prov   = Get-DllProvenance -Bash $bash -ProbeScript (Join-Path $here "provenance.sh") -Dlls $linked
Copy-RuntimeDlls -Linked $linked -Declared $b.runtime_dlls -Prov $prov -MsysRoot $msys -Stage $stage

Write-Output "[5/7] Lizenztexte und Herkunftsnachweis"
Copy-LicenceTexts -Build $b -Stage $stage -SourceTree $tree `
                  -RepoLicenceDir (Join-Path $here "licenses") -MsysRoot $msys
Write-NoticeAndSources -Pin $pin -Prov $prov -Stage $stage -ToolName "Gappa" `
    -Bezeichnung "Gappa $version" -SrcMeta $srcMeta `
    -Rezept "tools/windows/build_gappa.ps1 und tools/windows/build_gappa.sh"

Write-Output "[6/7] Rauchtest (aus dem Paket heraus, ohne MSYS2 im PATH)"
# Die Probe faehrt GEGEN DAS PAKET, nicht gegen den Bauplatz, und mit nacktem
# PATH - sonst prueft sie die Baumaschine statt das Ergebnis.
$smoke  = Join-Path $here "gappa-smoke"
$staged = Join-Path $stage "gappa.exe"
$env:PATH = "$env:SystemRoot\system32;$env:SystemRoot"

$holdsOut = Invoke-Native { & $staged (Join-Path $smoke "holds.g") } | Out-String
if ($LASTEXITCODE -ne 0) { throw "holds.g haette gelingen muessen, exit $LASTEXITCODE`n$holdsOut" }
Write-Output "       holds.g  exit 0"
# Ein Rauchtest, der nur das Gelingen prueft, wuerde auch `exit 0` bestehen.
$errOut = Invoke-Native { & $staged (Join-Path $smoke "fails.g") } | Out-String
if ($LASTEXITCODE -ne 1) { throw "fails.g haette scheitern muessen, exit $LASTEXITCODE" }
if ($errOut -notmatch [regex]::Escape("BND(|x - x_|)")) {
    throw "fails.g scheiterte, nannte aber nicht die Schranke. Ausgabe:`n$errOut"
}
Write-Output "       fails.g  exit 1, Schranke genannt"
$ver = Invoke-Native { & $staged --version } | Out-String
if ($ver -notmatch [regex]::Escape($version)) { throw "--version meldet '$($ver.Trim())', erwartet $version" }
Write-Output "       --version $($ver.Trim())"

Write-Output "[7/7] packen"
$outDir = Join-Path $root $Out
New-ToolPackage -Stage $stage -OutDir $outDir -BaseName $base `
    -SourceTarball $tar -SourceName $srcName `
    -IssFile (Join-Path $here "tool.iss") `
    -IssDefines @{ ToolName = "Gappa"; ToolVersion = $version; BaseName = $base
                   ToolId = "{{7B3F1C4E-9A52-4D77-8E31-6C0A2F5B41D9}"
                   StageDir = $stage; OutDir = $outDir } `
    -SkipInstaller:$SkipInstaller
Write-Output "[gappa] fertig in $outDir"
