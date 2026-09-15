"""Das .nupkg ist eine dritte Verpackung derselben Sache - und darf deshalb
nichts anderes behaupten als der Pin.

Geprueft wird das, was ein Bau auf Windows NICHT bemerken wuerde: dass die
Version aus dem Pin folgt (und bei matiec die Revision traegt, weil `0.1`
sonst zwei verschiedene Bauten gleich benennt), dass die Lizenzkennung
mitfaehrt und dass jede Datei aus dem Stage-Verzeichnis auch wirklich im
Paket liegt. Der Bau selbst laeuft nur auf einer MSYS2-Maschine; diese Datei
laeuft ueberall.
"""
from __future__ import annotations

import json
import pathlib
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "windows"))

import pack_nupkg  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _stage(tmp_path: pathlib.Path) -> pathlib.Path:
    """Ein Stage-Verzeichnis, wie win_package.ps1 es hinterlaesst."""
    stage = tmp_path / "stage"
    (stage / "licenses" / "tool").mkdir(parents=True)
    (stage / "gappa.exe").write_bytes(b"MZ")
    (stage / "NOTICE.txt").write_text("Lizenzen")
    (stage / "COPYING").write_text("CeCILL")           # ohne Endung
    (stage / "licenses" / "tool" / "COPYING.GPL").write_text("GPL")
    return stage


def test_gappa_traegt_seine_version_und_matiec_seine_revision():
    gappa = json.loads((ROOT / "gappa-pin.json").read_text(encoding="utf-8"))
    matiec = json.loads((ROOT / "matiec-pin.json").read_text(encoding="utf-8"))
    assert pack_nupkg.paketversion(gappa) == gappa["version"]
    # matiec meldet fuer jede Revision 0.1 - ohne die Revision waere die
    # Paketversion keine Kennung, sondern eine Kollision.
    assert pack_nupkg.paketversion(matiec) == f"0.1.0-rev{matiec['revision'][:7]}"


def test_das_paket_traegt_jede_datei_und_die_lizenzkennung(tmp_path):
    stage = _stage(tmp_path)
    nupkg = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "out")

    with zipfile.ZipFile(nupkg) as z:
        namen = set(z.namelist())
        spec = ET.fromstring(z.read("Zqel.Gappa.win-x64.nuspec"))
        typen = z.read("[Content_Types].xml").decode()

    fuer_alle = {f"tools/{p.relative_to(stage).as_posix()}"
                 for p in stage.rglob("*") if p.is_file()}
    assert fuer_alle <= namen, "eine Datei aus dem Stage fehlt im Paket"

    ns = "{http://schemas.microsoft.com/packaging/2012/06/nuspec.xsd}"
    spdx = json.loads((ROOT / "gappa-pin.json").read_text(
        encoding="utf-8"))["windows_build"]["tool_licence"]["spdx"]
    assert spec.find(f"{ns}metadata/{ns}license").text == spdx
    assert spec.find(f"{ns}metadata/{ns}version").text == "1.4.0"

    # Eine Datei ohne Endung kann kein Default fassen; ohne Override waere
    # das Paket fuer einen strengen OPC-Leser unvollstaendig.
    assert 'PartName="/tools/COPYING"' in typen
    assert 'Extension="exe"' in typen


def test_derselbe_stand_ergibt_dieselben_bytes(tmp_path):
    """Sonst meldet die Registry jede Woche eine Aenderung, die es nicht gab."""
    stage = _stage(tmp_path)
    a = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "a")
    b = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
