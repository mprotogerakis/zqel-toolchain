"""Windows baut seine Werkzeuge selbst - und zwar dieselben, die wir sonst haben.

Zwei Werkzeuge fehlten auf Windows und nur dort: gappa und matiec. Auf Linux und
macOS kommen beide aus der Flake; auf Windows gab es nichts Fertiges. Gemessen am
2026-09-13 kennt MSYS2 15725 Pakete und weder das eine noch das andere
(Gegenprobe: `boost` trifft achtmal), und beide Upstreams veroeffentlichen keine
Windows-Binaerdateien.

Die nicht offensichtliche Frage war nicht OB, sondern WELCHE Fassung. Bei gappa
steht Upstream bei 1.8.3 und die devShell bei 1.4.0; bei matiec gibt es gar keine
Releases, nur Revisionen. Die neueste zu nehmen haette beide Luecken geschlossen
und je eine Asymmetrie eingebaut: ein Beweis- bzw. Uebersetzungswerkzeug, das je
nach Plattform ein anderes ist. Genau die, die wir bei z3 win_arm64 (5.2.0.0
statt 5.1.0.0) nicht eingegangen sind.

Diese Datei haelt fest, was fuer BEIDE Pakete gelten muss - und zwar gegen
`tools/windows/win_package.ps1`, die eine Stelle, an der die Lizenz- und
Herkunftslogik steht. Eine Kopie davon je Werkzeug waere die zweite Autoritaet,
und sie wuerde irgendwann ein Paket mit falschem Lizenzhinweis ausliefern.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WIN = _ROOT / "tools" / "windows"
_SHARED = _WIN / "win_package.ps1"
_ISS = _WIN / "tool.iss"
_PROBE = _WIN / "provenance.sh"
_MSYS = _WIN / "deps.msys2.txt"

# name -> (Pin, Bauskript ps1, Bauskript sh, Workflow, Rauchprobe)
_TOOLS = {
    "gappa":  ("gappa-pin.json",  "build_gappa.ps1",  "build_gappa.sh",
               "gappa-windows.yml",  "gappa-smoke"),
    "matiec": ("matiec-pin.json", "build_matiec.ps1", "build_matiec.sh",
               "matiec-windows.yml", "matiec-smoke"),
}
_NAMES = sorted(_TOOLS)


def _pin(tool: str) -> dict:
    return json.loads((_ROOT / _TOOLS[tool][0]).read_text(encoding="utf-8"))


def _source(tool: str) -> dict:
    (only,) = _pin(tool)["source"].values()
    return only


def _ps1(tool: str) -> str:
    return (_WIN / _TOOLS[tool][1]).read_text(encoding="utf-8")


def _sh(tool: str) -> str:
    return (_WIN / _TOOLS[tool][2]).read_text(encoding="utf-8")


def _wf(tool: str) -> str:
    return (_ROOT / ".forgejo" / "workflows" / _TOOLS[tool][3]).read_text(encoding="utf-8")


def _identity(tool: str) -> str:
    """Woran das Werkzeug gebunden ist: eine Version oder eine Revision."""
    p = _pin(tool)
    return p.get("version") or p["revision"]


# --- Der Pin ist die Autoritaet ----------------------------------------------

@pytest.mark.parametrize("tool", _NAMES)
def test_the_pin_names_a_hashed_source(tool):
    src = _source(tool)
    assert len(src["sha256"]) == 64, "ein Pin ohne Hash pinnt nichts"
    assert src["size"] > 0
    assert src["url"].startswith("https://")


@pytest.mark.parametrize("tool", _NAMES)
def test_the_pin_says_which_upstream_it_is_pinned_against(tool):
    assert _pin(tool)["upstream_project"].startswith("https://")


@pytest.mark.parametrize("tool", _NAMES)
def test_the_scripts_carry_no_second_identity(tool):
    """Version bzw. Revision und Hash stehen im Pin. Ein Skript, das sie
    wiederholt, ist die zweite Stelle - und sie driftet."""
    ident = _identity(tool)
    for text, wo in ((_ps1(tool), _TOOLS[tool][1]), (_sh(tool), _TOOLS[tool][2]),
                     (_wf(tool), _TOOLS[tool][3])):
        for line in text.splitlines():
            if line.lstrip().startswith(("#", ";")):
                continue          # Kommentare duerfen sie nennen
            assert ident not in line, f"{wo}: feste Kennung in {line!r}"
        assert _source(tool)["sha256"] not in text, f"{wo}: fester Hash"


def test_gappa_is_pinned_to_what_the_devshell_has():
    """Upstream steht bei 1.8.3. Der Pin steht bei dem, was ueberall sonst laeuft."""
    pin = _pin("gappa")
    assert pin["version"] == "1.4.0"
    assert pin["upstream_latest_when_checked"] != pin["upstream_tag"], \
        "wenn Upstream eingeholt hat, gehoert der Abstand neu vermerkt"
    assert any("neueste" in z.lower() for z in pin["_comment"]), \
        "der Kommentar muss sagen, warum NICHT die neueste Version"


def test_matiec_is_pinned_to_the_revision_the_flake_builds():
    """Der schaerfste Fall: hier stehen zwei Dateien im Repo, die dieselbe
    Revision nennen muessen. Gehen sie auseinander, uebersetzt Windows mit einem
    anderen iec2c als Linux und macOS - und die Uebersetzungsvalidierung
    vergliche zwei verschiedene Werkzeuge."""
    rev = _pin("matiec")["revision"]
    flake = (_ROOT / "flake.nix").read_text(encoding="utf-8")
    assert re.search(rf'rev\s*=\s*"{re.escape(rev)}"', flake), \
        f"flake.nix baut eine andere matiec-Revision als matiec-pin.json ({rev})"


# --- Was der Bau erzwingt ----------------------------------------------------

def test_the_build_refuses_a_source_that_does_not_match():
    """Ein Downloader, der den Hash nur ausrechnet, prueft nichts."""
    text = _SHARED.read_text(encoding="utf-8")
    assert "Get-FileHash" in text
    assert "Hash weicht ab" in text
    assert "Remove-Item $tar -Force" in text, \
        "eine falsche Quelle muss weg, sonst gilt sie beim naechsten Lauf als da"


def test_the_dll_set_is_checked_against_the_pin():
    """Die ausgelieferten DLLs kommen aus dem Linker, die erlaubten aus dem Pin.
    Waechst eine Abhaengigkeit still dazu, bricht der Bau ab - statt ein Paket
    auszuliefern, dessen Lizenzhinweis sie nicht nennt."""
    text = _SHARED.read_text(encoding="utf-8")
    assert "Compare-Object" in text
    for tool in _NAMES:
        dlls = _pin(tool)["windows_build"]["runtime_dlls"]
        assert dlls, tool
        for d in dlls:
            assert d not in text, f"{d} steht fest im gemeinsamen Modul statt im Pin"


def test_the_build_refuses_a_changed_licence():
    """Eine neue Paketversion ist normal. Eine andere LIZENZ ist ein Befund -
    der beiliegende Hinweis waere sonst falsch, und das ist kein Bau-, sondern
    ein Verteilungsproblem."""
    text = _SHARED.read_text(encoding="utf-8")
    assert "msys2_licenses" in text
    assert "Lizenz von" in text and "geaendert" in text
    assert "Verteilungsproblem" in text


@pytest.mark.parametrize("tool", _NAMES)
def test_the_provenance_is_measured_not_maintained(tool):
    """Die Paketversion steht bewusst NICHT im Pin: sie waere nach dem naechsten
    pacman-Lauf falsch, und ein falscher Herkunftsnachweis ist schlimmer als
    keiner."""
    for name, meta in _pin(tool)["windows_build"]["runtime_dlls"].items():
        assert "msys2_version" not in meta, \
            f"{name}: die Version gehoert gemessen, nicht gepflegt"
    probe = _PROBE.read_text(encoding="utf-8")
    assert "pacman -Qo" in probe and "pacman -Qi" in probe


@pytest.mark.parametrize("tool", _NAMES)
def test_the_inner_script_insists_on_the_mingw_shell(tool):
    """Unter der MSYS-Standardshell meldet `uname -s` MSYS_NT-..., und
    Autotools-Projekte treffen dann den Unix-Zweig. Bei gappa linkte das sein
    Bauwerkzeug ohne -lws2_32; der Abbruch las sich wie ein gappa-Fehler."""
    text = _sh(tool)
    assert "MSYSTEM=MINGW64" in text
    assert "MINGW*)" in text, "die Shell muss geprueft werden, nicht nur gesetzt"
    assert "sort -u" in text, \
        "ldd nennt libwinpthread mehrfach - ohne -u meldet die Pin-Pruefung eine Abweichung"


def test_the_shared_module_does_not_mistake_stderr_for_failure():
    """`$ErrorActionPreference = "Stop"` macht aus jeder fremden stderr-Zeile
    einen Abbruch. Hier waere das doppelt falsch: pacman meldet "up to date --
    skipping" dorthin, und die gappa-Rauchprobe BRAUCHT ein Ziel, das scheitert.
    """
    assert "function Invoke-Native" in _SHARED.read_text(encoding="utf-8")
    for tool in _NAMES:
        for line in _ps1(tool).splitlines():
            if re.search(r"(?<!Invoke-Native \{ )& \$(bash|staged|iscc)\b", line):
                assert "Invoke-Native" in line or line.lstrip().startswith("#"), \
                    f"{tool}: ungekapselter nativer Aufruf: {line.strip()!r}"


def test_progress_never_leaves_a_function_as_a_return_value():
    """In PowerShell IST der Ausgabestrom der Rueckgabewert. Eine Funktion, die
    ihren Fortschritt mit Write-Output meldet und einen Pfad zurueckgibt, liefert
    ein Array aus beidem - und der Fehler faellt erst zwei Stufen spaeter auf."""
    text = _SHARED.read_text(encoding="utf-8")
    # Der Kommentar DARF Write-Output erklaeren - er tut es sogar. Gemeint sind
    # die Anweisungen.
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        assert "Write-Output" not in line, \
            f"im gemeinsamen Modul geht Fortschritt ueber Write-Host: {line.strip()!r}"
    assert "Write-Host" in text


# --- Lizenz und Herkunft -----------------------------------------------------

@pytest.mark.parametrize("tool", _NAMES)
def test_every_shipped_library_names_its_licence_texts(tool):
    for name, meta in _pin(tool)["windows_build"]["runtime_dlls"].items():
        assert meta.get("licence_files"), f"{name} nennt keinen Lizenztext"
        assert meta.get("msys2_package"), f"{name} nennt kein Herkunftspaket"
        assert meta.get("upstream_url", "").startswith("http"), name


@pytest.mark.parametrize("tool", _NAMES)
def test_the_package_ships_dlls_because_of_the_licence(tool):
    """LGPL ist der Grund fuer den dynamischen Link - nicht ein Versehen.
    Statisch laeuft gappa auch (gemessen: 21434128 Bytes, keine fremde DLL),
    schuldet aber eine Relink-Moeglichkeit."""
    b = _pin(tool)["windows_build"]
    assert b["link"] == "dynamisch"
    assert "LGPL" in b["_why_dynamic"]
    shared = _SHARED.read_text(encoding="utf-8")
    for name, meta in b["runtime_dlls"].items():
        assert meta["msys2_licenses"] not in shared, \
            f"Lizenz von {name} steht im Modul statt im Pin"
    assert "runtime_dlls" in shared and "$dllZeilen" in shared, \
        "das NOTICE muss aus dem Pin erzeugt werden"


def test_the_gcc_runtime_exception_travels_with_every_package():
    for tool in _NAMES:
        dlls = _pin(tool)["windows_build"]["runtime_dlls"]
        for name in ("libgcc_s_seh-1.dll", "libstdc++-6.dll"):
            files = " ".join(dlls[name]["licence_files"])
            assert "COPYING.RUNTIME" in files, \
                f"{tool}/{name}: ohne die Runtime Library Exception fehlt die Begruendung"


def test_the_lgpl_libraries_carry_both_required_texts():
    """LGPLv3 4(b): eine Kopie der GPL und der LGPL. Betrifft gappa (gmp, mpfr);
    matiec braucht beide Bibliotheken nicht."""
    dlls = _pin("gappa")["windows_build"]["runtime_dlls"]
    for name in ("libgmp-10.dll", "libmpfr-6.dll"):
        files = " ".join(dlls[name]["licence_files"])
        assert "LGPL-3.0" in files, f"{name}: LGPL-Text fehlt"
        assert "GPL" in files.replace("LGPL", ""), f"{name}: GPL-Text fehlt"
    assert "libgmp-10.dll" not in _pin("matiec")["windows_build"]["runtime_dlls"]


@pytest.mark.parametrize("tool", _NAMES)
def test_every_vendored_licence_text_exists_and_matches_its_hash(tool):
    """Ein beigelegter Lizenztext, den niemand pruefen kann, ist austauschbar."""
    for name, meta in _pin(tool)["windows_build"]["vendored_licence_texts"].items():
        f = _WIN / "licenses" / name
        assert f.is_file(), f"beigelegter Text fehlt: {name}"
        raw = f.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == meta["sha256"], name
        assert len(raw) == meta["size"], name


@pytest.mark.parametrize("tool", _NAMES)
def test_each_named_licence_text_is_either_vendored_or_harvestable(tool):
    """Jeder genannte Text hat genau eine Herkunft: das Repo, das MSYS2-Paket
    oder der Quellbaum des Werkzeugs. Ein vierter Fall waere eine Datei, die
    beim Bau aus dem Nichts kommt."""
    b = _pin(tool)["windows_build"]
    vendored = set(b["vendored_licence_texts"])
    aus_quelle = {"tool/" + pathlib.PurePosixPath(f).name
                  for f in b["tool_licence"]["files_from_source_tree"]}
    for meta in b["runtime_dlls"].values():
        for rel in meta["licence_files"]:
            if rel in vendored or rel in aus_quelle:
                continue
            assert rel.count("/") == 1, \
                f"{rel}: weder beigelegt noch als <paket>/<datei> aus MSYS2 holbar"


@pytest.mark.parametrize("tool", _NAMES)
def test_the_source_travels_with_the_binary(tool):
    """GPL, LGPL und CeCILL wollen wissen, wo der Quellcode ist. Ihn neben das
    Binary zu legen beantwortet das, ohne auf einen fremden Server zu zeigen."""
    assert _pin(tool)["windows_build"]["source_is_published_beside_the_binary"] is True
    shared = _SHARED.read_text(encoding="utf-8")
    assert "Copy-Item $SourceTarball" in shared
    assert "SOURCES.txt" in shared


def test_the_installer_ships_the_texts_not_just_the_binaries():
    iss = _ISS.read_text(encoding="utf-8")
    assert "recursesubdirs" in iss, \
        "eine zweite Dateiliste im Installer waere die zweite Autoritaet"
    assert "LicenseFile" in iss
    assert "Behauptung" in iss, \
        "der Installer muss sagen, warum die Texte mitgehen"


# --- Die Rauchproben ---------------------------------------------------------

def test_the_gappa_smoke_can_tell_a_prover_from_exit_zero():
    """Ein Rauchtest, der nur das Gelingen prueft, wuerde auch `exit 0`
    bestehen. Deshalb gehoert ein Ziel dazu, das scheitern MUSS."""
    smoke = _WIN / "gappa-smoke"
    holds = (smoke / "holds.g").read_text(encoding="utf-8")
    fails = (smoke / "fails.g").read_text(encoding="utf-8")
    assert "float<ieee_64,ne>" in holds, "der Parser allein ist zu wenig"
    assert "1b-53" in holds and "1b-60" in fails
    ps1 = _ps1("gappa")
    assert "-ne 1" in ps1, "das scheiternde Ziel muss auf exit 1 geprueft werden"
    assert "BND(|x - x_|)" in ps1, "es muss die Schranke NENNEN, nicht nur scheitern"


def test_the_matiec_smoke_checks_the_generated_files_not_the_exit_code():
    """Ein Uebersetzer, der nichts schreibt, meldet auch 0."""
    ps1 = _ps1("matiec")
    for f in ("POUS.c", "Config0.c", "VARIABLES.csv"):
        assert f in ps1, f"{f} wird nicht geprueft"
    assert "PROG0" in ps1, "der Inhalt muss geprueft werden, nicht nur die Existenz"
    st = (_WIN / "matiec-smoke" / "counter.st").read_text(encoding="utf-8")
    assert "CONFIGURATION" in st and "RESOURCE" in st, \
        "ohne Konfiguration erzeugt iec2c keine Res0.c"


def test_matiec_ships_more_than_a_binary():
    """MATIEC_DIR muss lib/ieclib.txt enthalten, sonst uebersetzt iec2c keine
    Standardfunktion - `iec2c.exe` allein waere ein unbrauchbares Paket."""
    payload = _pin("matiec")["windows_build"]["payload"]
    assert payload["binary"] == "iec2c.exe"
    assert payload["data_dir"] == "lib"
    ps1 = _ps1("matiec")
    assert "ieclib.txt" in ps1, "das Bauskript muss das nachpruefen"




# --- Die Laeufe --------------------------------------------------------------

@pytest.mark.parametrize("tool", _NAMES)
def test_the_weekly_run_reports_upstream_but_does_not_bump(tool):
    text = _wf(tool)
    assert "cron:" in text and "* * 1" in text, "woechentlich, nicht taeglich"
    assert "runs-on: windows-amd64" in text
    assert "continue-on-error: true" in text, \
        "der Upstream-Vergleich ist ein Befund, kein Gate"
    for verb in ("Set-Content " + _TOOLS[tool][0], "git commit", "git push"):
        assert verb not in text, f"der Lauf darf den Pin nicht schreiben: {verb}"


@pytest.mark.parametrize("tool", _NAMES)
def test_the_artifact_goes_to_the_registry_not_to_a_release(tool):
    """Die Linie, die z3 und diese Pakete auseinanderhaelt: was wir per Hash
    PINNEN und ein Werkzeug aufloesen muss, liegt als Release (z3, aus
    requirements.txt geholt); was unsere CI selbst BAUT, liegt in der
    Paketregistry. Ein Release legte zudem einen git-Tag fuer ein fremdes
    Werkzeug in unsere Historie."""
    text = _wf(tool)
    assert "PACKAGE_TOKEN != ''" in text
    assert "RELEASE_TOKEN" not in text, "kein toter Pfad: die Entscheidung ist gefallen"
    assert f"api/packages/proto/generic/{tool}" in text


def test_no_publishing_step_reddens_on_a_second_run():
    """Die Paketversion ist bei den Nightlies das Datum und bei den Werkzeugen
    der Pin - beide sind stabil. Ein zweiter Lauf laedt dieselbe Datei hoch, und
    die Registry antwortet mit 409. Bricht der Schritt daran ab, meldet ein
    voellig gesunder Build rot."""
    wf = _ROOT / ".forgejo" / "workflows"
    # Die zqel-Nightlies stehen nicht mehr hier - sie bauen zqel, nicht die
    # Werkzeuge, und sind in mprotogerakis/LoLa geblieben. Dieselbe Forderung
    # gilt dort weiter; sie wurde beim Umzug NICHT fallengelassen.
    namen = [_TOOLS[t][3] for t in _NAMES]
    for name in namen:
        text = (wf / name).read_text(encoding="utf-8")
        assert "409" in text, f"{name}: der Upload kennt den Wiederholungsfall nicht"
        assert "unveraendert" in text, \
            f"{name}: ein uebersprungener Upload muss sich als solcher melden"


def test_the_msys2_packages_live_in_one_file():
    pkgs = [l.strip() for l in _MSYS.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    assert {"autoconf", "automake", "flex", "bison"} <= set(pkgs), \
        "matiec liefert kein fertiges configure mit"
    assert not any("gappa" in p or "matiec" in p for p in pkgs), \
        "die Werkzeuge werden gebaut, nicht installiert - der Pin ist die Autoritaet"
    # Die eigentliche Regel ist nicht "das Wort kommt nicht vor" - `make` steht
    # zu Recht in einer Fortschrittszeile von build_matiec.ps1. Die Regel ist:
    # KEIN Werkzeugskript installiert selbst. Das tut genau eine Stelle, und sie
    # liest die Liste aus der Datei.
    for tool in _NAMES:
        ps1 = _ps1(tool)
        # `pacman` darf als Wort vorkommen - "[1/7] pacman aus deps.msys2.txt"
        # ist eine Fortschrittszeile. Was nicht vorkommen darf, ist der Aufruf.
        assert "pacman -S" not in ps1, \
            f"{tool}: installiert selbst, statt Install-MsysPackages zu rufen"
        assert "Install-MsysPackages" in ps1
        assert "deps.msys2.txt" in ps1
    shared = _SHARED.read_text(encoding="utf-8")
    assert "pacman -S --needed --noconfirm" in shared
    for name in pkgs:
        assert not re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", shared), \
            f"{name} steht doppelt: im gemeinsamen Modul und im Manifest"


@pytest.mark.skipif(shutil.which("gappa") is None,
                    reason="kein gappa auf dem PATH (Windows vor der Installation)")
def test_the_pinned_gappa_is_the_one_on_this_machine():
    """Der eigentliche Punkt: EIN gappa ueber alle Plattformen. Laeuft dieser
    Test auf einer Maschine mit gappa und schlaegt fehl, ist die Asymmetrie da -
    egal welche Seite sich bewegt hat."""
    out = subprocess.run(["gappa", "--version"], capture_output=True, text=True)
    reported = (out.stdout + out.stderr).strip()
    assert _pin("gappa")["version"] in reported, \
        f"devShell meldet {reported!r}, der Pin sagt {_pin('gappa')['version']}"


# --- Der MSYS2-Stand ist gesperrt, nicht nur notiert ------------------------
#
# Bis zum 2026-09-13 hat der Bau die Paketversionen GEMESSEN und berichtet. Das
# ist ehrlich und war trotzdem der falsche Schnitt: ein spaeterer `pacman -Syu`
# baut unter demselben Rezept mit anderen Bibliotheken, und der Bau meldet es
# nur. Codex hat das im Review benannt (#323, Punkt 3) - ich hatte "Herkunft
# ehrlich berichten" mit "Bau reproduzierbar machen" verwechselt.

_LOCK = _ROOT / "tools" / "windows" / "msys2.lock.json"


def test_the_lock_pins_what_the_build_installs_and_what_it_ships():
    lock = json.loads(_LOCK.read_text(encoding="utf-8-sig"))["packages"]
    pkgs = {l.strip() for l in _MSYS.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}
    fehlend = pkgs - set(lock)
    assert not fehlend, f"nicht gesperrt: {sorted(fehlend)}"
    # Die Eigentuemer der ausgelieferten DLLs kommen als Abhaengigkeit mit und
    # wuerden sonst ungesperrt driften.
    for eigentuemer in ("mingw-w64-x86_64-gcc-libs", "mingw-w64-x86_64-libwinpthread"):
        assert eigentuemer in lock, eigentuemer
    for name, eintrag in lock.items():
        assert eintrag["version"], name


def test_the_lock_names_the_boundary_it_does_not_cover():
    """Eine Zusicherung, die ihre Grenze verschweigt, wird beim naechsten Leser
    zur Behauptung ueber alles."""
    doc = json.loads(_LOCK.read_text(encoding="utf-8-sig"))
    text = " ".join(doc["_comment"])
    assert "transitive" in text and "nicht" in text


def test_the_build_stops_on_drift_instead_of_reporting_it():
    shared = _SHARED.read_text(encoding="utf-8")
    assert "msys2_lock.py" in shared
    assert "verify" in shared
    i = shared.index("msys2_lock.py")
    rest = shared[i:i + 400]
    assert "throw" in rest, "eine Abweichung muss den Bau anhalten, nicht nur reden"


def test_the_comparison_does_not_happen_in_the_shell():
    """Der erste Entwurf hat den Lock in der Shell zerlegt und verglichen - und
    meldete gruen, als die Kontrolle eine Version absichtlich verfaelschte. Das
    Sammeln bleibt in der Shell (dort lebt pacman), das Vergleichen nicht."""
    sh = (_ROOT / "tools" / "windows" / "msys2_lock.sh").read_text(encoding="utf-8")
    assert "pacman -Q" in sh
    # Nur die Anweisungen, nicht die Prosa: der Kommentar ERKLAERT den Fehler
    # und darf ihn deshalb benennen. Zum vierten Mal heute dieselbe Falle -
    # `make` in `remake`, `pacman` in einer Fortschrittszeile, `Write-Output`
    # in einem Kommentar, und jetzt `json`.
    anweisungen = "\n".join(z for z in sh.splitlines()
                            if not z.lstrip().startswith("#"))
    assert "json" not in anweisungen.lower(), \
        "JSON in der Shell zu lesen war der Fehler"
    py = (_ROOT / "tools" / "windows" / "msys2_lock.py").read_text(encoding="utf-8")
    assert "utf-8-sig" in py, \
        "PowerShell schreibt eine BOM; ohne sig bricht der Pruefer statt zu pruefen"
    assert "ANDERE Datei" in py, \
        "gleiche Version bei anderem Dateihash muss auffallen"
