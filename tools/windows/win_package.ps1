# Der gemeinsame Teil der Windows-Pakete (gappa, matiec, ...).
#
# Dot-sourcen, nicht aufrufen:
#     . (Join-Path $PSScriptRoot "win_package.ps1")
#
# WARUM ES DIESE DATEI GIBT:
# Der werkzeugspezifische Teil ist klein - eine Quelle holen, einen Compiler
# rufen, eine Rauchprobe fahren. Der Teil, der NICHT abweichen darf, ist gross:
# welche DLLs mitfahren duerfen, ob ihre Lizenz noch dieselbe ist, welche Texte
# beiliegen muessen, was im Herkunftsnachweis steht. Zwei Kopien davon waeren
# zwei Autoritaeten, und die eine wuerde irgendwann ein Paket ausliefern, dessen
# Lizenzhinweis nicht mehr stimmt.
#
# Laeuft unter Windows PowerShell 5.1.
#
# FORTSCHRITT GEHT UEBER Write-Host, NICHT Write-Output:
# In PowerShell ist der Ausgabestrom auch der Rueckgabewert. Eine Funktion, die
# ihren Fortschritt mit Write-Output meldet UND einen Pfad zurueckgibt, liefert
# dem Aufrufer ein Array aus beidem. Genau daran ist der erste Lauf dieses
# Moduls gescheitert ("Cannot convert value to type System.String"), und zwar
# erst zwei Stufen spaeter - der Fehler sah aus wie ein Pfadproblem.

# "Stop" macht aus JEDER Zeile, die ein fremdes Programm nach stderr schreibt,
# einen Abbruch. Das ist hier falsch: pacman meldet "up to date -- skipping"
# dorthin, und eine Rauchprobe BRAUCHT unter Umstaenden ein Werkzeug, das
# scheitert. Native Aufrufe laufen deshalb hierdurch, und ihr Urteil ist der
# Rueckgabewert, nicht der Kanal.
function Invoke-Native {
    param([Parameter(Mandatory)][scriptblock]$Block)
    $vorher = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Block 2>&1 } finally { $ErrorActionPreference = $vorher }
}

function ConvertTo-MsysPath {
    param([Parameter(Mandatory)][string]$Path)
    $p = (Resolve-Path $Path).Path
    return "/" + $p.Substring(0,1).ToLower() + ($p.Substring(2) -replace '\\','/')
}

function Install-MsysPackages {
    param([Parameter(Mandatory)][string]$Bash,
          [Parameter(Mandatory)][string]$ListFile)
    $pkgs = Get-Content $ListFile |
            Where-Object { $_.Trim() -and -not $_.StartsWith("#") } |
            ForEach-Object { $_.Trim() }
    Write-Host ("       " + ($pkgs -join " "))
    Invoke-Native { & $Bash -lc ("pacman -S --needed --noconfirm " + ($pkgs -join " ")) } |
        Select-Object -Last 3 | ForEach-Object { Write-Host "       $_" }
    if ($LASTEXITCODE -ne 0) { throw "pacman exit $LASTEXITCODE" }

    # Und jetzt gegen den Lock. Bis zum 2026-09-13 hat der Bau die Versionen
    # nur gemessen und berichtet - ehrlich, aber nicht reproduzierbar: ein
    # spaeterer `pacman -Syu` baut unter demselben Rezept mit anderen
    # Bibliotheken, und der Bau meldet es nur, statt anzuhalten.
    # Eine neue Baseline ist eine Entscheidung, kein Nebeneffekt.
    $lock = Join-Path (Split-Path $ListFile -Parent) "msys2_lock.py"
    Invoke-Native { & python $lock verify } | ForEach-Object { Write-Host "     $_" }
    if ($LASTEXITCODE -ne 0) {
        throw "MSYS2 weicht vom Lock ab (tools/windows/msys2.lock.json)"
    }
}

function Get-PinnedSource {
    <#  Holt die Quelle und prueft sie gegen den Pin. Ein Downloader, der den
        Hash nur ausrechnet, prueft nichts - deshalb faellt eine abweichende
        Datei weg, statt beim naechsten Lauf als "schon da" zu gelten. #>
    param([Parameter(Mandatory)]$SrcMeta,
          [Parameter(Mandatory)][string]$Name,
          [Parameter(Mandatory)][string]$WorkDir)
    New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
    $tar = Join-Path $WorkDir $Name
    if (-not (Test-Path $tar)) {
        Invoke-WebRequest -Uri $SrcMeta.url -OutFile $tar -UseBasicParsing
    }
    $got = (Get-FileHash $tar -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $SrcMeta.sha256) {
        Remove-Item $tar -Force
        throw "Hash weicht ab.`n  erwartet: $($SrcMeta.sha256)`n  bekommen: $got`nDas ist entweder eine neu hochgeladene Quelle oder etwas Schlimmeres. Der Pin entscheidet, nicht der Server."
    }
    Write-Host "       sha256 stimmt, $((Get-Item $tar).Length) Bytes"
    return $tar
}

