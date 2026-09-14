#!/usr/bin/env python3
"""Was dl.zqel.org WIRKLICH ausliefert, gegen das, was die Pins zusagen.

DIE LUECKE, DIE DAS SCHLIESST:
`mirror_upstream.py` prueft den Hash des HERUNTERGELADENEN Artefakts, bevor es
hochlaedt. Danach prueft niemand mehr etwas. Ein abgebrochener Upload, ein
ueberschriebener Schluessel, eine Datei, die nie ankam - all das faellt erst
dem auf, der sie benutzt. Genau die Seite, von der aus hier bisher niemand
geschaut hat.

WAS GEPRUEFT WIRD:
  * jedes Artefakt aus mirror-pin.json ist unter seiner oeffentlichen Adresse
    abrufbar, und seine Groesse stimmt mit dem Pin ueberein
  * die `.notice.txt` daneben existiert - ohne sie geben wir fremde Binaries
    ohne ihren Lizenzhinweis weiter, und das ist kein Schoenheitsfehler
  * mit --hash zusaetzlich: der ausgelieferte Inhalt ergibt den gepinnten
    SHA-256. Das laedt alles herunter (rund 600 MB) und ist deshalb nicht der
    Vorgabefall.

Ohne Anmeldung, nur stdlib. Laeuft auf jeder Maschine mit Python - auch auf
einer, die unser Netz nie gesehen hat.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

BASIS = "https://dl.zqel.org/tools"
ZEIT = 120

_stand = {"gut": 0, "schlecht": 0}


def sagt(ok: bool, satz: str, zusatz: str = "") -> None:
    _stand["gut" if ok else "schlecht"] += 1
    print(f"  [{'ok ' if ok else 'FEHL'}] {satz}" + (f"\n         {zusatz}" if zusatz else ""))


def _anfrage(url: str, methode: str = "GET"):
    return urllib.request.Request(url, method=methode,
                                  headers={"User-Agent": "zqel-mirror-check"})


def kopf(url: str):
    """(Status, Groesse) ohne den Koerper zu holen."""
    try:
        with urllib.request.urlopen(_anfrage(url, "HEAD"), timeout=ZEIT) as a:
            return a.status, int(a.headers.get("Content-Length") or -1)
    except urllib.error.HTTPError as e:
        return e.code, -1
    except OSError as e:
        return f"{type(e).__name__}", -1


def stromhash(url: str) -> str:
    """SHA-256 im Vorbeifliegen - nichts wird auf die Platte gelegt."""
    h = hashlib.sha256()
    with urllib.request.urlopen(_anfrage(url), timeout=ZEIT) as a:
        while stueck := a.read(1 << 20):
            h.update(stueck)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pin", default=str(pathlib.Path(__file__).resolve().parent.parent
                                         / "mirror-pin.json"))
    ap.add_argument("--hash", action="store_true",
                    help="den Inhalt wirklich durchrechnen (laedt alles herunter)")
    ap.add_argument("--nur", help="nur dieses Werkzeug pruefen")
    args = ap.parse_args(argv)

    pins = json.loads(pathlib.Path(args.pin).read_text(encoding="utf-8"))["tools"]
    print("\n  Der oeffentliche Spiegel gegen die Pins\n")

    for werkzeug, t in sorted(pins.items()):
        if args.nur and werkzeug != args.nur:
            continue
        version = t["version"]
        for datei, a in sorted((t.get("artifacts") or {}).items()):
            url = f"{BASIS}/{werkzeug}/{version}/{datei}"
            status, groesse = kopf(url)
            if status != 200:
                sagt(False, f"{werkzeug}/{datei}", f"HTTP {status} auf {url}")
                continue
            erwartet = int(a["size"])
            if groesse != erwartet:
                sagt(False, f"{werkzeug}/{datei}",
                     f"{groesse} Bytes ausgeliefert, {erwartet} gepinnt")
                continue
            if args.hash:
                ist = stromhash(url)
                if ist != a["sha256"]:
                    sagt(False, f"{werkzeug}/{datei}",
                         f"sha256 {ist[:16]}... statt {a['sha256'][:16]}...")
                    continue
                sagt(True, f"{werkzeug}/{datei}  {groesse} B, sha256 stimmt")
            else:
                sagt(True, f"{werkzeug}/{datei}  {groesse} B")

            # Ohne den Hinweis geben wir ein fremdes Binary ohne seine Lizenz
            # weiter. Das ist keine Formalie, sondern die Bedingung, unter der
            # wir es ueberhaupt weitergeben duerfen.
            hinweis = f"{url}.notice.txt"
            hs, _ = kopf(hinweis)
            sagt(hs == 200, f"{werkzeug}/{datei}.notice.txt",
                 "" if hs == 200 else f"HTTP {hs} - Weitergabe ohne Lizenzhinweis")

    print(f"\n  {_stand['gut']} bestanden, {_stand['schlecht']} nicht.")
    if not args.hash:
        print("  (ohne --hash wurde nur Erreichbarkeit und Groesse geprueft)")
    return 1 if _stand["schlecht"] else 0


if __name__ == "__main__":
    sys.exit(main())
