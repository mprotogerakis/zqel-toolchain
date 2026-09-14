"""Umgezogen aus mprotogerakis/LoLa am 2026-09-14.

Hier steht nur noch, was die MASCHINE betrifft. Was zqels eigenen
Windows-Bau prueft - build_dist.py, requirements.txt, der Nightly -
ist drueben geblieben: es hat mit der Werkzeugkette nichts zu tun.

#317: was Windows braucht, steht an EINER Stelle — und nicht zweimal.

Auf Linux und macOS haelt `flake.nix` fest, was gebraucht wird. Auf Windows
gibt es kein nix. Die naheliegende Folge waere eine zweite Liste, die dasselbe
nochmal sagt — und irgendwann etwas anderes.

Der Schnitt, der das verhindert: die KORREKTHEITSTRAGENDE Abhaengigkeit ist
ohnehin plattformunabhaengig. Z3 steht in `requirements.txt`, per Artefakt-Hash
gepinnt (`z3-nightly-0d4a2db`), und gilt dort auf jeder Plattform gleich — die
Flake baut es seit laengerem nicht mehr. Was Windows zusaetzlich braucht, ist
reine BAUINFRASTRUKTUR: git, Python, ein C-Compiler.

Diese Datei haelt beide Haelften auseinander.
"""
from __future__ import annotations

import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_MANIFEST = _ROOT / "tools" / "windows" / "deps.winget.json"


def _packages() -> list:
    doc = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    return [p["PackageIdentifier"] for s in doc["Sources"] for p in s["Packages"]]


def test_the_manifest_is_valid_winget_import():
    doc = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert doc["Sources"], "ohne Quelle kann `winget import` nichts tun"
    assert _packages(), "leeres Manifest"






def test_the_gated_tools_stay_out():
    """matiec, cbmc, creusot, why3 sind Linux-Werkzeuge hinter Gates. Sie im
    Windows-Manifest zu fuehren hiesse, etwas zu versprechen, das die Plattform
    nicht einloest.

    gappa steht aus einem anderen Grund nicht drin: Windows baut es selbst, aus
    einer per Hash gepinnten Quelle (gappa-pin.json). Fertig gibt es dort keines
    — gemessen am 2026-09-13 kennt MSYS2 15725 Pakete und kein gappa darunter
    (Gegenprobe: `boost` trifft achtmal). Auf Windows war Selbstbauen also der
    einzige Weg, nicht die schoenere von zwei Moeglichkeiten.
    """
    for tool in ("matiec", "cbmc", "creusot", "why3", "gappa"):
        assert not any(tool in p.lower() for p in _packages()), tool


def test_the_provisioning_script_applies_the_manifest():
    """Das Skript darf keine eigene Paketliste fuehren — es wendet das Manifest
    an. Sonst waere es die zweite Stelle."""
    script = (_ROOT / "tools" / "windows" / "provision.ps1").read_text(
        encoding="utf-8")
    assert "winget import" in script and "deps.winget.json" in script
    assert "winget install" not in script, \
        "eine Einzelinstallation im Skript ist eine Liste neben dem Manifest"


# --- Die andere Richtung: was der Workflow benutzt, muss erklaert sein ------















# --- Der Runner ist SYSTEM ---------------------------------------------------
#
# Zwei Nightly-Laeufe gingen daran verloren, und beide Male sah die Diagnose
# harmlos aus: `winget list` zeigte das Werkzeug an. Es lag nur im
# Benutzerprofil, und der act_runner-Dienst laeuft als NT AUTHORITY\SYSTEM.
# Gemessen am 2026-09-13 aus einer SYSTEM-Aufgabe heraus:
#
#     git:    C:\Program Files\Git\cmd\git.exe
#     python: FEHLT
#     pwsh:   FEHLT
#
# Die Tests hier halten die Lehre fest, nicht die Symptome.

def _script() -> str:
    return (_ROOT / "tools" / "windows" / "provision.ps1").read_text(
        encoding="utf-8")


def test_the_packages_that_default_to_the_user_profile_say_machine():
    """Python und Inno Setup installiert winget sonst ins Profil."""
    doc = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    by_id = {p["PackageIdentifier"]: p
             for s in doc["Sources"] for p in s["Packages"]}
    for ident in ("Python.Python.3.12", "JRSoftware.InnoSetup"):
        assert by_id[ident].get("Scope") == "machine", \
            f"{ident} ohne Scope=machine landet im Profil und ist fuer SYSTEM weg"


def test_powershell_is_not_promised_by_the_manifest():
    """winget antwortet auf `--scope machine` fuer Microsoft.PowerShell mit
    'No applicable installer found'. Ein Manifest, das es trotzdem auffuehrt,
    sieht beim Lesen erledigt aus und liefert nichts."""
    assert "Microsoft.PowerShell" not in _packages()
    script = _script()
    assert "PowerShell" in script and "msiexec" in script, \
        "wenn es nicht im Manifest steht, muss das Skript es holen"
    assert "Program Files\\PowerShell\\7\\pwsh.exe" in script, \
        "das Skript muss maschinenweit pruefen, nicht per Get-Command"


def test_the_check_rejects_tools_that_only_the_current_user_can_see():
    """Das ist die Kontrolle, die den Fehler gefunden HAETTE. Ohne sie meldet
    `provision.ps1 -VerifyOnly` gruen und der Build scheitert danach."""
    script = _script()
    assert "Users\\*" in script, \
        "ein Fund unter C:\\Users\\ muss als fehlend gelten"
    assert "SYSTEM" in script, \
        "das Skript muss sagen, WER den Build faehrt - sonst prueft der Naechste wieder sich selbst"
