from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import publish_r2  # noqa: E402


def test_sigv4_matches_the_official_get_vanilla_vector():
    headers = publish_r2.authorization(
        method="GET", host="example.amazonaws.com", path="/",
        payload_hash=publish_r2.EMPTY_SHA256,
        key_id="AKIDEXAMPLE",
        secret="wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        region="us-east-1", service="service",
        now=dt.datetime(2015, 8, 30, 12, 36, 0))
    assert headers["Authorization"] == (
        "AWS4-HMAC-SHA256 "
        "Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, "
        "SignedHeaders=host;x-amz-date, "
        "Signature=5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31")


def test_uploader_fails_closed_without_credentials(monkeypatch, tmp_path):
    for variable in ("R2_ID", "R2_SECRET", "R2_ENDPOINT", "R2_BUCKET"):
        monkeypatch.delenv(variable, raising=False)
    file = tmp_path / "artifact"
    file.write_bytes(b"x")
    with pytest.raises(SystemExit, match="must be set"):
        publish_r2.main([
            "--prefix", "flake", "--bucket", "", "--endpoint", "", str(file)])


def test_publish_workflow_has_no_pull_request_trigger():
    workflow = (ROOT / ".forgejo" / "workflows" / "publish-flake.yml").read_text()
    trigger_block = "\n".join(
        line for line in workflow.split("jobs:", 1)[0].splitlines()
        if not line.lstrip().startswith("#"))
    assert "pull_request" not in trigger_block
    assert "secrets.R2_BUCKET" in workflow
    assert "if:" not in workflow


def _ohne_netz(monkeypatch, *, liegt_da, etag=""):
    """Der Uploader darf im Test weder das Netz noch Zugaenge brauchen."""
    monkeypatch.setattr(publish_r2, "liegt_schon_da",
                        lambda key: (liegt_da, etag))
    hochgeladen = []
    monkeypatch.setattr(publish_r2, "put",
                        lambda file, **k: hochgeladen.append(k["key"]))
    for name, wert in (("R2_ID", "x"), ("R2_SECRET", "y"),
                       ("R2_ENDPOINT", "https://example.invalid"),
                       ("R2_BUCKET", "zqel")):
        monkeypatch.setenv(name, wert)
    return hochgeladen


def test_eine_werkzeugadresse_traegt_den_letzten_bau(monkeypatch, tmp_path):
    """Umgedreht am 2026-09-23 - vorher blieb hier die erste Fassung liegen.

    Der Gedanke war richtig: wer `gappa-1.4.0-win_amd64.zip` zitiert, meint
    bestimmte Bytes. Die Wirkung war es nicht. Der Windows-Bau ist nicht
    reproduzierbar, also wich JEDER Lauf ab, also blieb immer der alte Stand
    liegen - waehrend das Chocolatey-Paket daneben der neue war. Genau diese
    Schere hat zqel-gappa 1.4.0 am 21.09. aus der Freigabe geworfen.

    Wer bestimmte Bytes meint, nennt seither ihren sha256, nicht ihre
    Adresse: in VERIFICATION.txt, in der .sha256-Beilage, im
    winget-Manifest.
    """
    datei = tmp_path / "gappa-1.4.0-win_amd64.zip"
    datei.write_bytes(b"neuer Bau")
    hochgeladen = _ohne_netz(monkeypatch, liegt_da=True, etag="fremdes-etag")
    publish_r2.main(["--prefix", "tools/gappa/1.4.0", str(datei)])
    assert hochgeladen == ["tools/gappa/1.4.0/gappa-1.4.0-win_amd64.zip"]


def test_dieselben_bytes_werden_nicht_noch_einmal_geschrieben(monkeypatch, tmp_path):
    """Die einzige Ausnahme, und sie ist eine Ersparnis, kein Schutz."""
    import hashlib

    datei = tmp_path / "gappa-1.4.0-win_amd64.zip"
    datei.write_bytes(b"derselbe Bau")
    etag = hashlib.md5(b"derselbe Bau").hexdigest()
    hochgeladen = _ohne_netz(monkeypatch, liegt_da=True, etag=etag)
    publish_r2.main(["--prefix", "tools/gappa/1.4.0", str(datei)])
    assert hochgeladen == []