function Get-DllProvenance {
    <#  Woher jede DLL stammt - aus der Paketdatenbank der Maschine, die gerade
        baut, nicht aus einer gepflegten Liste. #>
    param([Parameter(Mandatory)][string]$Bash,
          [Parameter(Mandatory)][string]$ProbeScript,
          [Parameter(Mandatory)][string[]]$Dlls)
    $lines = Invoke-Native { & $Bash (ConvertTo-MsysPath $ProbeScript) $Dlls }
    if ($LASTEXITCODE -ne 0) { throw "gappa_provenance.sh exit $LASTEXITCODE" }
    $prov = @{}
    foreach ($line in $lines) {
        $f = ([string]$line).Trim() -split '\|'
        if ($f.Count -ge 5) {
            $prov[$f[0]] = @{ paket = $f[1]; version = $f[2]; lizenzen = $f[3]; url = $f[4] }
        }
    }
    return $prov
}

function Copy-RuntimeDlls {
    <#  Kopiert genau die DLLs, die der Linker zieht - und bricht ab, wenn das
        eine andere Menge ist als der Pin nennt oder wenn sich eine LIZENZ
        geaendert hat. Eine neue Paketversion ist normal; eine andere Lizenz
        macht den beiliegenden Hinweis falsch, und das ist kein Bau-, sondern
        ein Verteilungsproblem. #>
    param([Parameter(Mandatory)][string[]]$Linked,
          [Parameter(Mandatory)]$Declared,
          [Parameter(Mandatory)][hashtable]$Prov,
          [Parameter(Mandatory)][string]$MsysRoot,
          [Parameter(Mandatory)][string]$Stage)
    $wanted = @($Declared.PSObject.Properties.Name) | Sort-Object
    $diff = Compare-Object $wanted ($Linked | Sort-Object -Unique)
    if ($diff) {
        $diff | ForEach-Object { Write-Host ("       " + $_.SideIndicator + " " + $_.InputObject) }
        throw "Der Linker zieht andere DLLs als der Pin nennt. Eine still gewachsene Abhaengigkeit ist eine unbemerkte Auslieferungsluecke - und eine, deren Lizenz niemand genannt hat. Erst den Pin fortschreiben, dann bauen."
    }
    foreach ($d in ($Linked | Sort-Object -Unique)) {
        if (-not $Prov.ContainsKey($d)) { throw "Keine Herkunft fuer $d ermittelbar" }
        $decl = $Declared.$d
        $m = $Prov[$d]
        if ($m.lizenzen -ne $decl.msys2_licenses) {
            throw "Lizenz von $d hat sich geaendert.`n  Pin:      $($decl.msys2_licenses)`n  gemessen: $($m.lizenzen)`nDas ist kein Bau-, sondern ein Verteilungsproblem: der beiliegende Hinweis waere falsch."
        }
        if ($m.paket -ne $decl.msys2_package) {
            throw "$d kommt jetzt aus $($m.paket), der Pin nennt $($decl.msys2_package)"
        }
        Copy-Item (Join-Path $MsysRoot "mingw64\bin\$d") $Stage
        Write-Host ("       {0,-22} {1} {2}" -f $d, $m.paket, $m.version)
    }
}

