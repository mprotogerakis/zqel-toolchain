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


def test_eine_veroeffentlichte_werkzeugadresse_wird_nicht_ersetzt(monkeypatch, tmp_path):
    """Wer `gappa-1.4.0-win_amd64.zip` zitiert, meint bestimmte Bytes.

    Gemessen am 2026-09-15: zwei Laeufe auf demselben Pin haben dieselbe
    Adresse mit verschiedenen Bytes belegt, weil Zip und Inno-Installer
    Zeitstempel tragen. Seitdem liegt hier die Regel statt der Gewohnheit.
    """
    datei = tmp_path / "gappa-1.4.0-win_amd64.zip"
    datei.write_bytes(b"neuer Bau")
    hochgeladen = _ohne_netz(monkeypatch, liegt_da=True, etag="fremdes-etag")
    publish_r2.main(["--prefix", "tools/gappa/1.4.0", str(datei)])
    assert hochgeladen == [], "die veroeffentlichte Fassung wurde ersetzt"


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


def test_abweichende_bytes_werden_genannt_nicht_verschwiegen(monkeypatch, tmp_path, capsys):
    """Nicht ueberschreiben heisst nicht schweigen: die Drift gehoert ins Log."""
    datei = tmp_path / "gappa-1.4.0-win_amd64.zip"
    datei.write_bytes(b"neuer Bau")
    _ohne_netz(monkeypatch, liegt_da=True, etag="0" * 32)
    publish_r2.main(["--prefix", "tools/gappa/1.4.0", str(datei)])
    ausgabe = capsys.readouterr().out
    assert "::warning::" in ausgabe and "andere Bytes" in ausgabe


def test_eine_unklare_antwort_ist_kein_freibrief(monkeypatch, tmp_path):
    """HTTP 403 oder 500 heissen 'wir wissen es nicht'. Dann wird nicht
    ueberschrieben, sondern angehalten - sonst entscheidet eine Stoerung
    darueber, ob eine Zusage stehen bleibt."""
    import urllib.error

    def kaputt(anfrage, **egal):
        raise urllib.error.HTTPError("x", 503, "kaputt", {}, None)

    monkeypatch.setattr(publish_r2.urllib.request, "urlopen", kaputt)
    with pytest.raises(SystemExit, match="HTTP 503"):
        publish_r2.liegt_schon_da("tools/gappa/1.4.0/x.zip")
