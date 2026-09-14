"""Der Spiegel wird nach dem Hochladen nachgeprueft - nicht nur davor.

Umgezogen aus mprotogerakis/LoLa am 2026-09-14; dort lagen die
Workflows unter .github/, hier unter .forgejo/.

`mirror_upstream.py` prueft den Hash des HERUNTERGELADENEN Artefakts, bevor es
hochlaedt. Danach sah niemand mehr hin. Ein abgebrochener Upload oder ein
ueberschriebener Schluessel faellt erst dem auf, der die Datei benutzt - und
das ist die eine Person, die es uns nicht sagen kann.

Dasselbe Muster wie bei der veralteten Gegenprobe (#331) und den sechs toten
Downloadlinks (#330): geprueft wird die Quelle, nicht das Ergebnis.

Dieser Test hat KEINEN Netzzugang - er prueft, dass die Nachpruefung im
Workflow ueberhaupt stattfindet und dass sie die Lizenzbeilagen mitnimmt.
Die Messung selbst macht `tools/verify_public_mirror.py`.
"""
from __future__ import annotations

import ast
import json
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_WERKZEUG = _ROOT / "tools" / "verify_public_mirror.py"
_MIRROR = _ROOT / ".forgejo" / "workflows" / "mirror-tools.yml"


def test_the_mirror_workflow_checks_itself_afterwards():
    text = _MIRROR.read_text(encoding="utf-8")
    anweisungen = "\n".join(z for z in text.splitlines()
                            if not z.lstrip().startswith("#"))
    assert "verify_public_mirror.py" in anweisungen, \
        "der Spiegel laedt hoch und sieht nie nach, was ankam"
    assert "--hash" in anweisungen, \
        "ohne --hash wird nur Erreichbarkeit geprueft, nicht der Inhalt"


def test_the_check_runs_after_the_upload_not_before():
    """Vorher geprueft waere sinnlos: dann misst es den vorigen Stand.

    Verglichen wird NUR der Schritt-Teil. Der erste Entwurf las die ganze
    Datei und schlug fehl, sobald verify_public_mirror.py auch im Pfadfilter
    stand - also weiter oben, aber ohne etwas auszufuehren. Ein Ausloeser ist
    keine Anweisung.
    """
    text = _MIRROR.read_text(encoding="utf-8")
    schritte = text[text.index("\njobs:"):]
    assert schritte.index("publish_r2.py") < schritte.index("verify_public_mirror.py"), \
        "die Nachpruefung steht vor dem Hochladen - sie misst dann den alten Stand"


def test_it_also_demands_the_licence_notice():
    """Ohne den Hinweis geben wir ein fremdes Binary ohne seine Lizenz weiter.

    Das ist keine Formalie, sondern die Bedingung, unter der wir es ueberhaupt
    weitergeben duerfen - siehe docs/redistribution.md.
    """
    quelle = _WERKZEUG.read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    # Die ANWEISUNG muss den Sidecar bilden, nicht nur die Prosa ihn erwaehnen.
    for k in ast.walk(baum):
        if isinstance(k, ast.Constant) and k.value == ".notice.txt":
            break
    else:
        raise AssertionError("der Pruefer sieht die .notice.txt nicht nach")


def test_every_pinned_artifact_would_be_covered():
    """Der Nenner: der Pin muss dem Pruefer ueberhaupt etwas zu tun geben."""
    pins = json.loads((_ROOT / "mirror-pin.json").read_text(encoding="utf-8"))["tools"]
    artefakte = [(w, d) for w, t in pins.items()
                 for d in (t.get("artifacts") or {})]
    assert len(artefakte) >= 6, f"nur {len(artefakte)} Artefakte im Pin"
    for werkzeug, datei in artefakte:
        a = pins[werkzeug]["artifacts"][datei]
        assert a.get("sha256") and a.get("size"), \
            f"{werkzeug}/{datei}: ohne sha256 und size ist nichts nachpruefbar"


def test_the_verifier_sends_no_credentials():
    """Es prueft die OEFFENTLICHE Adresse. Nimmt es einen Zugang mit, prueft
    es etwas anderes als das, was ein Fremder sieht."""
    quelle = _WERKZEUG.read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    for knoten in ast.walk(baum):
        koerper = getattr(knoten, "body", None)
        if isinstance(koerper, list) and koerper:
            erste = koerper[0]
            if (isinstance(erste, ast.Expr) and isinstance(erste.value, ast.Constant)
                    and isinstance(erste.value.value, str)):
                koerper.pop(0)
                if not koerper:
                    koerper.append(ast.Pass())
    anweisungen = ast.unparse(ast.fix_missing_locations(baum))
    for verboten in ("Authorization", "R2_ID", "R2_SECRET", "netrc", "PACKAGE_TOKEN"):
        assert verboten not in anweisungen, f"der Pruefer benutzt {verboten}"