function Copy-LicenceTexts {
    <#  Jeder genannte Text hat genau eine Herkunft: der Quellbaum des Werkzeugs,
        das Repo (beigelegt, hashgeprueft) oder das MSYS2-Paket, aus dem die DLL
        stammt. Ein vierter Fall waere eine Datei, die beim Bau aus dem Nichts
        kommt. Am Ende wird gegengeprueft, dass wirklich jeder da ist. #>
    param([Parameter(Mandatory)]$Build,
          [Parameter(Mandatory)][string]$Stage,
          [Parameter(Mandatory)][string]$SourceTree,
          [Parameter(Mandatory)][string]$RepoLicenceDir,
          [Parameter(Mandatory)][string]$MsysRoot)
    $lic = Join-Path $Stage "licenses"
    New-Item -ItemType Directory -Force -Path $lic | Out-Null

    $toolDir = Join-Path $lic "tool"
    New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
    foreach ($rel in $Build.tool_licence.files_from_source_tree) {
        $ziel = Join-Path $toolDir (Split-Path $rel -Leaf)
        Copy-Item (Join-Path $SourceTree $rel) $ziel
    }
    # Der erste Text zusaetzlich obenauf: der Installer zeigt ihn als Lizenzseite.
    $erster = @($Build.tool_licence.files_from_source_tree)[0]
    Copy-Item (Join-Path $SourceTree $erster) (Join-Path $Stage "COPYING")

    foreach ($p in $Build.vendored_licence_texts.PSObject.Properties) {
        $srcFile = Join-Path $RepoLicenceDir $p.Name
        if (-not (Test-Path $srcFile)) { throw "beigelegter Lizenztext fehlt: $($p.Name)" }
        $h = (Get-FileHash $srcFile -Algorithm SHA256).Hash.ToLower()
        if ($h -ne $p.Value.sha256) {
            throw "Lizenztext $($p.Name) weicht vom Pin ab.`n  erwartet: $($p.Value.sha256)`n  gefunden: $h"
        }
        Copy-Item $srcFile (Join-Path $lic $p.Name)
    }

    $benoetigt = @()
    foreach ($p in $Build.runtime_dlls.PSObject.Properties) { $benoetigt += @($p.Value.licence_files) }
    foreach ($rel in ($benoetigt | Sort-Object -Unique)) {
        $ziel = Join-Path $lic $rel
        if (Test-Path $ziel) { continue }
        $teile = $rel -split '/'
        if ($teile.Count -ne 2) { throw "unbekannter Lizenzpfad im Pin: $rel" }
        $von = Join-Path $MsysRoot ("mingw64\share\licenses\" + $teile[0] + "\" + $teile[1])
        if (-not (Test-Path $von)) {
            throw "MSYS2 legt $rel nicht ab, und der Pin nennt keinen beigelegten Ersatz. Ohne den Text darf das Paket nicht ausgeliefert werden."
        }
        New-Item -ItemType Directory -Force -Path (Split-Path $ziel -Parent) | Out-Null
        Copy-Item $von $ziel
    }
    foreach ($rel in ($benoetigt | Sort-Object -Unique)) {
        if (-not (Test-Path (Join-Path $lic $rel))) { throw "Lizenztext fehlt im Paket: $rel" }
    }
    Write-Host ("       " + (Get-ChildItem $lic -Recurse -File).Count + " Lizenzdateien")
}

function Write-NoticeAndSources {
    <#  Beide Texte entstehen aus DERSELBEN Liste wie die kopierten Dateien.
        Zwei Listen hiessen: eine DLL kann mitfahren, ohne genannt zu werden -
        und genannt werden ist hier die Auflage, nicht die Hoeflichkeit. #>
    param([Parameter(Mandatory)]$Pin,
          [Parameter(Mandatory)][hashtable]$Prov,
          [Parameter(Mandatory)][string]$Stage,
          [Parameter(Mandatory)][string]$ToolName,
          [Parameter(Mandatory)][string]$Bezeichnung,
          [Parameter(Mandatory)]$SrcMeta,
          [Parameter(Mandatory)][string]$Rezept)
    $b = $Pin.windows_build
    $zeilen = @()
    $quellen = @()
    foreach ($p in $b.runtime_dlls.PSObject.Properties) {
        $m = $Prov[$p.Name]
        $zeilen += ("  {0,-20} {1,-24} {2}" -f $p.Name, $p.Value.library, $m.lizenzen)
        $zeilen += ("  {0,-20} aus {1} {2}" -f "", $m.paket, $m.version)
        $zeilen += ("  {0,-20} Texte: {1}" -f "", (@($p.Value.licence_files) -join ", "))
        $quellen += ("  " + $p.Name)
        $quellen += ("    MSYS2-Paket:   " + $m.paket + " " + $m.version)
        $quellen += ("    Bauanleitung:  https://github.com/msys2/MINGW-packages/tree/master/" + $m.paket)
        $quellen += ("    Upstream:      " + $m.url)
        $quellen += ("    Quelle holen:  pacman -S --downloadonly " + $m.paket + "   (MSYS2), oder vom Upstream")
        $quellen += ""
    }
    $dllZeilen = $zeilen -join "`r`n"
    $texte = (@($b.tool_licence.files_from_source_tree) | ForEach-Object { "licenses\tool\" + (Split-Path $_ -Leaf) }) -join ", "

    $notice = @"
$Bezeichnung fuer Windows x86_64

DIESES PROGRAMM
  $ToolName steht unter $($b.tool_licence.spdx).
  Die Lizenztexte liegen bei: $texte
  Die Lizenzseite des Installers zeigt COPYING.

  Uebersetzt aus:  $($SrcMeta.url)
  sha256:          $($SrcMeta.sha256)
  Upstream:        $($Pin.upstream_project)
  Die Quelle liegt unveraendert neben diesem Paket.

BEILIEGENDE BIBLIOTHEKEN, dynamisch gelinkt
$dllZeilen

  Sie liegen bei und sind NICHT einkompiliert. Das ist der Grund, warum dieses
  Paket DLLs mitbringt statt eines einzelnen Binaries: die LGPL verlangt, dass
  sich die Bibliotheken austauschen lassen. Das geht hier, indem die DLL im
  Installationsverzeichnis durch eine schnittstellenkompatible ersetzt wird.

  Gebaut wurden sie nicht von uns. Sie stammen als fertige Pakete aus MSYS2;
  woher ihr Quellcode zu beziehen ist, steht in SOURCES.txt.

INSTALLER
  Erzeugt mit Inno Setup (https://jrsoftware.org/isinfo.php).

Alle Lizenztexte: das Verzeichnis licenses\ neben dieser Datei.
"@
    Set-Content -Path (Join-Path $Stage "NOTICE.txt") -Value $notice -Encoding ascii

    $sources = @"
Woher der uebersetzte Quellcode stammt
======================================

Gebaut am $(Get-Date -Format "yyyy-MM-dd") auf einer MSYS2/MINGW64-Maschine.

$($Bezeichnung.ToUpper()) - der Teil, den WIR uebersetzt haben
  Quelle:   $($SrcMeta.url)
  sha256:   $($SrcMeta.sha256)
  Groesse:  $($SrcMeta.size) Bytes
  Upstream: $($Pin.upstream_project)

  Unveraendert uebersetzt - wir tragen keine Patches. Die Bauanleitung ist
  oeffentlich: $Rezept im zqel-Repository.

  Dieselbe Quelle liegt in derselben Paketversion neben diesem Paket, damit
  Quelle und Binaerdatei nicht auf verschiedenen Servern liegen.

BEILIEGENDE BIBLIOTHEKEN - von uns NICHT uebersetzt, nur weitergegeben
$($quellen -join "`r`n")
Die Versionsangaben oben sind zum Bauzeitpunkt GEMESSEN, nicht gepflegt.
"@
    Set-Content -Path (Join-Path $Stage "SOURCES.txt") -Value $sources -Encoding ascii

    # PIN.txt gehoert dazu und nicht in die einzelnen Bauskripte: sonst sagt das
    # eine Paket, woran es gebunden ist, und das andere vergisst es.
    $kennung = if ($Pin.PSObject.Properties.Name -contains "version") {
        "version             " + $Pin.version
    } else {
        "revision            " + $Pin.revision
    }
    $pinTxt = @"
$Bezeichnung
$kennung
upstream_project    $($Pin.upstream_project)
quelle_sha256       $($SrcMeta.sha256)
gebaut_am           $(Get-Date -Format "yyyy-MM-dd")
toolchain           $($b.toolchain)
link                $($b.link)

Gebunden ist diese Fassung an das, was die devShell fuehrt - nicht an die
neueste. Der Pin im Repository sagt warum.
Lizenzen: NOTICE.txt und licenses\. Herkunft des Quellcodes: SOURCES.txt.
"@
    Set-Content -Path (Join-Path $Stage "PIN.txt") -Value $pinTxt -Encoding ascii
}

function New-ToolPackage {
    <#  Zip, Quelle daneben, Installer - und je eine sha256-Datei. #>
    param([Parameter(Mandatory)][string]$Stage,
          [Parameter(Mandatory)][string]$OutDir,
          [Parameter(Mandatory)][string]$BaseName,
          [Parameter(Mandatory)][string]$SourceTarball,
          [Parameter(Mandatory)][string]$SourceName,
          [Parameter(Mandatory)][string]$IssFile,
          [Parameter(Mandatory)][hashtable]$IssDefines,
          [switch]$SkipInstaller)

    $zip = Join-Path $OutDir "$BaseName.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path "$Stage\*" -DestinationPath $zip
    (Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() + "  " + (Split-Path $zip -Leaf) |
        Set-Content "$zip.sha256" -Encoding ascii
    Write-Host ("       " + (Split-Path $zip -Leaf) + "  " + [math]::Round((Get-Item $zip).Length/1MB,2) + " MB")

    Copy-Item $SourceTarball (Join-Path $OutDir $SourceName) -Force
    (Get-FileHash (Join-Path $OutDir $SourceName) -Algorithm SHA256).Hash.ToLower() + "  " + $SourceName |
        Set-Content (Join-Path $OutDir "$SourceName.sha256") -Encoding ascii
    Write-Host ("       " + $SourceName + "  (Quelle, wandert mit)")

    if ($SkipInstaller) { Write-Host "       Installer uebersprungen"; return }

    $iscc = @(
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        (Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe")
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) {
        throw "ISCC.exe nicht gefunden. Inno Setup steht in deps.winget.json; provision.ps1 installiert es."
    }
    # ISCC.exe ist ein 32-BIT-Programm, und der CI-Bauplatz liegt unter
    # C:\Windows\System32\config\systemprofile\.cache\act\... - dort legt
    # act_runner ihn an, weil der Dienst als SYSTEM laeuft und das SYSTEM-Profil
    # dort steht. Fuer einen 32-Bit-Prozess leitet Windows System32 auf SysWOW64
    # um, und dort gibt es den Bauplatz nicht. PowerShell (64 Bit) sieht die
    # Dateien, ISCC sieht sie nicht.
    #
    # Gemessen am 2026-09-13, mit Gegenprobe: dieselben Dateien, dieselbe
    # Identitaet, derselbe Aufruf.
    #   unter System32 : exit 2, "The system cannot find the path specified"
    #   daneben        : exit 0, "Successful compile"
    # Vier CI-Fahrten hat es gekostet, weil `Test-Path` freundlich True sagte.
    #
    # Deshalb wird die Paketierung ausserhalb von System32 gefahren und das
    # Ergebnis zurueckgeholt.
    $pack = Join-Path $env:SystemDrive ("zqel-pack\" + $BaseName)
    if (Test-Path $pack) { Remove-Item $pack -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $pack | Out-Null
    Copy-Item $Stage (Join-Path $pack "stage") -Recurse
    Copy-Item $IssFile $pack
    $IssDefines = $IssDefines.Clone()
    $IssDefines["StageDir"] = (Join-Path $pack "stage")
    $IssDefines["OutDir"]   = $pack
    $IssFile = Join-Path $pack (Split-Path $IssFile -Leaf)
    Write-Host ("       Paketierung in " + $pack + " (32-Bit-Umleitung)")

    # NICHT $args nennen: das ist eine automatische Variable in PowerShell, und
    # sie zu ueberschreiben verwirft die Argumente. Der erste Lauf bekam
    # stattdessen die Hilfeseite von ISCC zu sehen.
    $isccArgs = @()
    foreach ($k in $IssDefines.Keys) { $isccArgs += ('/D{0}="{1}"' -f $k, $IssDefines[$k]) }
    $isccArgs += $IssFile
    $isccOut = Invoke-Native { & $iscc $isccArgs }
    if ($LASTEXITCODE -ne 0) {
        # Bei Erfolg genuegen die letzten Zeilen. Bei einem Fehlschlag ist genau
        # das Verschweigen der Grund, warum man zweimal hinfahren muss.
        Write-Host "       --- ISCC vollstaendig ---"
        $isccOut | ForEach-Object { Write-Host ("       | " + $_) }
        Write-Host ("       Arbeitsverzeichnis: " + (Get-Location).Path)
        Write-Host ("       TEMP: " + $env:TEMP)
        foreach ($pfad in @($IssFile, $Stage, $OutDir)) {
            Write-Host ("       " + $pfad + "  vorhanden=" + (Test-Path $pfad))
        }
        throw "ISCC exit $LASTEXITCODE"
    }
    $isccOut | Select-Object -Last 4 | ForEach-Object { Write-Host "       $_" }

    $gebaut = Join-Path $pack "$BaseName-setup.exe"
    if (-not (Test-Path $gebaut)) { throw "Installer fehlt: $gebaut" }
    Copy-Item $gebaut $OutDir -Force
    Remove-Item $pack -Recurse -Force
    $setup = Join-Path $OutDir "$BaseName-setup.exe"
    if (-not (Test-Path $setup)) { throw "Installer kam nicht zurueck: $setup" }
    (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower() + "  " + (Split-Path $setup -Leaf) |
        Set-Content "$setup.sha256" -Encoding ascii
    Write-Host ("       " + (Split-Path $setup -Leaf) + "  " + [math]::Round((Get-Item $setup).Length/1MB,2) + " MB")
}
