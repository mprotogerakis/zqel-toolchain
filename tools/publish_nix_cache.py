#!/usr/bin/env python3
"""Einen signierten Binaercache auf dl.zqel.org fuellen.

WARUM ES DEN BRAUCHT - gemessen, nicht geschaetzt:
Von den 157 Store-Pfaden der macOS-creusot-Kette liegen 135 in
cache.nixos.org. Die restlichen 22 nicht, und es sind genau die teuren:
cvc4, cvc5 1.3.1, CoCoALib, why3find, alt-ergo, die Rust-Nightly-Kette. Wer
`nix shell` auf die Flake wirft, uebersetzt sie beim ersten Mal selbst. Das
ist kein Defekt, sondern der Preis dafuer, dass Beweiseridentitaet an Pins
haengt statt an dem, was eine Distribution gerade fuehrt - aber niemand muss
ihn zweimal zahlen.

WARUM NUR DIE LUECKE HOCHGELADEN WIRD:
Ein Substituter wird je Pfad befragt, nicht je Closure. Was cache.nixos.org
schon hat, holt der Nutzer weiter von dort. Gemessen fuer aarch64-darwin:

    ganze Closure        3.36 GB
    nur die Luecke       1.09 GB unkomprimiert, xz grob 0.38 GB

Der Unterschied entscheidet, ob das in die R2-Freistufe passt.

WAS DIE SIGNATUR BEDEUTET:
Ein Substituter, dem jemand vertraut, ist eine lasttragende Stufe: wer den
Schluessel hat, bestimmt, welcher Beweiser bei einem Dritten laeuft. Der
geheime Teil liegt ausschliesslich als CI-Geheimnis vor; der oeffentliche
steht in flake.nix und in der Doku. Wer ihn nicht eintraegt, bekommt von
diesem Cache nichts - nix lehnt unsignierte Pfade ab. Das ist die richtige
Voreinstellung und wird hier nicht umgangen.

    python3 tools/publish_nix_cache.py .#packages.x86_64-linux.creusot-free
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

OEFFENTLICH = "https://cache.nixos.org"
ZIEL = "https://dl.zqel.org"
PRAEFIX = "nix"


def lauf(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=True, text=True, **kw)


def store_pfad(attr: str) -> str:
    """Die Ableitung realisieren und ihren Ausgabepfad nennen."""
    if attr.startswith("/nix/store/"):
        return attr
    aus = subprocess.run(["nix", "build", "--no-link", "--print-out-paths", attr],
                         capture_output=True, text=True)
    if aus.returncode != 0:
        raise SystemExit(f"{attr} laesst sich nicht bauen:\n{aus.stderr[-2000:]}")
    return aus.stdout.strip().splitlines()[-1]


def closure(pfad: str) -> list[str]:
    aus = subprocess.run(["nix", "path-info", "-r", pfad],
                         capture_output=True, text=True, check=True)
    return [z for z in aus.stdout.split("\n") if z.startswith("/nix/store/")]


def _hash(pfad: str) -> str:
    return pfad.split("/nix/store/")[1].split("-")[0]


def schon_oeffentlich(pfade: list[str]) -> set[str]:
    """Welche Hashes cache.nixos.org bereits fuehrt.

    Bei einem Netzfehler gilt ein Pfad als NICHT vorhanden. Lieber einmal zu
    viel hochgeladen als eine Luecke, die niemand bemerkt - der Fehler faellt
    sonst erst dem auf, der den Cache benutzt.
    """
    da = set()
    for p in pfade:
        h = _hash(p)
        try:
            req = urllib.request.Request(f"{OEFFENTLICH}/{h}.narinfo", method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as a:
                if a.status == 200:
                    da.add(h)
        except urllib.error.HTTPError:
            pass
        except OSError as e:
            print(f"    (unklar fuer {h}: {type(e).__name__} - wird hochgeladen)")
    return da


def lies_narinfos(ordner: pathlib.Path) -> dict[str, dict]:
    """Hash -> {datei, nar, signiert}."""
    raus = {}
    for f in sorted(ordner.glob("*.narinfo")):
        felder = {}
        for zeile in f.read_text(encoding="utf-8").splitlines():
            if ": " in zeile:
                k, v = zeile.split(": ", 1)
                felder.setdefault(k, v)
        pfad = felder.get("StorePath", "")
        if not pfad:
            continue
        raus[_hash(pfad)] = {
            "datei": f,
            "nar": felder.get("URL", ""),
            "signiert": bool(felder.get("Sig")),
        }
    return raus


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("attrs", nargs="+", help="Flake-Attribute oder Store-Pfade")
    ap.add_argument("--key", default=os.environ.get("NIX_SIGNING_KEY_FILE", ""),
                    help="Datei mit dem geheimen Signaturschluessel")
    ap.add_argument("--out", default="build/nix-cache")
    ap.add_argument("--alles", action="store_true",
                    help="auch hochladen, was cache.nixos.org schon hat")
    ap.add_argument("--nur-messen", action="store_true",
                    help="nichts hochladen, nur sagen was noetig waere")
    args = ap.parse_args(argv)

    if not args.nur_messen and not args.key:
        raise SystemExit(
            "Ohne --key wuerde ein UNSIGNIERTER Cache entstehen. nix lehnt den "
            "beim Nutzer ab, und zwar zu Recht. Setze NIX_SIGNING_KEY_FILE.")
    if args.key and not pathlib.Path(args.key).is_file():
        raise SystemExit(f"Signaturschluessel nicht da: {args.key}")

    alle: list[str] = []
    for attr in args.attrs:
        p = store_pfad(attr)
        print(f"  {attr} -> {p}")
        alle.extend(closure(p))
    alle = sorted(set(alle))
    print(f"\n  Closure: {len(alle)} Pfade")

    if args.alles:
        luecke = {_hash(p) for p in alle}
    else:
        da = schon_oeffentlich(alle)
        luecke = {_hash(p) for p in alle} - da
        print(f"  davon in {OEFFENTLICH}: {len(da)}")
    print(f"  hochzuladen: {len(luecke)}")

    if args.nur_messen:
        for p in alle:
            if _hash(p) in luecke:
                print(f"    {p.split('-', 1)[-1]}")
        return 0

    out = pathlib.Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # nix schreibt hier die NARs, die narinfos UND nix-cache-info. Signiert
    # wird beim Schreiben, nicht nachtraeglich.
    ziel = f"file://{out.resolve()}?compression=xz&secret-key={args.key}"
    for attr in args.attrs:
        lauf(["nix", "copy", "--to", ziel, store_pfad(attr)])

    narinfos = lies_narinfos(out)
    unsigniert = [h for h, v in narinfos.items() if not v["signiert"]]
    if unsigniert:
        raise SystemExit(
            f"{len(unsigniert)} Pfade wurden nicht signiert - der Cache waere "
            "fuer den Nutzer wertlos. Stimmt der Schluessel?")

    hochladen = [out / "nix-cache-info"]
    nars = []
    for h in sorted(luecke):
        eintrag = narinfos.get(h)
        if eintrag is None:
            print(f"    (kein narinfo fuer {h} - uebersprungen)")
            continue
        hochladen.append(eintrag["datei"])
        if eintrag["nar"]:
            nars.append(out / eintrag["nar"])

    bytes_ = sum(f.stat().st_size for f in hochladen + nars if f.exists())
    print(f"\n  {len(hochladen)} narinfo + {len(nars)} NAR, zusammen "
          f"{bytes_/1048576:.1f} MB")

    # ERST DIE NARs, DANN DIE NARINFOS. Die Reihenfolge ist nicht beliebig.
    #
    # Ein narinfo ist das Versprechen "diesen Pfad habe ich, hol ihn unter
    # dieser URL". Liegt es vor seinem NAR, verspricht der Cache waehrend des
    # ganzen Uploads etwas, das er nicht liefern kann - und bricht der Lauf
    # dazwischen ab, bleibt es dauerhaft so. Am 2026-09-14 waehrend des
    # Darwin-Laufs von aussen gemessen: narinfo 200, NAR 404.
    #
    # Andersherum ist der Zwischenstand harmlos: ein NAR, auf das noch kein
    # narinfo zeigt, findet niemand und stoert niemanden.
    if nars:
        lauf([sys.executable, "tools/publish_r2.py", "--prefix", f"{PRAEFIX}/nar",
              *[str(f) for f in nars]])
    lauf([sys.executable, "tools/publish_r2.py", "--prefix", PRAEFIX,
          *[str(f) for f in hochladen]])

    print(f"\n  Substituter: {ZIEL}/{PRAEFIX}")
    print("  Der oeffentliche Schluessel steht in flake.nix (nixConfig).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
