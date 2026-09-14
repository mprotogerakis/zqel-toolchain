# VERSUCHSPROTOKOLL, kein Baurezept.
#
#   powershell -ExecutionPolicy Bypass -File tools/windows/experiment_kani_creusot.ps1
#
# Frage: lassen sich Creusot und Kani nativ auf Windows bauen, so dass man
# ihnen glauben darf? Gemessen am 2026-09-13 auf win-nuitka-01.
#
# ERGEBNIS IN EINEM SATZ:
#   Creusot ja, mit drei kleinen Portabilitaetspatches - aber nur bis zur
#   .coma-Datei, nicht bis zum Beweis.
#   Kani nein. Nicht "schwer", sondern falsch.
#
# ------------------------------------------------------------------ KANI ----
# kani-driver.exe und kani-compiler.exe bauen mit sechs kleinen Patches und
# melden korrekt "Kani Rust Verifier 0.67.0". Danach greift im Compiler:
#
#   fn check_target(session: &Session) {
#       // The requirement below is needed to build a valid CBMC machine model
#       // in function `machine_model_from_session` ...
#
# und im Modell selbst:
#
#   // The model assumes a `x86_64-unknown-linux-gnu`, `x86_64-apple-darwin`
#   // or `aarch64-apple-darwin` platform. We check the target platform in
#   // `check_target` ... and error if it is not any of the ones we expect.
#
# Die Sperre ist also KEINE Paketierungsfrage, sondern die Vorbedingung dafuer,
# dass das CBMC-Maschinenmodell ueberhaupt gilt. `x86_64-pc-windows-msvc` in
# die Erlaubnisliste zu schreiben erweitert das Modell nicht - es entfernt die
# Zusicherung. Kani rechnete dann Verdikte gegen ein Modell einer anderen
# Maschine, und das Ergebnis saehe von aussen aus wie ein Verdikt.
#
# Deshalb: Kani auf Windows bleibt ein Fall fuer den Worker (#321), und zwar
# nicht wegen des Aufwands.
#
# ---------------------------------------------------------------- CREUSOT ----
# Drei Dateien, 16 Zeilen - allesamt echte Portabilitaetsfehler, die Sorte, die
# man upstream einreicht, nicht die Sorte, die eine Zusicherung aushebelt:
#
#   cargo-creusot/src/config.rs                Unix-Pfadkonvertierung
#   cargo-creusot/src/main.rs                  Programmpruefung ohne .exe-Suffix
#   creusot-setup/src/tools_versions_urls.rs   Prover-Tabelle nur Linux/macOS
#
# Damit baut der ganze Workspace, und das Ergebnis ist mehr als ein gelungener
# Compile: das Beispielverzeichnis uebersetzt zu echten .coma-Dateien
# (bdd.coma 146 KB, doubly_linked_list.coma 528 KB).
#
# Was FEHLT, ist die Beweiskette: Why3 und why3find. Der native opam-Weg
# existiert, richtet sich aber seine eigene Cygwin-Umgebung ein und baut OCaml
# von Grund auf. Zum Messzeitpunkt war why3.exe nicht vorhanden.
#
# Creusot auf Windows bringt einen also bis an die Tuer, nicht hindurch.
#
# --------------------------------------------------------------- FOLGERUNG ---
# Fuer den Worker aus #321 bleiben BEIDE Werkzeuge - aber aus verschiedenen
# Gruenden, und der Unterschied ist wichtig:
#   Kani    weil ein nativer Bau Verdikte erzeugte, die nichts bedeuten.
#   Creusot weil die Beweiskette (Why3) noch nicht steht - das ist Aufwand,
#           keine Bedeutungsfrage, und kann sich aendern.

$ErrorActionPreference = "Continue"
$W = "C:\kani-creusot-win"

function Zeile($t) { Write-Host $t }
function Pruefe($was, $bedingung) {
    Zeile ("  [{0}] {1}" -f $(if ($bedingung) { "ja " } else { "NEIN" }), $was)
    return $bedingung
}

Zeile "=== Voraussetzungen ==="
Pruefe "Rust (cargo)"      (Test-Path "$env:USERPROFILE\.cargo\bin\cargo.exe")   | Out-Null
Pruefe "MSVC-Buildwerkzeuge" (Test-Path "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2022\BuildTools") | Out-Null
Pruefe "opam"              (Test-Path "$env:LOCALAPPDATA\opam")                  | Out-Null

Zeile ""
Zeile "=== Creusot: baut und uebersetzt ==="
$cr = Pruefe "creusot-rustc.exe"  (Test-Path "$W\creusot\target\debug\creusot-rustc.exe")
Pruefe "cargo-creusot.exe"        (Test-Path "$W\creusot\target\debug\cargo-creusot.exe") | Out-Null
$coma = @(Get-ChildItem "$W\creusot" -Filter "*.coma" -Recurse -ErrorAction SilentlyContinue)
Pruefe ("erzeugte .coma-Dateien: " + $coma.Count) ($coma.Count -gt 0) | Out-Null
Zeile ""
Zeile "=== Creusot: die Beweiskette FEHLT ==="
Pruefe "why3.exe"     ([bool](Get-Command why3 -ErrorAction SilentlyContinue))     | Out-Null
Pruefe "why3find.exe" ([bool](Get-Command why3find -ErrorAction SilentlyContinue)) | Out-Null
Zeile "  -> ohne Why3 endet Creusot bei der .coma-Datei, nicht beim Beweis."

Zeile ""
Zeile "=== Kani: baut, darf aber nicht ==="
Pruefe "kani-driver.exe"   (Test-Path "$W\kani\target\debug\kani-driver.exe")   | Out-Null
Pruefe "kani-compiler.exe" (Test-Path "$W\kani\target\debug\kani-compiler.exe") | Out-Null
if (Test-Path "$W\kani\target\debug\kani-driver.exe") {
    $v = & "$W\kani\target\debug\kani-driver.exe" --version 2>&1 | Select-Object -First 1
    Zeile ("  meldet: " + $v)
}
$ci = "$W\kani\kani-compiler\src\codegen_cprover_gotoc\compiler_interface.rs"
if (Test-Path $ci) {
    $modell = Select-String -Path $ci -Pattern "The model assumes a" -SimpleMatch
    if ($modell) { Zeile ("  Quelltext sagt: " + $modell.Line.Trim()) }
    $geoeffnet = Select-String -Path $ci -Pattern "is_x86_64_windows_target" -SimpleMatch
    if ($geoeffnet) {
        Zeile "  ACHTUNG: die Plattformsperre wurde hier geoeffnet."
        Zeile "  Das erweitert das Maschinenmodell NICHT - es entfernt die Zusicherung,"
        Zeile "  dass es gilt. Verdikte daraus sind keine."
    }
}

Zeile ""
Zeile "=== Folgerung ==="
Zeile "  Kani    -> Worker. Nicht wegen des Aufwands, sondern weil ein nativer"
Zeile "             Bau Verdikte erzeugte, die nichts bedeuten."
Zeile "  Creusot -> Worker, solange Why3 auf Windows nicht steht. Das ist"
Zeile "             Aufwand, keine Bedeutungsfrage - und kann sich aendern."