def test_navigation_darf_sich_weiter_bewegen(monkeypatch, tmp_path):
    """latest.json ist Navigation, keine Identitaet - es MUSS wandern."""
    datei = tmp_path / "latest.json"
    datei.write_text("{}")
    hochgeladen = _ohne_netz(monkeypatch, liegt_da=True, etag="egal")
    publish_r2.main(["--prefix", "flake", str(datei)])
    assert hochgeladen == ["flake/latest.json"]


def test_eine_neue_version_wird_ganz_normal_veroeffentlicht(monkeypatch, tmp_path):
    datei = tmp_path / "gappa-1.8.3-win_amd64.zip"
    datei.write_bytes(b"erste Fassung")
    hochgeladen = _ohne_netz(monkeypatch, liegt_da=False)
    publish_r2.main(["--prefix", "tools/gappa/1.8.3", str(datei)])
    assert hochgeladen == ["tools/gappa/1.8.3/gappa-1.8.3-win_amd64.zip"]


def test_ersetzen_wird_genannt_nicht_verschwiegen(monkeypatch, tmp_path, capsys):
    """Ersetzen ist erlaubt, aber nicht still: beide md5 gehoeren ins Log.

    Sonst ist eine Adresse, die ihre Bytes gewechselt hat, hinterher von
    einer, die es nicht tat, nicht mehr zu unterscheiden.
    """
    datei = tmp_path / "gappa-1.4.0-win_amd64.zip"
    datei.write_bytes(b"neuer Bau")
    _ohne_netz(monkeypatch, liegt_da=True, etag="0" * 32)
    publish_r2.main(["--prefix", "tools/gappa/1.4.0", str(datei)])
    ausgabe = capsys.readouterr().out
    assert "wird ERSETZT" in ausgabe
    assert "0" * 32 in ausgabe


def test_eine_unklare_antwort_haelt_die_auslieferung_nicht_auf(monkeypatch, tmp_path):
    """HTTP 403 oder 500 heissen "wir wissen es nicht" - und im Zweifel gilt
    seit dem 2026-09-23, was der Lauf gebaut hat.

    Vorher hielt das hier an, damit keine Zusage ungefragt wanderte. Es hat
    zweimal eine halbe Auslieferung hinterlassen: eine Stoerung beim LESEN
    darf nicht darueber entscheiden, ob geschrieben wird.
    """
    import urllib.error

    def kaputt(anfrage, **egal):
        raise urllib.error.HTTPError("x", 503, "kaputt", {}, None)

    monkeypatch.setattr(publish_r2.urllib.request, "urlopen", kaputt)
    assert publish_r2.liegt_schon_da("tools/gappa/1.4.0/x.zip") == (False, "")


def test_die_existenzfrage_geht_am_cache_vorbei(monkeypatch):
    """Ein HEAD auf die blanke Adresse fragt den Cache, nicht den Bucket.

    GEMESSEN am 2026-09-17 (Lauf #85): vier Objekte von Hand geloescht, dann
    veroeffentlicht. Die beiden .sha256 waren aus dem Cloudflare-Cache
    gefallen und wurden geschrieben; Zip und Installer antworteten noch mit
    200 aus dem Cache und galten als "liegt schon da". Zurueck blieben zwei
    Beilagen, die den Hash von Dateien nennen, die es nicht gibt - und ein
    gruener Lauf.
    """
    gesehen = []

    class Antwort:
        headers = {"ETag": '"x"'}
        def __enter__(self): return self
        def __exit__(self, *egal): return False

    def merke(anfrage, **egal):
        gesehen.append(anfrage.full_url)
        return Antwort()

    monkeypatch.setattr(publish_r2.urllib.request, "urlopen", merke)
    publish_r2.liegt_schon_da("tools/gappa/1.4.0/x.zip")
    publish_r2.liegt_schon_da("tools/gappa/1.4.0/x.zip")

    assert all("nocache=" in u for u in gesehen), \
        "ohne Cache-Buster beantwortet der Cache die Frage nach dem Bucket"
    assert gesehen[0] != gesehen[1], \
        "ein FESTER Buster waere nach dem ersten Mal selbst wieder im Cache"
