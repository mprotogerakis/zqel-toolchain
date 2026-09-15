"""Die Bindung ueber die Repositoriumsgrenze.

Solange Pins und Konsument im selben Commit lagen, war "dieses Verdikt, jener
Beweiser" trivial. Seit die Werkzeugkette ein eigenes Repository ist, laeuft
die Bindung ueber eine Grenze - und eine Grenze, ueber die nur Vertrauen
geht, ist keine Bindung.

toolchain-lock.json ist diese Bindung. Diese Tests halten sie fest.
"""
from __future__ import annotations

import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import write_toolchain_lock as lock  # noqa: E402

LOCK = json.loads((ROOT / "toolchain-lock.json").read_text(encoding="utf-8"))
FLAKE = (ROOT / "flake.nix").read_text(encoding="utf-8")


def test_the_lock_still_matches_the_pins():
    """Sonst beschreibt sie etwas, das es nicht mehr gibt."""
    neu = lock.sammle()
    beweglich = ("erzeugt", "quell_commit", "aktueller_flake_hash")
    a = {k: v for k, v in LOCK.items() if k not in beweglich}
    b = {k: v for k, v in neu.items() if k not in beweglich}
    assert a == b, ("toolchain-lock.json passt nicht mehr zu den Pins - "
                    "neu erzeugen mit tools/write_toolchain_lock.py")


def test_every_mirrored_tool_appears_in_the_lock():
    """Der Nenner: ein Werkzeug, das die Datei auslaesst, faellt drueben nicht
    auf - es fehlt dort einfach."""
    pins = json.loads((ROOT / "mirror-pin.json").read_text(encoding="utf-8"))["tools"]
    assert pins, "mirror-pin.json ist leer - Muster veraltet?"
    for name in pins:
        assert name in LOCK["werkzeuge"], f"{name} fehlt in toolchain-lock.json"


def test_every_artifact_has_its_licence_notice_beside_it():
    """Ohne den Hinweis geben wir ein fremdes Binary ohne seine Lizenz weiter.

    NICHT jede Datei neben dem Binary ist ein Artefakt. cbmc liefert ein
    `licence_sidecar` - den Lizenztext von diffblue/cbmc als eigene Datei,
    weil ein .msi sich ohne Windows nicht durchsehen laesst. Von IHM einen
    Beipackzettel zu verlangen hiesse, einen Lizenzhinweis fuer einen
    Lizenzhinweis zu fordern; genau daran war dieser Test rot, ohne dass die
    Auslieferung einen Mangel hatte.

    Welcher Name das ist, weiss `mirror-pin.json` - deshalb wird es dort
    gefragt und steht nicht als Ausnahmeliste hier. Ein zweiter Sidecar
    braeuchte sonst eine zweite Zeile an einer Stelle, die niemand ansieht.
    """
    pins = json.loads((ROOT / "mirror-pin.json").read_text(encoding="utf-8"))["tools"]
    for name, w in LOCK["werkzeuge"].items():
        if w["herkunft"] != "gespiegelt":
            continue
        lizenztext = (pins[name].get("licence_sidecar") or {}).get("name")
        if lizenztext:
            # Die Ausnahme darf ihn nicht verschwinden lassen: er ist
            # zugesagt, also muss er auch ausgeliefert werden.
            assert any(d.endswith(f"/{lizenztext}") for d in w["dateien"]), (
                f"{name}: {lizenztext} ist gepinnt, steht aber in keiner Adresse")
        archive = [d for d in w["dateien"]
                   if not d.endswith(".notice.txt")
                   and not (lizenztext and d.endswith(f"/{lizenztext}"))]
        beilagen = {d for d in w["dateien"] if d.endswith(".notice.txt")}
        assert archive, f"{name}: keine Artefakte"
        for a in archive:
            assert f"{a}.notice.txt" in beilagen, f"{name}: {a} ohne Lizenzhinweis"


def test_the_cache_in_the_lock_is_the_cache_in_the_flake():
    """Zwei Stellen, eine Wahrheit. Die Flake ist die Quelle - nix liest sie
    dort -, die Datei gibt sie nur weiter."""
    assert LOCK["cache"]["substituter"] in FLAKE
    assert LOCK["cache"]["public_key"] in FLAKE


def test_the_lock_says_that_the_flake_hash_is_navigation():
    """Ein beweglicher Wert in einer Bindungsdatei muss sich als beweglich
    zu erkennen geben - sonst zitiert ihn jemand als Identitaet."""
    assert "NAVIGATION" in LOCK["_hinweis_flake"]
    assert "aktueller_flake_hash" in LOCK


def test_the_generator_sends_a_user_agent():
    """Gemessen am 2026-09-14: Cloudflare weist den Vorgabewert von
    python-urllib mit 403 ab, ein eigener bekommt 200. Ohne ihn lieferte die
    Abfrage still None, und die Datei trug keinen Hash."""
    quelle = (ROOT / "tools" / "write_toolchain_lock.py").read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    treffer = [k for k in ast.walk(baum)
               if isinstance(k, ast.Constant) and k.value == "User-Agent"]
    assert treffer, "kein User-Agent gesetzt - die Abfrage bekommt 403"


def test_a_failed_lookup_is_loud_except_for_not_yet_published():
    """Ein stiller Fehlschlag hier heisst: die Datei traegt keinen Hash, und
    niemand merkt es."""
    quelle = (ROOT / "tools" / "write_toolchain_lock.py").read_text(encoding="utf-8")
    stelle = quelle[quelle.index("def _aktueller_flake_hash"):]
    stelle = stelle[:stelle.index("\ndef ")]
    assert "raise SystemExit" in stelle
    assert "e.code == 404" in stelle, "nur 'noch nicht da' darf leise sein"


def test_every_package_in_the_flake_is_referenced_by_a_check():
    """Ein Paket, das niemand baut, ist irgendwann kaputt, ohne dass es
    auffaellt. Genau so war matiec beim Umzug einen Commit lang da.

    Der erste Entwurf verlangte einen Rauchtest namens `<paket>-smoke`. Der
    fuer creusot-free heisst creusot-smoke - meine Erwartung, nicht die
    Wirklichkeit. Die REGEL ist "jedes Paket wird von etwas gebaut".
    """
    pakete = set(re.findall(r"^\s+([\w-]+) = \w+For system;", FLAKE, re.M))
    assert pakete, "keine Pakete in flake.nix gefunden - Muster veraltet?"
    pruefblock = FLAKE[FLAKE.index("checks = forAllSystems"):]
    for name in pakete:
        assert f"self.packages.${{system}}.{name}" in pruefblock, \
            f"{name} wird von keiner Pruefung angefasst"


def test_every_check_in_the_flake_is_actually_run_by_ci():
    """Eine Pruefung, die nur in der Flake steht, prueft nichts."""
    check = (ROOT / ".forgejo" / "workflows" / "check.yml").read_text(encoding="utf-8")
    anweisungen = "\n".join(z for z in check.splitlines()
                             if not z.lstrip().startswith("#"))
    pruefblock = FLAKE[FLAKE.index("checks = forAllSystems"):]
    pruefungen = set(re.findall(r"^\s+([\w-]+) = pkgs\.runCommand", pruefblock, re.M))
    assert pruefungen, "keine Pruefungen gefunden - Muster veraltet?"
    for name in pruefungen:
        assert name in anweisungen, f"{name} wird von check.yml nie gebaut"
