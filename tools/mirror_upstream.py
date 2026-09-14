#!/usr/bin/env python3
"""Fremdartefakte spiegeln - hashgeprueft, lizenzgeprueft, unveraendert.

    python tools/mirror_upstream.py --out build/mirror           # nur holen
    python tools/mirror_upstream.py --out build/mirror --publish # und hochladen

WAS DAS SOLL:
Die forgejo-Registry loest auf eine private Adresse auf; wer nicht im HSD-Netz
sitzt, kommt an nichts heran. dl.zqel.org ist der oeffentliche Weg, und dorthin
gehoert alles, was ein Nutzer braucht - auch das, was wir nicht selbst bauen.

WAS DAS NICHT TUT:
Umpacken. Die Archive gehen byteweise unveraendert raus. Was hinzukommt, ist
ein Beipackzettel daneben. Ein umgepacktes Archiv waere eine Bearbeitung, und
dann gaelten andere Pflichten als die der blossen Weitergabe.

WARUM ES DIE LIZENZPRUEFUNG GIBT:
"Die Lizenzdatei liegt irgendwo im Archiv" ist als Zusicherung wertlos, solange
sie niemand nachsieht. mirror-pin.json nennt je Artefakt die Dateien, die drin
liegen MUESSEN; hier wird nachgesehen. Fehlt eine, bricht der Lauf ab - vor dem
Hochladen, nicht danach.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tarfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIN = ROOT / "mirror-pin.json"


def _sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for stueck in iter(lambda: f.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


def hole(url: str, ziel: pathlib.Path, erwartet: str, groesse: int = -1) -> None:
    """Holen und gegen den Pin pruefen. Eine abweichende Datei fliegt raus,
    statt beim naechsten Lauf als 'schon da' zu gelten."""
    if ziel.exists() and _sha256(ziel) == erwartet:
        print(f"  {ziel.name:46s} schon da, Hash stimmt")
        return
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=600) as antwort, ziel.open("wb") as f:
        while stueck := antwort.read(1 << 20):
            f.write(stueck)
    got = _sha256(ziel)
    if got != erwartet:
        ziel.unlink()
        raise SystemExit(
            f"{ziel.name}: Hash weicht ab.\n  erwartet: {erwartet}\n  bekommen: {got}\n"
            "Upstream hat das Artefakt ersetzt oder etwas ist dazwischen. Der Pin "
            "entscheidet, nicht der Server.")
    if groesse >= 0 and ziel.stat().st_size != groesse:
        raise SystemExit(f"{ziel.name}: {ziel.stat().st_size} Bytes, Pin sagt {groesse}")
    print(f"  {ziel.name:46s} {ziel.stat().st_size/1048576:7.1f} MB  geholt und geprueft")


def inhalt(archiv: pathlib.Path) -> list[str]:
    """Die Dateiliste eines Archivs, ohne es auszupacken."""
    if archiv.suffix == ".zip":
        with zipfile.ZipFile(archiv) as z:
            return z.namelist()
    if archiv.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archiv, "r:gz") as t:
            return t.getnames()
    return []          # .msi und anderes: von aussen nicht durchsehbar


def pruefe_lizenzdateien(archiv: pathlib.Path, verlangt: list[str]) -> None:
    if not verlangt:
        return
    drin = set(inhalt(archiv))
    if not drin:
        raise SystemExit(
            f"{archiv.name}: der Pin nennt Lizenzdateien im Archiv, aber das "
            "Format laesst sich nicht durchsehen - dann gehoert der Text als "
            "Beipackzettel daneben, nicht als Verweis hinein.")
    fehlen = [f for f in verlangt if f not in drin]
    if fehlen:
        raise SystemExit(
            f"{archiv.name}: diese Lizenzdateien nennt der Pin, das Archiv "
            f"enthaelt sie nicht: {', '.join(fehlen)}\n"
            "Entweder hat Upstream umgebaut, oder der Pin war nie richtig. "
            "Weitergeben ohne sie kommt nicht in Frage.")
    print(f"  {archiv.name:46s} {len(verlangt)} Lizenzdatei(en) nachgewiesen")


def beipackzettel(werkzeug: str, meta: dict, name: str, art: dict,
                  ziel: pathlib.Path) -> pathlib.Path:
    """Was neben dem Archiv liegt: Herkunft, Hash, Lizenzlage - und der Satz,
    dass wir nichts veraendert haben."""
    zeilen = [
        f"{name}",
        "=" * len(name),
        "",
        "Dies ist eine unveraenderte Kopie eines fremden Artefakts.",
        "",
        f"Werkzeug:   {werkzeug} {meta['version']}",
        f"Upstream:   {meta['upstream']}",
        f"Bezogen von: {art['url']}",
        f"sha256:     {art['sha256']}",
        f"Groesse:    {art['size']} Bytes",
        f"Lizenz:     {meta['spdx']}",
        "",
        "Hinweis zur Lizenz",
        "------------------",
        meta["_licence_note"],
        "",
    ]
    if art.get("licence_files_inside"):
        zeilen += ["Im Archiv enthaltene Lizenztexte (beim Spiegeln nachgewiesen):"]
        zeilen += [f"  {f}" for f in art["licence_files_inside"]]
        zeilen += [""]
    if meta.get("licence_sidecar"):
        zeilen += [f"Lizenztext liegt daneben: {meta['licence_sidecar']['name']}", ""]
    zeilen += [
        "Warum wir das spiegeln",
        "----------------------",
        "Unsere interne Registry ist von aussen nicht erreichbar. Damit ein",
        "Nutzer ohne Netzzugang zur Hochschule alles an einer Stelle findet,",
        "liegt hier eine Kopie. Sie ist byteweise dieselbe Datei wie beim",
        "Upstream - der Hash oben ist der Beleg, und der Upstream bleibt die",
        "Quelle, wenn diese Kopie einmal nicht mehr da ist.",
        "",
    ]
    p = ziel / f"{name}.notice.txt"
    p.write_text("\n".join(zeilen), encoding="ascii", errors="replace")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="build/mirror")
    ap.add_argument("--publish", action="store_true",
                    help="nach dem Pruefen nach R2 hochladen")
    ap.add_argument("--only", default=None, help="nur dieses Werkzeug")
    args = ap.parse_args(argv)

    pin = json.loads(PIN.read_text(encoding="utf-8"))
    out = pathlib.Path(args.out)
    hochzuladen: dict[str, list[pathlib.Path]] = {}

    for werkzeug, meta in pin["tools"].items():
        if args.only and werkzeug != args.only:
            continue
        print(f"[{werkzeug} {meta['version']}] {meta['spdx']}")
        ordner = out / werkzeug / meta["version"]
        ordner.mkdir(parents=True, exist_ok=True)
        dateien = []
        for name, art in meta["artifacts"].items():
            f = ordner / name
            hole(art["url"], f, art["sha256"], art["size"])
            pruefe_lizenzdateien(f, art.get("licence_files_inside", []))
            (ordner / f"{name}.sha256").write_text(f"{art['sha256']}  {name}\n")
            dateien += [f, ordner / f"{name}.sha256",
                        beipackzettel(werkzeug, meta, name, art, ordner)]
        sc = meta.get("licence_sidecar")
        if sc:
            f = ordner / sc["name"]
            hole(sc["url"], f, sc["sha256"])
            dateien.append(f)
        hochzuladen[f"tools/{werkzeug}/{meta['version']}"] = dateien

    if not args.publish:
        print("\nnur geholt und geprueft (--publish laedt hoch)")
        return 0

    import publish_r2
    for prefix, dateien in hochzuladen.items():
        print(f"\n-> {prefix}")
        publish_r2.main([*sum((["--prefix", prefix], []), []),
                         *[str(f) for f in dateien]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
