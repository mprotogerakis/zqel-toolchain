#!/usr/bin/env python3
"""Die Gegenprobe: geht das alles auch von draussen?

WOZU DIESES SKRIPT UEBERHAUPT EXISTIERT:
Wer die Auslieferung gebaut hat, prueft sie auf der Maschine, auf der er sie
gebaut hat - mit einem Repository daneben, einem vollen /nix/store und den
Zugaengen seiner Organisation. Dann geht alles, und man weiss nichts. Codex hat
im Review genau darauf bestanden: der Nachweis zaehlt von einer fremden,
leeren, anonymen Maschine aus.

Dieses Skript IST dieser Nachweis, in ausfuehrbarer Form. Es braucht nichts
ausser Python und curl-freiem stdlib-HTTP; `--mit-nix` fuegt die Auswertung
hinzu, wenn nix da ist.

    python3 probe_public_toolchain.py
    python3 probe_public_toolchain.py --mit-nix

WAS ES AUSDRUECKLICH NICHT ZEIGT:
Von welchem Netz aus es lief. Das steht am Ende im Klartext - ein Befund, der
seine eigene Reichweite verschweigt, ist die gefaehrliche Sorte.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

BASIS = "https://dl.zqel.org/flake"
ZEIT = 60

_stand = {"gut": 0, "schlecht": 0}


def sagt(ok: bool, satz: str, zusatz: str = "") -> bool:
    _stand["gut" if ok else "schlecht"] += 1
    print(f"  [{'ok ' if ok else 'FEHL'}] {satz}" + (f"\n         {zusatz}" if zusatz else ""))
    return ok


def hole(url: str) -> bytes:
    """Ohne jede Anmeldung - das ist der Punkt.

    Keine Kopfzeile mit Token, kein Netrc, kein Cookie. Wenn das hier klappt,
    klappt es fuer jeden.
    """
    anfrage = urllib.request.Request(url, headers={"User-Agent": "zqel-probe"})
    with urllib.request.urlopen(anfrage, timeout=ZEIT) as antwort:
        return antwort.read()


def pruefe_inputs(lock: dict) -> None:
    """Die Inputs am Tarball, den nix WIRKLICH holt.

    NICHT ueber api.github.com: die drosselt anonyme Aufrufe und meldet dann
    403 fuer alles, auch fuer NixOS/nixpkgs. Genau dieser Instrumentenfehler
    hat am 2026-09-13 fast zu dem Befund "alle Inputs sind privat" gefuehrt.
    """
    for name, knoten in sorted(lock.get("nodes", {}).items()):
        lo = knoten.get("locked", {})
        if lo.get("type") == "github":
            url = f"https://github.com/{lo['owner']}/{lo['repo']}/archive/{lo['rev']}.tar.gz"
        elif lo.get("type") == "tarball":
            url = lo.get("url", "")
        else:
            continue
        try:
            anfrage = urllib.request.Request(url, method="HEAD",
                                             headers={"User-Agent": "zqel-probe"})
            with urllib.request.urlopen(anfrage, timeout=ZEIT) as a:
                sagt(200 <= a.status < 300, f"Input {name} ist anonym erreichbar")
        except urllib.error.HTTPError as e:
            sagt(False, f"Input {name} ist anonym erreichbar", f"HTTP {e.code} auf {url}")
        except OSError as e:
            sagt(False, f"Input {name} ist anonym erreichbar", f"{type(e).__name__} auf {url}")


def mit_nix(archiv: pathlib.Path, leerer_store: bool) -> None:
    if not shutil.which("nix"):
        print("  [--- ] nix ist nicht da - die Auswertung wurde uebersprungen")
        return
    befehl = ["nix", "flake", "metadata", "--json",
              "--extra-experimental-features", "nix-command flakes",
              f"tarball+file://{archiv}"]
    laden = None
    if leerer_store:
        # Ein FRISCHER Store. Sonst beweist ein Treffer nur, dass diese
        # Maschine die Inputs schon einmal geholt hat.
        # .resolve(): auf macOS liefert mkdtemp /var/folders/..., und /var ist
        # ein Symlink auf /private/var. nix verweigert einen Store, dessen
        # Elternpfad ueber einen Symlink laeuft - gemessen, nicht vermutet.
        laden = str(pathlib.Path(tempfile.mkdtemp(prefix="zqel-store-")).resolve())
        befehl[2:2] = ["--store", laden]
    try:
        aus = subprocess.run(befehl, capture_output=True, text=True, timeout=900)
    except subprocess.SubprocessError as e:
        sagt(False, "nix wertet den Tarball aus", str(e))
        return
    if aus.returncode != 0:
        sagt(False, "nix wertet den Tarball aus", (aus.stderr or "").strip()[-400:])
        return
    knoten = json.loads(aus.stdout)["locks"]["nodes"]
    ohne = [n for n, v in knoten.items() if n != "root" and not v.get("locked", {}).get("narHash")]
    sagt(not ohne, f"nix wertet den Tarball aus - {len(knoten)-1} Inputs, alle gelockt",
         f"ohne narHash: {ohne}" if ohne else "")
    if laden:
        print(f"         (in einem frischen Store: {laden})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="Tarball-Adresse; sonst aus latest.json")
    ap.add_argument("--mit-nix", action="store_true", help="auch von nix auswerten lassen")
    ap.add_argument("--frischer-store", action="store_true",
                    help="dabei einen leeren /nix/store benutzen")
    args = ap.parse_args(argv)

    print("\n  Gegenprobe: die zqel-Toolchain von aussen\n")

    url = args.url
    if not url:
        try:
            zeiger = json.loads(hole(f"{BASIS}/latest.json"))
        except (OSError, ValueError) as e:
            sagt(False, "latest.json ist anonym lesbar", f"{type(e).__name__}: {e}")
            return 1
        sagt(True, "latest.json ist anonym lesbar", f"zeigt auf {zeiger['sha256'][:16]}...")
        url = zeiger["url"]

    try:
        roh = hole(url)
    except (OSError, ValueError) as e:
        sagt(False, "der Tarball ist anonym ladbar", f"{type(e).__name__}: {e}")
        return 1
    sagt(True, "der Tarball ist anonym ladbar", f"{len(roh)} Bytes von {url}")

    # DER KERN: der Name benennt den Inhalt. Stimmt das nicht, ist die
    # Adresse keine Identitaet mehr, sondern nur ein Ort.
    erwartet = url.rsplit("/", 1)[-1].removesuffix(".tar.gz")
    tatsaechlich = hashlib.sha256(roh).hexdigest()
    sagt(erwartet == tatsaechlich, "der Name ist der Hash des Inhalts",
         "" if erwartet == tatsaechlich else f"Name {erwartet}, Inhalt {tatsaechlich}")

    with tempfile.TemporaryDirectory() as tmp:
        archiv = pathlib.Path(tmp) / "flake.tar.gz"
        archiv.write_bytes(roh)
        with tarfile.open(archiv) as tar:
            namen = tar.getnames()
            oberste = {n.split("/", 1)[0] for n in namen}
            sagt(len(oberste) == 1, "genau eine oberste Ebene", f"gefunden: {sorted(oberste)}")
            innen = {n.split("/", 1)[1] for n in namen if "/" in n}
            sagt("flake.nix" in innen and "flake.lock" in innen,
                 "flake.nix und flake.lock liegen darin")
            lock = json.loads(tar.extractfile(
                next(n for n in namen if n.endswith("flake.lock"))).read())

        pruefe_inputs(lock)
        if args.mit_nix:
            mit_nix(archiv, args.frischer_store)

    print(f"\n  {_stand['gut']} bestanden, {_stand['schlecht']} nicht.")
    print("\n  WAS DIESER LAUF NICHT ZEIGT:")
    print("  Von welchem Netz aus er lief. Wer die Auslieferung gebaut hat,")
    print("  kann das nicht selbst nachweisen - dafuer braucht es eine Maschine")
    print("  ausserhalb der eigenen Organisation. Genau dafuer gibt es dieses")
    print("  Skript: es ist der Nachweis, den ein Fremder fuehren kann.")
    return 1 if _stand["schlecht"] else 0


if __name__ == "__main__":
    sys.exit(main())
