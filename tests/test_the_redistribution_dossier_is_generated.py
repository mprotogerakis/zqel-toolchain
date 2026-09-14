"""Die Lizenzuebersicht wird erzeugt, nicht gepflegt.

Eine von Hand geschriebene Uebersicht ist nach dem naechsten Pin-Wechsel falsch,
und niemand merkt es - sie ist dann eine zweite, driftende Behauptung neben den
Pins. Dieser Test haelt sie an die Pins gebunden.

Sie ist die Unterlage fuer die lizenzfachliche Abnahme aus #323, Punkt 5.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DOC = _ROOT / "docs" / "redistribution.md"
_GEN = _ROOT / "tools" / "redistribution_report.py"


def test_the_page_matches_what_the_generator_produces():
    erzeugt = subprocess.run([sys.executable, str(_GEN)], capture_output=True,
                             text=True, cwd=str(_ROOT))
    assert erzeugt.returncode == 0, erzeugt.stderr
    assert _DOC.read_text(encoding="utf-8") == erzeugt.stdout, (
        "docs/redistribution.md weicht vom Erzeuger ab. Nicht die Seite "
        "bearbeiten - die Pins aendern und neu erzeugen:\n"
        "  python tools/redistribution_report.py > docs/redistribution.md")


def test_it_says_plainly_that_it_is_not_legal_advice():
    text = _DOC.read_text(encoding="utf-8")
    assert "not legal advice" in text


def test_it_names_its_own_gaps():
    """Eine Zusicherung, die ihre Grenze verschweigt, wird beim naechsten Leser
    zur Behauptung ueber alles. Drei Luecken sind bekannt und muessen dastehen.
    """
    text = _DOC.read_text(encoding="utf-8")
    assert "does not cover" in text
    assert "transitive dependency closure" in text
    assert "cvc5" in text.split("does not cover")[1], \
        "die offene Frage zur cvc5-Binaerkonfiguration gehoert in die Luecken"


def test_every_thing_we_publish_appears():
    text = _DOC.read_text(encoding="utf-8")
    for name in ("Gappa", "matiec", "zqel", "cvc5", "cbmc", "kani"):
        assert name in text, f"{name} fehlt in der Uebersicht"
