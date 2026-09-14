#!/usr/bin/env python3
"""Antwortet der Cache einem Fremden - und ist seine Antwort signiert?

WARUM DAS EINEN EIGENEN PRUEFER BRAUCHT:
Ein Cache, den nur der befragt, der ihn gefuellt hat, ist eine Behauptung.
Der Upload kann gelingen und die Adresse trotzdem nichts liefern: ein falsches
Praefix, ein NAR, das nie ankam, ein narinfo ohne Signatur. All das faellt
sonst erst dem auf, der ihn benutzt - und der merkt nur, dass sein Bau wieder
Stunden dauert, ohne zu wissen warum.

WAS GEPRUEFT WIRD:
  * nix-cache-info ist da und nennt /nix/store als StoreDir - ohne das haelt
    nix die Adresse fuer keinen Cache
  * fuer jeden Pfad der Closure, den cache.nixos.org NICHT hat, liegt bei uns
    ein narinfo
  * jedes dieser narinfos traegt eine Sig-Zeile mit unserem Schluesselnamen -
    ein unsigniertes lehnt nix beim Nutzer ab, und dann war die Muehe umsonst
  * das NAR, auf das es zeigt, ist abrufbar

Ohne Anmeldung, nur stdlib. Laeuft auf jeder Maschine mit Python.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.error
import urllib.request

OEFFENTLICH = "https://cache.nixos.org"
UNSERER = "https://dl.zqel.org/nix"
SCHLUESSELNAME = "dl.zqel.org-1"

_stand = {"gut": 0, "schlecht": 0}


def sagt(ok: bool, satz: str, zusatz: str = "") -> None:
    _stand["gut" if ok else "schlecht"] += 1
    print(f"  [{'ok ' if ok else 'FEHL'}] {satz}" + (f"\n         {zusatz}" if zusatz else ""))


def hole(url: str, methode: str = "GET"):
    req = urllib.request.Request(url, method=methode,
                                 headers={"User-Agent": "zqel-cache-check"})
    with urllib.request.urlopen(req, timeout=60) as a:
        return a.status, (a.read() if methode == "GET" else b"")


def da(url: str) -> bool:
    try:
        status, _ = hole(url, "HEAD")
        return status == 200
    except (urllib.error.HTTPError, OSError):
        return False


def _hash(pfad: str) -> str:
    return pfad.split("/nix/store/")[1].split("-")[0]


def closure(attr: str) -> list[str]:
    if attr.startswith("/nix/store/"):
        pfad = attr
    else:
        aus = subprocess.run(["nix", "build", "--no-link", "--print-out-paths", attr],
                             capture_output=True, text=True)
        if aus.returncode != 0:
            # NICHT dem Cache die Schuld geben, wenn der Aufruf schuld ist.
            #
            # `verify_nix_cache.py creusot-free` (ohne `.#`) meldete
            # "creusot-free liegt hier nicht vor" - als fehlte etwas in der
            # Ablage. In Wahrheit hat nix das FLAKE nicht gefunden. Genau der
            # Fall, in dem eine Probe den Benutzer beschuldigt, statt zu
            # sagen, was sie meint.
            fehler = aus.stderr[-1500:]
            if "in the flake registries" in fehler or "cannot find flake" in fehler:
                raise SystemExit(
                    f"{attr!r} ist kein Flake-Attribut, das nix aufloesen kann.\n"
                    f"Gemeint war vermutlich '.#{attr}' - dieses Werkzeug "
                    f"erwartet die Flake-Schreibweise oder einen Store-Pfad.\n"
                    f"Der Cache wurde dabei gar nicht befragt.\n{fehler}")
            raise SystemExit(
                f"{attr} laesst sich hier nicht bauen - der Cache wurde noch "
                f"nicht befragt:\n{fehler}")
        pfad = aus.stdout.strip().splitlines()[-1]
    aus = subprocess.run(["nix", "path-info", "-r", pfad],
                         capture_output=True, text=True, check=True)
    return [z for z in aus.stdout.split("\n") if z.startswith("/nix/store/")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("attrs", nargs="+")
    ap.add_argument("--base", default=UNSERER)
    args = ap.parse_args(argv)

    print(f"\n  Der Cache unter {args.base}, von aussen befragt\n")

    try:
        status, roh = hole(f"{args.base}/nix-cache-info")
        text = roh.decode("utf-8", "replace")
        sagt("StoreDir: /nix/store" in text, "nix-cache-info nennt /nix/store",
             "" if "StoreDir" in text else text[:120])
    except (urllib.error.HTTPError, OSError) as e:
        sagt(False, "nix-cache-info ist abrufbar", f"{type(e).__name__}: {e}")
        print("\n  Ohne diese Datei haelt nix die Adresse fuer keinen Cache.")
        return 1

    pfade = []
    for attr in args.attrs:
        pfade.extend(closure(attr))
    pfade = sorted(set(pfade))

    # Nur das pruefen, was wir ueberhaupt tragen muessen. Was upstream hat,
    # ist nicht unsere Zusage.
    unsere = [p for p in pfade if not da(f"{OEFFENTLICH}/{_hash(p)}.narinfo")]
    print(f"  Closure {len(pfade)} Pfade, davon von uns zu tragen: {len(unsere)}\n")
    if not unsere:
        sagt(False, "nichts zu pruefen",
             "entweder ist die Closure leer oder upstream hat schon alles - "
             "dann misst dieser Lauf nichts")
        return 1

    for p in unsere:
        h = _hash(p)
        name = p.split("-", 1)[-1]
        try:
            status, roh = hole(f"{args.base}/{h}.narinfo")
        except (urllib.error.HTTPError, OSError) as e:
            sagt(False, name, f"kein narinfo: {type(e).__name__} {e}")
            continue
        felder = dict(z.split(": ", 1) for z in roh.decode().splitlines() if ": " in z)
        sig = felder.get("Sig", "")
        if not sig.startswith(SCHLUESSELNAME + ":"):
            sagt(False, name, f"Signatur fehlt oder fremder Schluessel: {sig[:40] or '(keine)'}")
            continue
        nar = felder.get("URL", "")
        if not nar or not da(f"{args.base}/{nar}"):
            sagt(False, name, f"NAR nicht abrufbar: {nar or '(keine URL)'}")
            continue
        sagt(True, f"{name}  signiert, NAR da")

    print(f"\n  {_stand['gut']} bestanden, {_stand['schlecht']} nicht.")
    return 1 if _stand["schlecht"] else 0


if __name__ == "__main__":
    sys.exit(main())
