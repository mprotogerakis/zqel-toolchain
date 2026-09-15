#!/usr/bin/env python3
"""Dasselbe Windows-Paket noch einmal als .nupkg - fuer Ketten, die NuGet sprechen.

WOZU, WO ES ZIP UND INSTALLER SCHON GIBT:
Zip und Installer setzen einen Menschen voraus, der eine Datei holt und
auspackt. Eine Werkzeugkette auf Windows loest ihre Werkzeuge stattdessen aus
einer Registry auf - und nennt dabei eine Version. Genau das ist der Ertrag:
`Zqel.Gappa.win-x64 1.4.0` ist eine Angabe, die ein Bauskript festhalten kann,
waehrend "ich habe mal ein Zip heruntergeladen" keine ist.

WARUM SELBST GEZIPPT UND NICHT `nuget pack`:
Auf der Baumaschine steht kein .NET-SDK und kein nuget.exe - deps.winget.json
fuehrt git, Python, BuildTools, MSYS2 und Inno Setup, und das ist die
vollstaendige Liste (tests/test_windows_deps_are_declared_once.py haelt sie
fest). Ein zweites Paketsystem NUR zum Einpacken waere teurer als diese Datei:
ein .nupkg IST ein Zip mit einer .nuspec obenauf.

WAS HIER NICHT ENTSTEHT:
Die Lizenztexte. Eingepackt wird genau das Stage-Verzeichnis, das
win_package.ps1 bereits mit NOTICE.txt, SOURCES.txt, COPYING und licenses/
gefuellt hat. Eine zweite Stelle, die Lizenzen zusammensucht, waere eine
zweite Autoritaet - und eine von beiden liefert irgendwann ein Paket aus,
dessen Hinweis nicht mehr stimmt.

Aufruf:
    python tools/windows/pack_nupkg.py --pin gappa-pin.json \\
        --stage dist/gappa/stage --out dist/gappa-nuget
"""
from __future__ import annotations

import argparse
import json
import pathlib
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape

#: Reproduzierbarkeit wie bei pack_flake.py: ohne feste Zeit bekommt derselbe
#: Inhalt zwei verschiedene Bytes - und die Registry meldet eine Aenderung,
#: die es nicht gab. 1980-01-01 ist das Aelteste, was ein Zip-Kopf kann.
EPOCHE = (1980, 1, 1, 0, 0, 0)

PROJEKT = "https://github.com/mprotogerakis/zqel-toolchain"

NUSPEC = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd">
  <metadata>
    <id>{id}</id>
    <version>{version}</version>
    <authors>zqel-toolchain</authors>
    <owners>zqel-toolchain</owners>
    <projectUrl>{projekt}</projectUrl>
    <license type="expression">{spdx}</license>
    <requireLicenseAcceptance>false</requireLicenseAcceptance>
    <description>{beschreibung}</description>
    <tags>{tags}</tags>
  </metadata>
