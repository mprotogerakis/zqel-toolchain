#!/usr/bin/env python3
"""Die Flake als Tarball - fuer alle, die das Repository nicht haben.

WOZU:
`nix develop github:...` setzt einen Zugang zur Weiterleitung voraus, die wir
nicht kontrollieren. Ein Tarball unter unserer eigenen Adresse setzt nur
voraus, dass jemand HTTPS sprechen kann:

    nix shell 'tarball+https://dl.zqel.org/flake/<sha256>.tar.gz#creusot-free'

WARUM UEBER DEN HASH UND NICHT UEBER `latest`:
Der Name benennt den Inhalt. Wer dieselbe Adresse zweimal aufruft, bekommt
zweimal dasselbe - und ein Verdikt, das unter dieser Adresse entstand, bleibt
nachvollziehbar. `latest` ist Navigation, niemals Beweisidentitaet.

WAS HINEIN GEHOERT - UND WARUM ES NICHT HIER STEHT:
Die Liste wird aus flake.nix ABGELEITET, nicht gepflegt. Eine gepflegte Liste
vergisst irgendwann einen Pfad, und der Tarball scheitert dann erst bei dem,
der ihn benutzt - mit einer Fehlermeldung ueber eine fehlende Datei, die im
Repository laengst existiert.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import pathlib
import re
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Immer dabei, unabhaengig davon, was flake.nix erwaehnt.
GRUNDSTOCK = ("flake.nix", "flake.lock")

#: Ein fester Wurzelname im Archiv. nix entfernt genau eine oberste Ebene;
#: ohne sie landen flake.nix und ein halbes Repository nebeneinander.
WURZEL = "zqel-toolchain"

#: Reproduzierbarkeit: ohne feste Zeit und feste Eigentuemer bekommt derselbe
#: Inhalt zwei verschiedene Hashes, und die Adresse verliert ihre Aussage.
EPOCHE = 0


def referenzierte_pfade(flake_text: str) -> list[str]:
    """Was flake.nix an Pfaden aus dem Baum zieht.

    nix schreibt solche Pfade ohne Anfuehrungszeichen: `./tests/fixtures/...`.
    Gesucht wird deshalb das Literal, nicht eine Zeichenkette.
    """
    treffer = set()
    for m in re.finditer(r"(?<![\w/.])\./([A-Za-z0-9_./-]+)", flake_text):
        p = m.group(1).rstrip(".")
        if p and not p.startswith("configure"):
            treffer.add(p)
    return sorted(treffer)


def sammle(root: pathlib.Path = ROOT) -> list[pathlib.Path]:
    flake = (root / "flake.nix").read_text(encoding="utf-8")
    gewollt = list(GRUNDSTOCK) + referenzierte_pfade(flake)
    dateien: list[pathlib.Path] = []
    for rel in gewollt:
        p = root / rel
        if p.is_dir():
            dateien.extend(sorted(q for q in p.rglob("*") if q.is_file()))
        elif p.is_file():
            dateien.append(p)
        else:
            # Kein stilles Weglassen: ein Pfad, den flake.nix nennt und den es
            # nicht gibt, ist ein Befund ueber flake.nix.
            raise SystemExit(f"flake.nix nennt {rel}, das es nicht gibt")
    # Eindeutig, und in stabiler Reihenfolge - sonst wandert der Hash.
    return sorted(set(dateien))


def packe(ziel: pathlib.Path, root: pathlib.Path = ROOT) -> str:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz", compresslevel=9,
                      format=tarfile.GNU_FORMAT) as tar:
        # mtime der gz-Kopfzeile selbst: tarfile schreibt sonst die Uhrzeit.
        for datei in sammle(root):
            rel = datei.relative_to(root)
            info = tarfile.TarInfo(f"{WURZEL}/{rel.as_posix()}")
            daten = datei.read_bytes()
            info.size = len(daten)
            info.mtime = EPOCHE
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(daten))
    roh = puffer.getvalue()
    # gzip legt die Packzeit in Byte 4..8 ab. Auf Null setzen, sonst ist
    # derselbe Inhalt jedes Mal ein anderer Hash.
    roh = roh[:4] + b"\0\0\0\0" + roh[8:]
    ziel.write_bytes(roh)
    return hashlib.sha256(roh).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="dist", help="Verzeichnis fuer das Archiv")
    ap.add_argument("--print-name", action="store_true",
                    help="nur den Dateinamen ausgeben, fuer die CI")
    args = ap.parse_args(argv)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    vorlaeufig = out / "flake-unbenannt.tar.gz"
    summe = packe(vorlaeufig)
    ziel = out / f"{summe}.tar.gz"
    vorlaeufig.rename(ziel)

    if args.print_name:
        print(ziel.name)
        return 0
    print(f"  {ziel}")
    print(f"  sha256 {summe}")
    print("  nix shell "
          f"'tarball+https://dl.zqel.org/flake/{summe}.tar.gz#creusot-free'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
