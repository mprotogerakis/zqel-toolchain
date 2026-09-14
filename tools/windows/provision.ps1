# Eine Windows-Baumaschine aus dem Manifest herrichten (#317).
#
#   powershell -ExecutionPolicy Bypass -File tools/windows/provision.ps1
#   powershell -ExecutionPolicy Bypass -File tools/windows/provision.ps1 -VerifyOnly
#
# `deps.winget.json` ist die EINE Stelle, an der steht, was diese Plattform
# braucht. Dieses Skript wendet es an — es fuehrt keine eigene Liste.
#
# Was es NICHT installiert: Z3. Das steht in requirements.txt, per Artefakt-Hash
# gepinnt, und gilt dort plattformunabhaengig. Es hier zu wiederholen hiesse,
# zwei Stellen zu pflegen, an denen ein Hash stehen muss.
param([switch]$VerifyOnly)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifest = Join-Path $here "deps.winget.json"

if (-not $VerifyOnly) {
    Write-Output "[1/3] Pakete aus dem Manifest"
    winget import --import-file $manifest --accept-source-agreements --accept-package-agreements --ignore-versions

    # PowerShell 7 steht bewusst NICHT im Manifest: winget antwortet auf
    # --scope machine mit "No applicable installer found" (gemessen
    # 2026-09-13). Ins Benutzerprofil installiert nuetzt es nichts, denn der
    # Runner-Dienst laeuft als NT AUTHORITY\SYSTEM. Also das MSI direkt.
    if (-not (Test-Path "C:\Program Files\PowerShell\7\pwsh.exe")) {
        Write-Output "      PowerShell 7 per MSI (winget kann es nicht maschinenweit)"
        $msi = Join-Path $env:TEMP "pwsh-7.msi"
        $rel = Invoke-RestMethod -UseBasicParsing -Headers @{ "User-Agent" = "zqel" } `
                 -Uri "https://api.github.com/repos/PowerShell/PowerShell/releases/latest"
        $asset = $rel.assets | Where-Object { $_.name -like "PowerShell-*-win-x64.msi" } | Select-Object -First 1
        Write-Output ("      " + $asset.name)
        Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $msi
        Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /quiet /norestart ADD_PATH=1" -Wait
    }
}

Write-Output "[2/3] Die interne Root-CA"
# Ohne sie erreicht die Maschine den forgejo-Server nicht — und `winget`
# scheitert an der msstore-Quelle. Gemessen beim Onboarding am 2026-09-13.
$ca = Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Subject -like "*root-ca-fb3-auto*" }
if ($ca) {
    Write-Output ("  vorhanden: " + $ca[0].Thumbprint)
} else {
    Write-Warning "  FEHLT - ohne sie ist der forgejo-Server nicht erreichbar."
}

Write-Output "[3/3] Pruefen, was der Build wirklich braucht"
# WER hier prueft, ist der ganze Punkt. Dieses Skript laeuft meist als
# Administrator, der Runner-Dienst aber als NT AUTHORITY\SYSTEM. Ein Werkzeug
# im Benutzerprofil beantwortet `Get-Command` hier freundlich und existiert
# fuer den Runner trotzdem nicht. Genau so gingen zwei Nightly-Laeufe verloren:
# `winget list` zeigte pwsh an, der Build meldete "Cannot find: pwsh in PATH".
# Deshalb gilt ein Fund unter C:\Users\ als NICHT vorhanden.
$missing = New-Object System.Collections.ArrayList
foreach ($tool in @("git", "python", "pwsh")) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if (-not $cmd) {
        [void]$missing.Add($tool)
    } elseif ($cmd.Source -like "$env:SystemDrive\Users\*") {
        Write-Output ("  " + $tool + ": " + $cmd.Source)
        Write-Warning ("  ^ liegt im Benutzerprofil - der Runner laeuft als SYSTEM und sieht das nicht.")
        [void]$missing.Add($tool + " (nur im Benutzerprofil)")
    } else {
        Write-Output ("  " + $tool + ": " + $cmd.Source)
    }
}

# Der C-Compiler liegt nicht im PATH, sondern hinter vcvarsall.bat.
$pf86 = [Environment]::GetFolderPath("ProgramFilesX86")
$vswhere = Join-Path $pf86 "Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $vc = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($vc) { Write-Output ("  MSVC: " + $vc) } else { [void]$missing.Add("MSVC VC.Tools") }
} else {
    [void]$missing.Add("Visual Studio Installer")
}

# Was der gappa-Bau braucht (gappa-pin.json). Nicht im PATH, deshalb je ein
# fester Ort. Fehlt es, scheitert der Bau sonst erst nach dem Download.
$msysBash = "C:\msys64\usr\bin\bash.exe"
if (Test-Path $msysBash) { Write-Output ("  MSYS2: " + $msysBash) } else { [void]$missing.Add("MSYS2") }

$iscc = @(
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    (Join-Path $pf86 "Inno Setup 6\ISCC.exe")
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) { Write-Output ("  Inno Setup: " + $iscc) } else { [void]$missing.Add("Inno Setup 6") }

if ($missing.Count -gt 0) {
    Write-Error ("fehlt: " + ($missing -join ", "))
    exit 1
}
Write-Output "bereit."
