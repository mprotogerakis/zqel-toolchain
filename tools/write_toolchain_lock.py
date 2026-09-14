#!/usr/bin/env python3
"""Was diese Werkzeugkette liefert, als EINE Datei, die andere lesen koennen.

WOZU:
Solange Pins und Konsument im selben Commit lagen, war die Bindung zwischen
"dieses Verdikt" und "dieser Beweiser" trivial. Seit die Werkzeugkette ein
eigenes Repository ist, laeuft sie ueber eine Repositoriumsgrenze - und eine
Grenze, ueber die nur Vertrauen geht, ist keine Bindung.

`toolchain-lock.json` ist diese Bindung: eine erzeugte, inhaltsadressierte
Aufstellung dessen, was hier veroeffentlicht ist. zqel legt sie sich in den
Baum und prueft dagegen. Aendert sich hier etwas, ohne dass die Datei drueben
mitgeht, faellt es auf - statt still zu driften.

WAS DRINSTEHT UND WAS NICHT:
Versionen, Lizenzen, die fertigen Adressen, der Flake-Hash und der
Cache-Schluessel. NICHT die Hashes der Artefakte - die stehen in
mirror-pin.json und gehoeren dorthin; diese Datei sagt, WAS es gibt, nicht
WORAUS es besteht.

    python3 tools/write_toolchain_lock.py --out toolchain-lock.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.request

WURZEL = pathlib.Path(__file__).resolve().parent.parent
BASIS = "https://dl.zqel.org"


def _flake_config() -> dict:
    """Substituter und oeffentlicher Schluessel - aus flake.nix, nicht doppelt.

    Sie stehen dort, weil nix sie dort liest. Sie hier erneut zu tippen waere
    eine zweite Wahrheit, die irgendwann abweicht.
    """
    text = (WURZEL / "flake.nix").read_text(encoding="utf-8")
    subs = re.findall(r'extra-substituters\s*=\s*\[\s*"([^"]+)"', text)
    keys = re.findall(r'"([A-Za-z0-9_.:-]+-\d:[A-Za-z0-9+/=]+)"', text)
    if not subs or not keys:
        raise SystemExit("flake.nix nennt keinen Substituter oder keinen Schluessel")
    return {"substituter": subs[0], "public_key": keys[0]}


def _aktueller_flake_hash() -> str | None:
    """Der zuletzt veroeffentlichte Stand - Navigation, nicht Identitaet.

    Steht mit genau diesem Vermerk in der Datei. Wer ein Verdikt bindet,
    nennt den Hash, nicht diese Zeile.
    """
    # MIT eigenem User-Agent. Gemessen am 2026-09-14: Cloudflare weist den
    # Vorgabewert von python-urllib mit 403 ab, ein eigener bekommt 200. Ohne
    # ihn lieferte diese Funktion still None, und die Datei trug keinen Hash -
    # ein Fehlschlag, den niemand bemerkt haette.
    req = urllib.request.Request(f"{BASIS}/flake/latest.json",
                                 headers={"User-Agent": "zqel-toolchain-lock"})
    try:
        with urllib.request.urlopen(req, timeout=30) as a:
            return json.loads(a.read()).get("sha256")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None          # noch nichts veroeffentlicht - zulaessig
        raise SystemExit(f"latest.json antwortet mit HTTP {e.code}")
    except OSError as e:
        raise SystemExit(f"latest.json ist nicht erreichbar: {type(e).__name__}: {e}")


def _commit() -> str:
    fuer_ci = os.environ.get("GITHUB_SHA")
    if fuer_ci:
        return fuer_ci
    aus = subprocess.run(["git", "-C", str(WURZEL), "rev-parse", "HEAD"],
                         capture_output=True, text=True)
    return aus.stdout.strip() if aus.returncode == 0 else ""


def sammle() -> dict:
    werkzeuge: dict[str, dict] = {}

    spiegel = json.loads((WURZEL / "mirror-pin.json").read_text(encoding="utf-8"))
    for name, t in sorted(spiegel["tools"].items()):
        version = t["version"]
        dateien = sorted((t.get("artifacts") or {}))
        beilagen = [f"{d}.notice.txt" for d in dateien]
        werkzeuge[name] = {
            "version": version,
            "spdx": t.get("spdx", ""),
            "upstream": t.get("upstream", ""),
            "herkunft": "gespiegelt",
            "dateien": [f"{BASIS}/tools/{name}/{version}/{d}"
                        for d in dateien + beilagen],
        }

    # Selbst gebaute Werkzeuge, sobald ihre Pins hier liegen. Fehlt einer,
    # wird er NICHT stillschweigend ausgelassen - er taucht dann in der Datei
    # gar nicht auf, und der Test drueben merkt es.
    for pin, name in (("gappa-pin.json", "gappa"), ("matiec-pin.json", "matiec")):
        p = WURZEL / pin
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        version = d["version"]
        if d.get("revision"):
            version = f"{version}-{d['revision'][:7]}"
        werkzeuge[name] = {
            "version": version,
            "spdx": (d.get("windows_build", {}).get("tool_licence", {}) or {}).get("spdx", ""),
            "upstream": d.get("upstream_project", ""),
            "herkunft": "selbst gebaut",
            "dateien": [],   # wird vom Windows-Bau gefuellt
        }

    return {
        "_comment": (
            "Erzeugt von tools/write_toolchain_lock.py in "
            "mprotogerakis/zqel-toolchain. Nicht von Hand bearbeiten - die "
            "Wahrheit stehen in den Pins und in flake.nix."),
        "_hinweis_flake": (
            "aktueller_flake_hash ist NAVIGATION. Wer ein Verdikt bindet, "
            "nennt den Hash ausdruecklich; diese Zeile bewegt sich."),
        "schema": 1,
        "erzeugt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "quell_commit": _commit(),
        "cache": _flake_config(),
        "aktueller_flake_hash": _aktueller_flake_hash(),
        "werkzeuge": werkzeuge,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="toolchain-lock.json")
    ap.add_argument("--pruefen", action="store_true",
                    help="nicht schreiben, nur melden ob die Datei aktuell ist")
    args = ap.parse_args(argv)

    neu = sammle()
    ziel = pathlib.Path(args.out)

    if args.pruefen:
        if not ziel.exists():
            raise SystemExit(f"{ziel} gibt es nicht")
        alt = json.loads(ziel.read_text(encoding="utf-8"))
        # Zeitstempel, Commit und der bewegliche Flake-Hash zaehlen nicht -
        # sonst waere die Datei bei jedem Lauf "veraltet".
        beweglich = ("erzeugt", "quell_commit", "aktueller_flake_hash")
        a = {k: v for k, v in alt.items() if k not in beweglich}
        b = {k: v for k, v in neu.items() if k not in beweglich}
        if a != b:
            raise SystemExit(
                f"{ziel} passt nicht mehr zu den Pins. Neu erzeugen:\n"
                f"  python3 tools/write_toolchain_lock.py --out {ziel}")
        print(f"  {ziel} ist aktuell ({len(neu['werkzeuge'])} Werkzeuge)")
        return 0

    ziel.write_text(json.dumps(neu, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(f"  {ziel}: {len(neu['werkzeuge'])} Werkzeuge, "
          f"{sum(len(w['dateien']) for w in neu['werkzeuge'].values())} Adressen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