</package>
"""


def paket_id(werkzeug: str) -> str:
    return f"Zqel.{werkzeug.capitalize()}.win-x64"


def paketversion(pin: dict) -> str:
    """Die Paketversion aus dem Pin - drei Stellen, und die Revision dahinter.

    NuGet will SemVer. `0.1` allein ist keins, und matiec meldet fuer JEDE
    Revision `0.1` (matiec-pin.json sagt warum). Zwei verschiedene Bauten
    laegen also unter derselben Paketversion, und der zweite Upload haette
    mit 409 als "unveraendert" gegolten - wie beim generischen Upload, nur
    ohne dass es jemandem auffiele.

    Die Revision wandert deshalb in den Vorabteil: `0.1.0-rev7949c0b`. Dass
    ein Werkzeug ohne Release als Vorab gilt, ist keine Notluege, sondern die
    Lage - `dotnet add package` braucht dafuer `--prerelease`.
    """
    teile = str(pin["version"]).split(".")
    teile += ["0"] * (3 - len(teile))
    version = ".".join(teile[:3])
    revision = pin.get("revision")
    return f"{version}-rev{revision[:7]}" if revision else version


def nuspec(pin: dict, werkzeug: str) -> str:
    bau = pin["windows_build"]
    quelle = next(iter(pin["source"].items()))
    spdx = bau["tool_licence"]["spdx"]
    beschreibung = (
        f"{werkzeug} {paketversion(pin)} fuer Windows x86_64, gebaut aus "
        f"{quelle[1]['url']} (sha256 {quelle[1]['sha256']}). "
        f"Lizenz: {spdx}. Die Lizenztexte, der Herkunftsnachweis und der "
        f"gepinnte Stand liegen im Paket unter tools/ (NOTICE.txt, "
        f"SOURCES.txt, PIN.txt, licenses/), der uebersetzte Quelltext unter "
        f"tools/source/. Die Binaerdatei liegt unter tools/ - das Paket "
        f"traegt keinen .NET-Code und wird nicht referenziert, sondern "
        f"ausgepackt."
    )
    return NUSPEC.format(
        id=paket_id(werkzeug),
        version=paketversion(pin),
        projekt=PROJEKT,
        # NuGet kennt nur eine Teilmenge der SPDX-Kennungen als Ausdruck;
        # CECILL-2.1 koennte darunter fehlen. Das kostet hoechstens die
        # huebsche Anzeige - bindend ist ohnehin der Text IM Paket, und der
        # kommt aus derselben Quelle wie hier die Kennung.
        spdx=escape(spdx),
        beschreibung=escape(beschreibung),
        tags=f"{werkzeug} windows zqel toolchain",
    )


def content_types(pfade: list[str]) -> str:
    """Der OPC-Kopf. Ohne ihn ist die Datei fuer strenge Leser kein Paket.

    Dateien ohne Endung - COPYING, COPYING3, COPYING.LIB heisst hier
    Endung `lib` - kann ein `Default` nicht fassen; fuer sie steht je ein
    `Override`. Und genau das ist der Grund, warum diese Liste ABGELEITET
    wird: eine gepflegte vergaesse den naechsten Lizenztext.
    """
    endungen = sorted({
        p.rsplit(".", 1)[1].lower()
        for p in pfade if "." in p.rsplit("/", 1)[-1]
    })
    zeilen = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
    ]
    zeilen += [
        f'  <Default Extension="{e}" ContentType="application/octet-stream" />'
        for e in endungen
    ]
    zeilen += [
        f'  <Override PartName="/{p}" ContentType="application/octet-stream" />'
        for p in pfade if "." not in p.rsplit("/", 1)[-1]
    ]
    zeilen.append("</Types>")
    return "\n".join(zeilen) + "\n"


def packe(pin_pfad: pathlib.Path, stage: pathlib.Path,
          out: pathlib.Path) -> pathlib.Path:
    werkzeug = pin_pfad.name.removesuffix("-pin.json")
    pin = json.loads(pin_pfad.read_text(encoding="utf-8"))
    dateien = sorted(p for p in stage.rglob("*") if p.is_file())
    if not dateien:
        raise SystemExit(f"{stage} ist leer - vor dem Paketieren wird gebaut")

    # Alles unter tools/: das ist der Ort fuer ein Paket, das Programme
    # mitbringt statt Bibliotheken. lib/ waere .NET-Code, und den gibt es hier
    # nicht.
    im_paket = {f"tools/{p.relative_to(stage).as_posix()}": p for p in dateien}

    # UND DIE QUELLE. Sie ist keine Beigabe: gappa steht unter CeCILL und
    # GPL-3.0, matiec unter GPL-3.0 - wer ein selbst gebautes Binary
    # weitergibt, schuldet den dazugehoerigen Quelltext.
    #
    # Formal genuegte der Verweis: GPL-3.0 §6(d) erlaubt die Quelle auf einem
    # anderen Server, solange beim Binary steht, wo sie liegt - und das steht
    # in SOURCES.txt. Der Grund, sie trotzdem einzupacken, ist ein anderer:
    # SOURCES.txt sagt woertlich "Dieselbe Quelle liegt in derselben
    # Paketversion neben diesem Paket". Im Zip stimmt das (New-ToolPackage
    # legt sie daneben), im .nupkg stimmte es nicht. Ein Lizenzdokument, das
    # im Paket etwas Falsches ueber dieses Paket behauptet, ist schlimmer als
    # ein paar hundert Kilobyte - gemessen 388 KB bei gappa, 713 KB bei
    # matiec, neben 6,6 MB Binary.
    for name in sorted(pin["source"]):
        quelle = stage.parent / name
        if not quelle.is_file():
            raise SystemExit(
                f"Der Quell-Tarball {name} liegt nicht in {stage.parent} - "
                "ohne ihn behauptet SOURCES.txt im Paket etwas Falsches. "
                "Er entsteht in New-ToolPackage; erst bauen, dann packen.")
        im_paket[f"tools/source/{name}"] = quelle
    ziel = out / f"{paket_id(werkzeug)}.{paketversion(pin)}.nupkg"
    out.mkdir(parents=True, exist_ok=True)

    inhalt: dict[str, bytes] = {
        f"{paket_id(werkzeug)}.nuspec": nuspec(pin, werkzeug).encode("utf-8"),
    }
    for name, quelle in im_paket.items():
        inhalt[name] = quelle.read_bytes()
    inhalt["[Content_Types].xml"] = content_types(sorted(inhalt)).encode("utf-8")

    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(inhalt):
            info = zipfile.ZipInfo(name, date_time=EPOCHE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, inhalt[name])

    pruefe(ziel, len(im_paket))
    return ziel


def pruefe(nupkg: pathlib.Path, erwartete_dateien: int) -> None:
    """Das eben geschriebene Paket noch einmal von aussen lesen.

    Ein Packer, der nur schreibt, prueft nichts - und ein kaputtes .nupkg
    faellt sonst erst dem auf, der es installieren will.
    """
    with zipfile.ZipFile(nupkg) as z:
        if z.testzip() is not None:
            raise SystemExit(f"{nupkg.name}: beschaedigter Eintrag")
        namen = z.namelist()
        spec = [n for n in namen if n.endswith(".nuspec") and "/" not in n]
        if len(spec) != 1:
            raise SystemExit(f"{nupkg.name}: genau eine .nuspec erwartet, {len(spec)} gefunden")
        ET.fromstring(z.read(spec[0]))
        getragen = sum(1 for n in namen if n.startswith("tools/"))
        if getragen != erwartete_dateien:
            raise SystemExit(
                f"{nupkg.name}: {getragen} Dateien im Paket, {erwartete_dateien} im Stage")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pin", required=True, help="gappa-pin.json / matiec-pin.json")
    ap.add_argument("--stage", required=True, help="das fertige Stage-Verzeichnis")
    ap.add_argument("--out", required=True, help="Verzeichnis fuer das .nupkg")
    args = ap.parse_args(argv)

    ziel = packe(pathlib.Path(args.pin), pathlib.Path(args.stage),
                 pathlib.Path(args.out))
    print(f"  {ziel}  {ziel.stat().st_size / 1048576:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
