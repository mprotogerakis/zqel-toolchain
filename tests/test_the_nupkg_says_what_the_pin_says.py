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

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "windows"))

import pack_nupkg  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _stage(tmp_path: pathlib.Path) -> pathlib.Path:
    """Ein dist-Verzeichnis, wie New-ToolPackage es hinterlaesst: das Stage
    und daneben der Quell-Tarball."""
    stage = tmp_path / "stage"
    (stage / "licenses" / "tool").mkdir(parents=True)
    (stage / "gappa.exe").write_bytes(b"MZ")
    (stage / "NOTICE.txt").write_text("Lizenzen")
    (stage / "COPYING").write_text("CeCILL")           # ohne Endung
    (stage / "licenses" / "tool" / "COPYING.GPL").write_text("GPL")
    (tmp_path / "gappa-1.4.0.tar.gz").write_bytes(b"\x1f\x8b Quelle")
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


def test_die_quelle_faehrt_mit_und_ihr_fehlen_ist_laut(tmp_path):
    """Der Quelltext gehoert ins Paket, nicht nur in einen Verweis.

    Formal genuegte der Verweis (GPL-3.0 §6(d)). Aber SOURCES.txt sagt IM
    Paket "Dieselbe Quelle liegt in derselben Paketversion neben diesem
    Paket" - ohne Tarball behauptet ein Lizenzdokument etwas Falsches ueber
    das Paket, in dem es liegt.
    """
    stage = _stage(tmp_path)
    nupkg = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "out")
    with zipfile.ZipFile(nupkg) as z:
        assert "tools/source/gappa-1.4.0.tar.gz" in z.namelist()

    # Und wenn sie fehlt, faellt der Packer - statt ein Paket auszuliefern,
    # das seine eigene Zusage bricht.
    (tmp_path / "gappa-1.4.0.tar.gz").unlink()
    with pytest.raises(SystemExit):
        pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "ohne")


def test_derselbe_stand_ergibt_dieselben_bytes(tmp_path):
    """Sonst meldet die Registry jede Woche eine Aenderung, die es nicht gab."""
    stage = _stage(tmp_path)
    a = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "a")
    b = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()


def test_das_choco_paket_traegt_was_die_moderation_verlangt(tmp_path):
    """Chocolatey prueft ein Paket mit Binaerdateien von Hand nach.

    Was sie sucht, ist nicht Kosmetik: woher die Binaerdatei stammt
    (VERIFICATION.txt), unter welcher Lizenz sie weitergegeben wird
    (LICENSE.txt und licenseUrl) und wo das Rezept steht (packageSourceUrl).
    Fehlt eines davon, liegt das Paket in der Warteschlange statt in der
    Registry - und niemand faehrt deswegen noch einmal eine Woche.
    """
    stage = _stage(tmp_path)
    nupkg = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "choco",
                             "choco")
    # NICHT `gappa`: der kanonische Name verspricht die jeweils aktuelle
    # Fassung, dieses Paket verspricht die gepinnte. Bindestrich, nicht
    # Punkt - der Punkt ist auf Chocolatey ein Variantensuffix.
    assert nupkg.name == "zqel-gappa.1.4.0.nupkg"

    pin = json.loads((ROOT / "gappa-pin.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(nupkg) as z:
        namen = set(z.namelist())
        spec = z.read("zqel-gappa.nuspec").decode()
        pruef = z.read("tools/VERIFICATION.txt").decode()

    assert "tools/VERIFICATION.txt" in namen
    assert "tools/LICENSE.txt" in namen
    assert "tools/source/gappa-1.4.0.tar.gz" in namen
    assert pin["windows_build"]["tool_licence"]["url"] in spec
    assert "packageSourceUrl" in spec

    # Nachgefordert am 2026-09-17 (zqel-gappa 1.4.0, "Waiting for Maintainer").
    # Und zwar der Herausgeber des WERKZEUGS - wer ein Binary weitergibt,
    # erwirbt daran kein Urheberrecht.
    assert (f"<copyright>Copyright (c) {pin['upstream_publisher']}</copyright>"
            in spec)

    # Der Hash des Binaries steht DRIN, nachgefragt am 2026-09-21: sonst
    # muss ein Moderator erst ein Zip von einem fremden Server holen, um
    # ueberhaupt etwas pruefen zu koennen.
    import hashlib
    with zipfile.ZipFile(nupkg) as z:
        exe = z.read("tools/gappa.exe")
    assert hashlib.sha256(exe).hexdigest() in pruef
    assert "Get-FileHash tools\\gappa.exe" in pruef

    # Die Verifikation nennt NUR Adressen, die aus den Pins folgen - sonst
    # schickt sie einen Moderator an eine Stelle, an der nichts liegt.
    for adresse in pack_nupkg.oeffentliche_adressen("gappa"):
        assert adresse in pruef
    assert pin["source"]["gappa-1.4.0.tar.gz"]["sha256"] in pruef

    # Und die Beschreibung sagt es auch: wer die neueste Fassung sucht, ist
    # hier falsch. Der Name allein traegt diese Zusage nicht.
    # Englisch, weil Chocolatey diese Felder seinen Nutzern zeigt.
    assert "does NOT follow" in spec
    assert "does not track upstream releases" in spec


def test_das_paket_ist_ein_opc_dokument(tmp_path):
    """Ein .nupkg ist nicht irgendein Zip - es ist ein OPC-Paket.

    GEMESSEN am 2026-09-15: der Upload nach push.chocolatey.org antwortete mit
    HTTP 500. Die forgejo-Registry liest nur die .nuspec und war zufrieden;
    die NuGet-Gallery von Chocolatey oeffnet das Paket als OPC-Dokument und
    findet ohne _rels/.rels gar keinen Einstieg. Ein echtes Paket von dort
    (7zip) traegt genau diese vier Teile im Rumpf.
    """
    stage = _stage(tmp_path)
    nupkg = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "o", "choco")
    with zipfile.ZipFile(nupkg) as z:
        namen = z.namelist()
        rels = z.read("_rels/.rels").decode()
        typen = z.read("[Content_Types].xml").decode()

    assert "_rels/.rels" in namen
    props = [n for n in namen if n.endswith(".psmdcp")]
    assert len(props) == 1, "genau eine core-properties erwartet"
    assert props[0].startswith("package/services/metadata/core-properties/")

    # Die Beziehung muss auf die .nuspec zeigen, sonst findet ein Leser sie
    # nicht - und auf die psmdcp, die wirklich im Paket liegt.
    assert 'Target="/zqel-gappa.nuspec"' in rels
    assert f'Target="/{props[0]}"' in rels

    # `octet-stream` waere fuer diese beiden formal falsch.
    assert 'Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"' in typen
    assert 'Extension="psmdcp" ContentType="application/vnd.openxmlformats-package.core-properties+xml"' in typen


def test_auch_die_opc_teile_sind_bei_gleichem_stand_gleich(tmp_path):
    """Echte Werkzeuge wuerfeln den Namen der .psmdcp und die Ids. Hier werden
    sie abgeleitet - sonst meldete die Registry jede Woche eine Aenderung, die
    es nicht gab."""
    stage = _stage(tmp_path)
    a = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "a", "choco")
    b = pack_nupkg.packe(ROOT / "gappa-pin.json", stage, tmp_path / "b", "choco")
    assert a.read_bytes() == b.read_bytes()
