"""Oeffentlich spiegeln ist Weitergabe - und Weitergabe hat Auflagen.

Die interne forgejo-Registry loest auf 10.30.38.20 auf; wer nicht im HSD-Netz
sitzt, kommt an nichts heran. dl.zqel.org ist der oeffentliche Weg, und dorthin
gehoert auch das, was wir nicht selbst bauen.

Damit wechselt aber die Rolle: aus "wir benutzen dieses Werkzeug" wird "wir
geben es weiter". Ein Codex-Review am 2026-09-13 hat dazu zu Recht bemaengelt,
dass "die Lizenzdatei liegt irgendwo im Archiv" als Projektregel zu schwach
ist - niemand hatte nachgesehen.

Diese Datei haelt fest, was nachgesehen werden MUSS.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PIN = _ROOT / "mirror-pin.json"
_TOOL = _ROOT / "tools" / "mirror_upstream.py"


def _pin() -> dict:
    return json.loads(_PIN.read_text(encoding="utf-8"))


def _werkzeuge():
    return sorted(_pin()["tools"])


@pytest.mark.parametrize("werkzeug", _werkzeuge())
def test_every_mirrored_artifact_is_pinned_by_hash(werkzeug):
    meta = _pin()["tools"][werkzeug]
    assert meta["artifacts"], werkzeug
    for name, art in meta["artifacts"].items():
        assert len(art["sha256"]) == 64, f"{name}: kein Hash"
        assert art["size"] > 0, name
        assert art["url"].startswith("https://"), name
        assert name in art["url"], \
            f"{name}: der Dateiname muss in der Quell-URL vorkommen"


@pytest.mark.parametrize("werkzeug", _werkzeuge())
def test_every_mirrored_tool_states_its_licence_and_what_it_obliges(werkzeug):
    meta = _pin()["tools"][werkzeug]
    assert meta["spdx"], werkzeug
    assert len(meta["_licence_note"]) > 120, \
        f"{werkzeug}: ein SPDX-Kuerzel allein sagt nicht, was zu tun ist"
    assert meta["upstream"].startswith("https://")


@pytest.mark.parametrize("werkzeug", _werkzeuge())
def test_every_artifact_can_show_its_licence_one_way_or_the_other(werkzeug):
    """Entweder die Lizenztexte liegen nachweislich IM Archiv, oder ein
    Lizenztext liegt daneben. Beides zu unterlassen waere eine Weitergabe ohne
    Hinweis."""
    meta = _pin()["tools"][werkzeug]
    sidecar = meta.get("licence_sidecar")
    for name, art in meta["artifacts"].items():
        drin = art.get("licence_files_inside")
        assert drin or sidecar, \
            f"{name}: weder Lizenztexte im Archiv noch ein Text daneben"
    if sidecar:
        assert len(sidecar["sha256"]) == 64
        assert sidecar["url"].startswith("https://")


def test_the_cbmc_advertising_clause_is_not_quietly_dropped():
    """BSD-4-Clause Ziffer 3 ist eine Pflicht, die man leicht uebersieht, weil
    fast alle anderen BSD-Varianten sie nicht mehr haben."""
    meta = _pin()["tools"]["cbmc"]
    assert meta["spdx"] == "BSD-4-Clause"
    assert "Werbeklausel" in meta["_licence_note"]
    assert meta.get("licence_sidecar"), \
        "ein .msi laesst sich nicht durchsehen - der Text muss daneben liegen"


def test_we_mirror_the_variant_without_gpl_dependencies():
    """cvc5 KANN gegen CLN und GLPK (GPL) gelinkt werden, tut es standardmaessig
    nicht. Welche Variante wir weitergeben, entscheidet ueber die Pflichten."""
    meta = _pin()["tools"]["cvc5"]
    for name in meta["artifacts"]:
        assert "-gpl" not in name, f"{name}: das ist die GPL-Variante"
    assert "GPL" in meta["_licence_note"]


def test_the_mirror_verifies_before_it_publishes():
    """Die Reihenfolge ist der ganze Punkt: pruefen, dann hochladen. Andersherum
    stuende eine Datei oeffentlich, bevor jemand wusste, ob sie das darf."""
    src = _TOOL.read_text(encoding="utf-8")
    i_pruef = src.index("def pruefe_lizenzdateien")
    i_pub = src.index('if not args.publish')
    assert i_pruef < i_pub
    # Im Hauptlauf: erst holen und pruefen, dann der Publish-Zweig.
    lauf = src[src.index("def main("):]
    assert lauf.index("pruefe_lizenzdateien(") < lauf.index("--publish laedt hoch")
    assert "raise SystemExit" in src


def test_nothing_is_repacked():
    """Ein umgepacktes Archiv waere eine Bearbeitung, und dann gaelten andere
    Pflichten als die der blossen Weitergabe. Der Beipackzettel liegt DANEBEN."""
    src = _TOOL.read_text(encoding="utf-8")
    assert ".notice.txt" in src
    # Keine Regex-Klammern hier: der erste Entwurf hat sich an der offenen
    # Klammer in "ZipFile(.*'w'" selbst verschluckt.
    for verboten in ("extractall", "ZipFile(archiv, \"w", "tarfile.open(archiv, \"w"):
        assert verboten not in src, f"packt um: {verboten}"
    # Lesen ja, schreiben nein.
    assert 'ZipFile(archiv)' in src and 'tarfile.open(archiv, "r:gz")' in src


def test_the_pin_says_why_these_versions_and_not_the_newest():
    """Dieselbe Regel wie bei gappa: ein Werkzeug, das je nach Plattform ein
    anderes ist, laesst sich nicht vergleichen."""
    for werkzeug, meta in _pin()["tools"].items():
        assert meta.get("_why_this_version"), werkzeug
