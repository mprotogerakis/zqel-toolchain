#!/usr/bin/env python3
"""Traegt das Paket dieselben Bytes wie das, was oeffentlich liegt?

WOZU (gemessen am 2026-09-21, Lauf #92):
Der woechentliche Lauf hat gappa neu gebaut. Auf R2 blieb das Zip vom 17.09.
liegen - `tools/` ist dort unveraenderlich, und das ist richtig so. Nach
Chocolatey ging das Paket vom 21.09. trotzdem durch, weil ein Paket in
Moderation ersetzt werden DARF. Danach trugen die beiden verschiedene
gappa.exe, und VERIFICATION.txt im Paket forderte den Moderator auf, genau
sie zu vergleichen. Er hat es getan und das Paket zurueckgestellt.

Niemand hatte das entschieden. Der Cron hat es getan.

Das ist kein Chocolatey-Problem und kein R2-Problem, sondern die Stelle
dazwischen: zwei Ablageorte mit verschiedener Veraenderlichkeit, und eine
Zusage im Paket, die sie aneinander bindet. Wer die Zusage macht, muss sie
vor dem Einreichen pruefen.

Verglichen werden BYTES, nicht die .sha256-Beilage daneben: die Beilage ist
eine zweite Datei und kann selbst veralten - genau das ist am 2026-09-17
passiert, als zwei Beilagen ohne ihre Dateien auf R2 lagen.

Exit 0 = dasselbe, einreichen.
Exit 1 = etwas anderes, NICHT einreichen (kein Fehler, der Normalfall beim
         woechentlichen Lauf).
Exit 2 = nicht feststellbar. Dann wird auch nicht eingereicht, aber laut.

Aufruf:
    python tools/windows/dasselbe_wie_draussen.py --werkzeug gappa --dist dist/gappa
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import urllib.error
import urllib.request
import uuid

WURZEL = pathlib.Path(__file__).resolve().parents[2]


def oeffentliche_zip_adresse(werkzeug: str) -> str:
    """Die eine Adresse, unter der das Zip liegt - aus toolchain_adressen.py.

    Nicht hier zusammengesetzt: dieselbe Ableitung stand schon einmal zweimal
    im Baum, und die zweite Stelle driftete.
    """
    sys.path.insert(0, str(WURZEL / "tools"))
    from toolchain_adressen import adressen, alle

    zips = [a for a in adressen(alle()[werkzeug]) if a.endswith(".zip")]
    if len(zips) != 1:
        raise SystemExit(f"{werkzeug}: genau eine Zip-Adresse erwartet, {len(zips)} gefunden")
    return zips[0]


def hole(url: str) -> bytes:
    # Mit Cache-Buster, aus demselben Grund wie in publish_r2.py: dl.zqel.org
    # liegt hinter Cloudflare, und ein Cache weiss nichts von einer Loeschung.
    req = urllib.request.Request(
        f"{url}?nocache={uuid.uuid4().hex}",
        headers={"User-Agent": "zqel-dasselbe-wie-draussen",
                 "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=300) as antwort:
        return antwort.read()


def urteil(werkzeug: str, dist: pathlib.Path) -> int:
    url = oeffentliche_zip_adresse(werkzeug)
    hier = dist / url.rsplit("/", 1)[-1]
    if not hier.is_file():
        print(f"  {hier} gibt es nicht - vor dem Einreichen wird gebaut")
        return 2
    try:
        draussen = hole(url)
    except (urllib.error.URLError, OSError) as fehler:
        print(f"  {url} ist nicht lesbar ({type(fehler).__name__}: {fehler})")
        return 2

    a = hashlib.sha256(hier.read_bytes()).hexdigest()
    b = hashlib.sha256(draussen).hexdigest()
    print(f"  hier:     {a}  {hier.name}")
    print(f"  draussen: {b}  {url}")
    if a == b:
        print("  dasselbe - das Paket darf eingereicht werden")
        return 0
    print("  NICHT dasselbe. Auf R2 liegt ein anderer Bau, und dort bleibt er")
    print("  liegen (tools/ ist unveraenderlich). Ein Paket, dessen")
    print("  VERIFICATION.txt auf dieses Zip zeigt, waere falsch.")
    print("  Wer diesen Bau veroeffentlichen will, loescht die Adressen unter")
    print(f"  {url.rsplit('/', 1)[0]}/ von Hand und faehrt den Lauf erneut.")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--werkzeug", required=True, help="gappa / matiec")
    ap.add_argument("--dist", required=True, help="Verzeichnis mit dem gebauten Zip")
    args = ap.parse_args(argv)
    return urteil(args.werkzeug, pathlib.Path(args.dist))


if __name__ == "__main__":
    raise SystemExit(main())
