"""Ein Paket, dessen VERIFICATION.txt auf ein fremdes Zip zeigt, geht nicht raus.

GEMESSEN am 2026-09-21 (Lauf #92, der woechentliche): der Lauf hat gappa neu
gebaut. Auf R2 blieb das Zip vom 17.09. liegen - `tools/` ist dort
unveraenderlich. Nach Chocolatey ging das Paket vom 21.09. trotzdem durch,
weil ein Paket in Moderation ersetzt werden DARF. Danach trugen die beiden
verschiedene gappa.exe, und VERIFICATION.txt forderte den Moderator auf,
genau sie zu vergleichen. Er hat es getan und zurueckgestellt.

Niemand hatte das entschieden. Der Cron hat es getan. Diese Datei haelt den
Riegel fest, der seither davorsteht.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "windows"))

import dasselbe_wie_draussen as riegel  # noqa: E402

WERKZEUGE = ("gappa", "matiec")


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_dasselbe_zip_darf_eingereicht_werden(tmp_path, monkeypatch, werkzeug):
    url = riegel.oeffentliche_zip_adresse(werkzeug)
    (tmp_path / url.rsplit("/", 1)[-1]).write_bytes(b"dieselben Bytes")
    monkeypatch.setattr(riegel, "hole", lambda u: b"dieselben Bytes")
    assert riegel.urteil(werkzeug, tmp_path) == 0


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_ein_anderer_bau_wird_nicht_eingereicht(tmp_path, monkeypatch, werkzeug):
    """Der Fall vom 21.09. - und er ist KEIN Fehler, sondern der Normalfall
    jedes woechentlichen Laufs. Deshalb 1 und nicht 2."""
    url = riegel.oeffentliche_zip_adresse(werkzeug)
    (tmp_path / url.rsplit("/", 1)[-1]).write_bytes(b"der Bau von heute")
    monkeypatch.setattr(riegel, "hole", lambda u: b"der Bau von vorletzter Woche")
    assert riegel.urteil(werkzeug, tmp_path) == 1


def test_eine_unklare_antwort_reicht_auch_nicht_ein_aber_laut(tmp_path, monkeypatch):
    """Nicht feststellbar ist nicht dasselbe wie 'darf nicht'. Ein stilles
    Ueberspringen waere hier dieselbe fail-open Stufe wie in #210."""
    url = riegel.oeffentliche_zip_adresse("gappa")
    (tmp_path / url.rsplit("/", 1)[-1]).write_bytes(b"egal")

    def kaputt(u):
        raise OSError("Leitung weg")

    monkeypatch.setattr(riegel, "hole", kaputt)
    assert riegel.urteil("gappa", tmp_path) == 2


def test_ohne_gebautes_zip_wird_nichts_behauptet(tmp_path):
    assert riegel.urteil("gappa", tmp_path) == 2


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_der_riegel_steht_vor_dem_upload_nicht_dahinter(werkzeug):
    """Die Reihenfolge ist der ganze Ertrag: pruefen, DANN einreichen."""
    lauf = (ROOT / ".forgejo" / "workflows" /
            f"{werkzeug}-windows.yml").read_text(encoding="utf-8")
    # Auf den AUFRUF, nicht auf den Namen: `push.chocolatey.org` steht drei
    # Zeilen weiter oben auch im Kommentar, und dagegen zu pruefen hiesse,
    # die Reihenfolge der Prosa zu messen statt die der Schritte.
    upload = '-Uri "https://push.chocolatey.org/api/v2/package"'
    assert "dasselbe_wie_draussen.py" in lauf
    assert upload in lauf
    assert lauf.index("dasselbe_wie_draussen.py") < lauf.index(upload)


@pytest.mark.parametrize("werkzeug", WERKZEUGE)
def test_der_riegel_fragt_nicht_den_cache(werkzeug):
    """Dieselbe Lehre wie in publish_r2.py am 2026-09-17: dl.zqel.org liegt
    hinter Cloudflare, und ein Cache weiss nichts von einer Loeschung."""
    quelle = (ROOT / "tools" / "windows" /
              "dasselbe_wie_draussen.py").read_text(encoding="utf-8")
    assert "nocache=" in quelle
