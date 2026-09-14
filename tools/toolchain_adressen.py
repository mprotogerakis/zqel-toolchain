#!/usr/bin/env python3
"""Welche Adressen ein Werkzeug unter dl.zqel.org hat - an EINER Stelle.

WOZU:
Dieselbe Ableitung stand zweimal im Baum: einmal in
`write_download_table.py` (fuer die Tabelle in der README), einmal - als
leere Liste mit einem Vorsatz - in `write_toolchain_lock.py`. Zwei Stellen,
die dasselbe rechnen, driften; das ist in dieser Woche das haeufigste Muster
gewesen. Hier steht es einmal.

WAS DIE WAHRHEIT IST:
Die Pins. `mirror-pin.json` fuer die gespiegelten Fremdwerkzeuge,
`gappa-pin.json` und `matiec-pin.json` fuer die, die wir selbst bauen. Die
Dateinamen der eigenen Bauten entstehen in `tools/windows/build_*.ps1`; hier
werden sie GENAUSO abgeleitet, damit ein geaenderter Pin beide Verbraucher
mitzieht statt sie still falsch zu machen.
"""
from __future__ import annotations

import json
import pathlib

WURZEL = pathlib.Path(__file__).resolve().parent.parent
BASIS = "https://dl.zqel.org"

#: Was `New-ToolPackage` in tools/windows/win_package.ps1 neben dem Archiv
#: ablegt. Der Installer wird von ISCC gebaut, die .sha256 daneben geschrieben.
WINDOWS_ENDUNGEN = (".zip", ".zip.sha256", "-setup.exe", "-setup.exe.sha256")


def gespiegelt() -> dict[str, dict]:
    """Die Fremdwerkzeuge aus mirror-pin.json, mit ihren Adressen."""
    pin = json.loads((WURZEL / "mirror-pin.json").read_text(encoding="utf-8"))
    raus = {}
    for name, t in sorted(pin["tools"].items()):
        version = t["version"]
        dateien = sorted(t.get("artifacts") or {})
        # Die .notice.txt DANEBEN - und zwar wirklich daneben: jeder Hinweis
        # folgt unmittelbar auf sein Artefakt. Sie ist keine Beigabe, ohne
        # sie geben wir ein fremdes Binary ohne seinen Lizenzhinweis weiter,
        # und in einer Liste, die sie hinten sammelt, sieht man nicht mehr,
        # ob einem Artefakt seiner fehlt.
        namen = [n for d in dateien for n in (d, f"{d}.notice.txt")]
        if "licence_sidecar" in t:
            namen.append(t["licence_sidecar"]["name"])
        raus[name] = {
            "version": version,
            "revision": None,
            "spdx": t.get("spdx", ""),
            "upstream": t.get("upstream", ""),
            "herkunft": "gespiegelt",
            "praefix": f"tools/{name}/{version}",
            "namen": namen,
        }
    return raus


def selbst_gebaut() -> dict[str, dict]:
    """gappa und matiec - unsere eigenen Windows-Bauten UND ihre Quelle.

    Die Quelle ist keine Bequemlichkeit: gappa steht unter CeCILL, matiec
    unter GPL-3.0. Wer ein Binary weitergibt, das er selbst gebaut hat,
    schuldet den dazugehoerigen Quelltext. Bis zum 2026-09-14 stand sie in
    keiner Ableitung, obwohl sie auf R2 lag.
    """
    raus = {}
    for datei, name in (("gappa-pin.json", "gappa"),
                        ("matiec-pin.json", "matiec")):
        p = WURZEL / datei
        if not p.exists():
            # NICHT stillschweigend auslassen: ein Werkzeug, das aus der Datei
            # verschwindet, faellt drueben auf.
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        revision = d.get("revision")
        # Die ANZEIGEVERSION, so wie die Bauskripte sie in den Dateinamen
        # setzen: `matiec-0.1-7949c0b-win_amd64.zip`.
        version = d["version"]
        if revision:
            version = f"{version}-{revision[:7]}"
        namen = [f"{name}-{version}-win_amd64{e}" for e in WINDOWS_ENDUNGEN]
        for quelle in sorted(d.get("source") or {}):
            namen += [quelle, f"{quelle}.sha256"]
        raus[name] = {
            "version": version,
            # Die VOLLE Revision daneben. Ohne sie kann ein Verbraucher
            # matiec nicht binden: zqels flake.nix pinnt 40 Zeichen, die
            # Anzeigeversion traegt sieben. Das war die zweite Luecke, die
            # den Lock untragfaehig machte.
            "revision": revision,
            "spdx": (d.get("windows_build", {}).get("tool_licence", {})
                     or {}).get("spdx", ""),
            "upstream": d.get("upstream_project", ""),
            "herkunft": "selbst gebaut",
            "praefix": f"tools/{name}/{version}",
            "namen": namen,
        }
    return raus


def alle() -> dict[str, dict]:
    werkzeuge = gespiegelt()
    werkzeuge.update(selbst_gebaut())
    return werkzeuge


def adressen(werkzeug: dict) -> list[str]:
    return [f"{BASIS}/{werkzeug['praefix']}/{n}" for n in werkzeug["namen"]]
