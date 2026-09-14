#!/usr/bin/env python3
"""Den MSYS2-Stand festschreiben und pruefen.

    python tools/windows/msys2_lock.py write    # Lock neu erzeugen
    python tools/windows/msys2_lock.py verify   # gegen den Lock pruefen

WARUM ES DAS GIBT:
Bis zum 2026-09-13 hat der Bau die Paketversionen nur GEMESSEN und berichtet.
Das ist ehrlich, aber nicht reproduzierbar: ein spaeterer `pacman -Syu` baut
unter demselben Rezept mit anderen Bibliotheken, und der Bau meldet es nur,
statt anzuhalten. Codex hat das im Review benannt (#323, Punkt 3).

Eine neue Baseline ist eine Entscheidung, kein Nebeneffekt. `verify` bricht ab.

GRENZE, ausdruecklich: gesperrt sind die ausdruecklich installierten Pakete und
die Eigentuemer der ausgelieferten DLLs. Die vollstaendige transitive Closure
ist es nicht.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

HIER = pathlib.Path(__file__).resolve().parent
LOCK = HIER / "msys2.lock.json"
BASH = pathlib.Path(r"C:\msys64\usr\bin\bash.exe")


def _msys_pfad(p: pathlib.Path) -> str:
    p = p.resolve()
    return "/" + p.drive[0].lower() + str(p)[2:].replace("\\", "/")


def bericht() -> dict[str, dict]:
    """Was auf dieser Maschine installiert ist - aus pacman, nicht aus einer
    Datei."""
    if not BASH.is_file():
        raise SystemExit(f"MSYS2 fehlt ({BASH})")
    roh = subprocess.run([str(BASH), _msys_pfad(HIER / "msys2_lock.sh")],
                         capture_output=True, text=True)
    if roh.returncode != 0:
        raise SystemExit(f"msys2_lock.sh exit {roh.returncode}\n{roh.stderr}")
    aus = {}
    for zeile in roh.stdout.splitlines():
        if not zeile.strip():
            continue
        teile = (zeile.rstrip("\n").split("\t") + ["", "", ""])[:4]
        aus[teile[0]] = {"version": teile[1], "file": teile[2], "sha256": teile[3]}
    return aus


def schreiben() -> int:
    import datetime
    LOCK.write_text(json.dumps({
        "_comment": [
            "Der MSYS2-Stand, auf dem die Windows-Pakete gebaut werden.",
            "",
            "Erzeugt mit: python tools/windows/msys2_lock.py write",
            "Geprueft bei jedem Bau. Weicht eine Version ab, bricht er ab -",
            "eine neue Baseline ist eine Entscheidung, kein Nebeneffekt.",
            "",
            "GRENZE: gesperrt sind die ausdruecklich installierten Pakete und",
            "die Eigentuemer der ausgelieferten DLLs. Die vollstaendige",
            "transitive Closure ist es nicht - siehe #323.",
        ],
        "generated_on": datetime.date.today().isoformat(),
        "packages": dict(sorted(bericht().items())),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    d = _lock_lesen()
    print(f"  Lock geschrieben: {len(d['packages'])} Pakete")
    return 0


def _lock_lesen() -> dict:
    """utf-8-sig, nicht utf-8: wer die Datei unter Windows mit PowerShell
    anfasst, bekommt eine BOM davor, und `json.loads` bricht dann mit einem
    Rueckverfolgungsprotokoll ab, das nach einem kaputten Werkzeug aussieht
    statt nach einer BOM. Gemessen am 2026-09-13 - beim Versuch, genau diese
    Pruefung zu kontrollieren."""
    return json.loads(LOCK.read_text(encoding="utf-8-sig"))


def pruefen() -> int:
    soll = _lock_lesen()["packages"]
    ist = bericht()
    abweichungen = []
    for name, erwartet in sorted(soll.items()):
        da = ist.get(name, {"version": "(nicht installiert)"})
        if da["version"] != erwartet["version"]:
            abweichungen.append(f"    {name}: Lock {erwartet['version']}, "
                                f"installiert {da['version']}")
        elif erwartet["sha256"] and da["sha256"] and da["sha256"] != erwartet["sha256"]:
            abweichungen.append(f"    {name}: gleiche Version, ANDERE Datei")
    for name in sorted(set(ist) - set(soll)):
        abweichungen.append(f"    {name}: nicht im Lock")
    if abweichungen:
        print("  MSYS2 weicht vom Lock ab:", file=sys.stderr)
        print("\n".join(abweichungen), file=sys.stderr)
        print("\n  Der Bau wuerde damit etwas anderes bauen als beim letzten Mal.\n"
              "  Wenn das gewollt ist, ist es eine Entscheidung:\n"
              "    python tools/windows/msys2_lock.py write\n"
              "  und den Unterschied im Commit benennen.", file=sys.stderr)
        return 1
    print(f"  MSYS2-Stand stimmt mit dem Lock ueberein ({len(soll)} Pakete)")
    return 0


if __name__ == "__main__":
    befehl = sys.argv[1] if len(sys.argv) > 1 else "verify"
    raise SystemExit(schreiben() if befehl == "write" else pruefen())
