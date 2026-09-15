"""Die winget-Manifeste sagen dasselbe wie die Pins - oder sie sind falsch.

Anders als bei NuGet und Chocolatey traegt winget das Binary NICHT: das
Manifest NENNT eine Adresse und einen Hash. Damit ist jede Abweichung vom Pin
hier keine Kosmetik, sondern eine Anweisung an fremde Rechner, etwas anderes
zu installieren, als dieses Repository gepinnt hat.

Diese Datei prueft das OHNE Netz - Kennungen, Versionen, Lizenzangaben und
Adressen gegen die Pins. Ob der genannte Hash auch der ist, den die
oeffentliche Beilage nennt, prueft die CI mit
`write_winget_manifest.py --pruefen`; das braucht eine Leitung nach draussen.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "windows"))

import toolchain_adressen  # noqa: E402
import write_winget_manifest as winget  # noqa: E402

WERKZEUGE = ("gappa", "matiec")


def _felder(pfad: pathlib.Path) -> dict[str, str]:
    """Die flachen Schluessel einer Manifestdatei - ohne yaml-Abhaengigkeit.

    Die Dateien sind erzeugt, also kennen wir ihre Form; ein Parser waere
    hier eine Abhaengigkeit fuer nichts.
    """
    felder = {}
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        if zeile.startswith("#") or not zeile.strip():
            continue
        if ": " in zeile and not zeile.startswith(" "):
            k, _, v = zeile.partition(": ")
            felder[k] = v.strip()
        elif zeile.strip().startswith("InstallerUrl:") or \
                zeile.strip().startswith("InstallerSha256:"):
            k, _, v = zeile.strip().partition(": ")
            felder[k] = v.strip()
    return felder


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_jedes_manifest_gibt_es_und_es_nennt_dieselbe_version(werkzeug):
    pin = json.loads((ROOT / f"{werkzeug}-pin.json").read_text(encoding="utf-8"))
    version = toolchain_adressen.alle()[werkzeug]["version"]
    id_ = winget.kennung(werkzeug)
    stamm = ROOT / "tools" / "windows" / "winget" / id_ / version

    for endung in ("", ".installer", ".locale.en-US"):
        datei = stamm / f"{id_}{endung}.yaml"
        assert datei.is_file(), f"{datei} fehlt - neu erzeugen"
        f = _felder(datei)
        assert f["PackageIdentifier"] == id_
        # Die Anzeigeversion, nicht die nackte: bei matiec traegt sie die
        # Revision, und ohne sie benennt das Manifest zwei Bauten gleich.
        assert f["PackageVersion"] == version
        assert f["ManifestVersion"] == winget.SCHEMA
    assert pin  # der Pin muss lesbar sein, sonst sagt der Rest nichts


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_lizenz_und_herausgeber_kommen_aus_dem_pin(werkzeug):
    """Eine Lizenzangabe, die von der im Paket abweicht, ist eine falsche
    Zusage an jeden, der `winget show` liest."""
    pin = json.loads((ROOT / f"{werkzeug}-pin.json").read_text(encoding="utf-8"))
    version = toolchain_adressen.alle()[werkzeug]["version"]
    id_ = winget.kennung(werkzeug)
    f = _felder(ROOT / "tools" / "windows" / "winget" / id_ / version /
                f"{id_}.locale.en-US.yaml")

    lizenz = pin["windows_build"]["tool_licence"]
    assert f["License"] == lizenz["spdx"]
    assert f["LicenseUrl"] == lizenz["url"]
    # Herausgeber ist UPSTREAM. Uns dort einzutragen waere eine Anmassung -
    # wir paketieren, wir schreiben das Werkzeug nicht.
    assert f["Publisher"] == pin["upstream_publisher"]
    assert f["PublisherUrl"] == pin["upstream_project"]


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_die_installeradresse_folgt_derselben_ableitung_wie_alles_andere(werkzeug):
    """Sonst zeigt das Manifest irgendwohin, waehrend die README woandershin
    zeigt - und genau dieses Muster hat dieses Repository schon einmal
    eingesammelt."""
    version = toolchain_adressen.alle()[werkzeug]["version"]
    id_ = winget.kennung(werkzeug)
    f = _felder(ROOT / "tools" / "windows" / "winget" / id_ / version /
                f"{id_}.installer.yaml")

    erwartet = [a for a in toolchain_adressen.adressen(
        toolchain_adressen.alle()[werkzeug]) if a.endswith("-setup.exe")]
    assert f["InstallerUrl"] == erwartet[0]
    assert f["InstallerType"] == "inno", "tool.iss baut einen Inno-Installer"

    # Ob DIESER Hash stimmt, misst die CI. Hier nur: es ist ueberhaupt einer,
    # und in der Schreibweise, die winget verlangt.
    h = f["InstallerSha256"]
    assert len(h) == 64 and h == h.upper() and all(c in "0123456789ABCDEF" for c in h)
