#!/usr/bin/env python3
"""Die winget-Manifeste - abgeleitet aus den Pins, der Hash GEMESSEN.

WOZU (#19):
`winget install` ist auf Windows das, was `nix shell` auf Linux ist: der Weg,
auf dem jemand ein Werkzeug bekommt, ohne eine Datei zu suchen. Anders als
NuGet und Chocolatey traegt winget das Binary NICHT - ein Manifest nennt die
Adresse des Installers und seinen SHA-256. Das passt zu diesem Repository,
denn beides gibt es hier schon oeffentlich.

WARUM DER HASH NICHT IM MANIFEST GEPFLEGT WIRD:
Er wird aus der Beilage geholt, die neben dem Installer liegt
(`...-setup.exe.sha256`), und zwar von der OEFFENTLICHEN Adresse. Damit
beschreibt das Manifest, was draussen wirklich ausgeliefert wird, und nicht,
was wir einmal hineingeschrieben haben. Faellt die Abfrage aus, entsteht kein
Manifest - ein Manifest mit geratenem Hash ist schlimmer als keines: winget
bricht beim Nutzer ab, nicht bei uns.

WAS ES NICHT TUT:
Einreichen. Ein Manifest wird in `microsoft/winget-pkgs` gemergt, und das ist
ein oeffentlicher Pull Request unter einem Namen - eine Entscheidung, kein
Nebeneffekt eines woechentlichen Laufs. Die Dateien liegen fertig im Baum und
werden so eingereicht:

    winget validate --manifest tools/windows/winget/zqel.gappa/1.4.0
    # dann die drei Dateien nach manifests/z/zqel/gappa/1.4.0/ in einem Fork
    # von microsoft/winget-pkgs, und ein PR von dort.

`winget validate` laeuft nur auf Windows. Was sich OHNE Windows pruefen laesst
- dass die Manifeste zu den Pins passen und der genannte Hash der ist, den die
oeffentliche Beilage nennt -, prueft `--pruefen` und
tests/test_the_winget_manifests_follow_the_pins.py.

Aufruf:
    python tools/windows/write_winget_manifest.py --pin gappa-pin.json
    python tools/windows/write_winget_manifest.py --pin gappa-pin.json --pruefen
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

WURZEL = pathlib.Path(__file__).resolve().parents[2]
ZIEL = WURZEL / "tools" / "windows" / "winget"
PROJEKT = "https://github.com/mprotogerakis/zqel-toolchain"

#: Die Schemaversion, gegen die diese Dateien geschrieben sind. winget lehnt
#: ein Manifest ab, dessen ManifestVersion es nicht kennt - deshalb an EINER
#: Stelle und nicht dreimal im Text.
SCHEMA = "1.6.0"


def kennung(werkzeug: str) -> str:
    """`zqel.gappa` - Herausgeber Punkt Paket, so will winget es.

    Der erste Teil sind WIR, nicht Upstream: wir geben dieses Paket heraus,
    Upstream gibt das Werkzeug heraus. Das Manifest trennt beides - Publisher
    nennt Upstream, die Kennung uns.
    """
    return f"zqel.{werkzeug}"


def gemessener_hash(url: str) -> str:
    """Der SHA-256 aus der Beilage neben dem Installer - GROSS, so will winget es.

    Mit eigenem User-Agent: gemessen am 2026-09-14 weist Cloudflare den
    Vorgabewert von python-urllib mit 403 ab (dieselbe Falle wie in
    write_toolchain_lock.py).
    """
    req = urllib.request.Request(f"{url}.sha256",
                                 headers={"User-Agent": "zqel-toolchain-winget"})
    try:
        with urllib.request.urlopen(req, timeout=30) as a:
            roh = a.read().decode("ascii").split()[0].strip()
    except (urllib.error.URLError, OSError) as e:
        raise SystemExit(
            f"{url}.sha256 ist nicht erreichbar ({type(e).__name__}: {e}).\n"
            "Ohne gemessenen Hash entsteht hier kein Manifest - ein geratener "
            "bricht beim Nutzer ab, nicht bei uns.")
    if len(roh) != 64:
        raise SystemExit(f"{url}.sha256 enthaelt keinen SHA-256: {roh!r}")
    return roh.upper()


def adressen(werkzeug: str) -> tuple[str, str]:
    """Installer und Anzeigeversion, aus derselben Ableitung wie alles andere."""
    sys.path.insert(0, str(WURZEL / "tools"))
    from toolchain_adressen import adressen as urls, alle

    w = alle()[werkzeug]
    setup = [a for a in urls(w) if a.endswith("-setup.exe")]
    if len(setup) != 1:
        raise SystemExit(f"{werkzeug}: genau ein Installer erwartet, {len(setup)} gefunden")
    return setup[0], w["version"]


def manifeste(pin_pfad: pathlib.Path) -> dict[str, str]:
    werkzeug = pin_pfad.name.removesuffix("-pin.json")
    pin = json.loads(pin_pfad.read_text(encoding="utf-8"))
    installer, version = adressen(werkzeug)
    quellname, quelle = next(iter(pin["source"].items()))
    id_ = kennung(werkzeug)
    spdx = pin["windows_build"]["tool_licence"]["spdx"]

    kopf = f"# Erzeugt von tools/windows/write_winget_manifest.py - nicht von Hand pflegen.\n"
    gemeinsam = f"PackageIdentifier: {id_}\nPackageVersion: {version}\n"

    version_yaml = (kopf + gemeinsam +
                    f"DefaultLocale: en-US\nManifestType: version\n"
                    f"ManifestVersion: {SCHEMA}\n")

    installer_yaml = (
        kopf + gemeinsam +
        "InstallerLocale: en-US\n"
        # Inno Setup, weil tools/windows/tool.iss ihn baut. winget leitet
        # daraus die stillen Schalter ab (/VERYSILENT), die wir sonst von
        # Hand nennen muessten - und falsch nennen koennten.
        "InstallerType: inno\n"
        "Installers:\n"
        "  - Architecture: x64\n"
        f"    InstallerUrl: {installer}\n"
        f"    InstallerSha256: {gemessener_hash(installer)}\n"
        f"ManifestType: installer\nManifestVersion: {SCHEMA}\n")

    locale_yaml = (
        kopf + gemeinsam +
        "PackageLocale: en-US\n"
        f"Publisher: {pin['upstream_publisher']}\n"
        f"PublisherUrl: {pin['upstream_project']}\n"
        f"PackageName: {werkzeug}\n"
        f"PackageUrl: {PROJEKT}\n"
        f"License: {spdx}\n"
        f"LicenseUrl: {pin['windows_build']['tool_licence']['url']}\n"
        f"ShortDescription: {werkzeug} {version} for Windows x86_64, built "
        f"from the pinned upstream source.\n"
        "Description: >-\n"
        f"  Built by the zqel toolchain from {quelle['url']}\n"
        f"  (sha256 {quelle['sha256']}), so that the same version of this tool\n"
        "  runs on Windows as in the verification gate. The installer carries\n"
        "  its licence texts, a provenance record and the source tarball it was\n"
        f"  compiled from ({quellname}).\n"
        f"ManifestType: defaultLocale\nManifestVersion: {SCHEMA}\n")

    stamm = f"{ZIEL.relative_to(WURZEL)}/{id_}/{version}"
    return {
        f"{stamm}/{id_}.yaml": version_yaml,
        f"{stamm}/{id_}.installer.yaml": installer_yaml,
        f"{stamm}/{id_}.locale.en-US.yaml": locale_yaml,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pin", required=True, help="gappa-pin.json / matiec-pin.json")
    ap.add_argument("--pruefen", action="store_true",
                    help="nicht schreiben, nur melden ob die Dateien aktuell sind")
    args = ap.parse_args(argv)

    neu = manifeste(pathlib.Path(args.pin))
    abweichung = []
    for rel, text in neu.items():
        datei = WURZEL / rel
        if not datei.exists() or datei.read_text(encoding="utf-8") != text:
            abweichung.append(rel)

    if args.pruefen:
        if abweichung:
            for rel in abweichung:
                print(f"  weicht ab: {rel}")
            raise SystemExit(
                "Die winget-Manifeste passen nicht mehr zu den Pins oder zu "
                "dem, was oeffentlich ausgeliefert wird. Neu erzeugen mit "
                "tools/windows/write_winget_manifest.py --pin <pin>")
        print(f"  {len(neu)} Manifeste stimmen mit den Pins und dem "
              "gemessenen Installer-Hash ueberein.")
        return 0

    for rel, text in neu.items():
        datei = WURZEL / rel
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text(text, encoding="utf-8")
        print(f"  {rel}")
    if not abweichung:
        print("  (unveraendert)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
