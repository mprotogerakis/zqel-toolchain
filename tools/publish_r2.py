#!/usr/bin/env python3
"""Upload files to the public dl.zqel.org Cloudflare R2 bucket.

The implementation uses only Python's standard library and signs S3 PUT
requests with AWS Signature Version 4.  Endpoint and credentials are supplied
by Forgejo secrets; this public repository contains none of their values.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import os
import pathlib
import urllib.error
import urllib.request
import uuid

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

#: Die oeffentliche Adresse, unter der der Bucket gelesen wird. Geprueft wird
#: HIER, nicht am S3-Endpunkt: es geht um das, was ein Fremder bekommt.
OEFFENTLICH = "https://dl.zqel.org"

#: Adressen, die eine ZUSAGE sind und deshalb nicht mehr wandern duerfen.
#:
#: Unter tools/<werkzeug>/<version>/ liegt ein benanntes Artefakt einer
#: benannten Version. Wer es zitiert, meint bestimmte Bytes. Gemessen am
#: 2026-09-15: zwei Laeufe auf demselben Pin haben gappa-1.4.0-win_amd64.zip
#: zweimal veroeffentlicht - mit verschiedenen Bytes, weil Zip und
#: Inno-Installer Zeitstempel tragen. Dieselbe Adresse meinte an zwei Tagen
#: zwei Dateien, und nichts wurde deswegen rot.
#:
#: NICHT hier stehen duerfen: flake/latest.json und die uebrigen
#: Navigationsadressen - die MUESSEN sich bewegen; der Cache unter nix/, wo
#: ein neu signiertes narinfo rechtmaessig ersetzt wird; und
#: flake/<sha256>.tar.gz, das seinen Inhalt schon im Namen traegt.
UNVERAENDERLICH = ("tools/",)


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    key = _sign(("AWS4" + secret).encode("utf-8"), date)
    key = _sign(key, region)
    key = _sign(key, service)
    return _sign(key, "aws4_request")


def authorization(*, method: str, host: str, path: str, payload_hash: str,
                  key_id: str, secret: str, region: str, service: str,
                  now: dt.datetime,
                  extra: dict[str, str] | None = None) -> dict[str, str]:
    """Return SigV4 headers for one request; kept pure for vector tests."""
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    headers = {"host": host, "x-amz-date": timestamp}
    headers.update({key.lower(): value for key, value in (extra or {}).items()})
    names = sorted(headers)
    canonical_headers = "".join(
        f"{name}:{headers[name].strip()}\n" for name in names)
    signed_headers = ";".join(names)
    canonical_request = (
        f"{method}\n{path}\n\n{canonical_headers}\n"
        f"{signed_headers}\n{payload_hash}")
    scope = f"{date}/{region}/{service}/aws4_request"
    to_sign = (
        "AWS4-HMAC-SHA256\n" + timestamp + "\n" + scope + "\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest())
    signature = hmac.new(
        signing_key(secret, date, region, service),
        to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}")
    return headers


def _content_type(name: str) -> str:
    return {
        ".gz": "application/gzip",
        ".json": "application/json",
        ".py": "text/x-python; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }.get(pathlib.Path(name).suffix, "application/octet-stream")


def liegt_schon_da(key: str) -> tuple[bool, str]:
    """Antwortet die oeffentliche Adresse - und mit welchem ETag?

    R2 setzt bei einem einfachen PUT die MD5-Summe als ETag. Das genuegt, um
    "dieselbe Datei" von "andere Datei unter demselben Namen" zu trennen; ein
    zusammengesetztes ETag (Suffix -N) traegt diese Aussage nicht und wird als
    unbekannt behandelt.
    """
    # AM CACHE VORBEI, und das ist keine Vorsicht, sondern eine Messung:
    # dl.zqel.org liegt hinter Cloudflare, und ein HEAD auf die blanke
    # Adresse beantwortet die Frage "liegt das im Bucket?" mit dem, was im
    # CACHE liegt. Gemessen am 2026-09-17 (Lauf #85): vier Objekte von Hand
    # geloescht, dann veroeffentlicht - die beiden .sha256 waren aus dem
    # Cache gefallen und wurden geschrieben, Zip und Installer antworteten
    # noch mit 200 aus dem Cache und wurden uebersprungen. Ergebnis: zwei
    # Beilagen, die den Hash von Dateien nennen, die es nicht gibt, und zwei
    # tote Downloadadressen in der README. Der Lauf war gruen.
    #
    # Der Parameter gehoert in den Cache-Schluessel, deshalb wirkt er;
    # `Cache-Control: no-cache` allein tut es bei Cloudflare nicht.
    req = urllib.request.Request(
        f"{OEFFENTLICH}/{key}?nocache={uuid.uuid4().hex}", method="HEAD",
        headers={"User-Agent": "zqel-publish-r2", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as antwort:
            return True, antwort.headers.get("ETag", "").strip('"')
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            return False, ""
        # Alles andere ist KEIN "gibt es nicht": eine 403 oder 500 hiesse,
        # wir wissen es nicht - und dann darf nicht ueberschrieben werden.
        raise SystemExit(f"{key}: HEAD antwortet HTTP {fehler.code}")
    except OSError as fehler:
        raise SystemExit(
            f"{key}: die oeffentliche Adresse ist nicht erreichbar "
            f"({type(fehler).__name__}: {fehler})")


def put(file: pathlib.Path, *, bucket: str, key: str, endpoint: str,
        key_id: str, secret: str) -> None:
    payload = file.read_bytes()
    payload_hash = hashlib.sha256(payload).hexdigest()
    host = endpoint.split("://", 1)[1].rstrip("/")
    path = f"/{bucket}/{key}"
    headers = authorization(
        method="PUT", host=host, path=path, payload_hash=payload_hash,
        key_id=key_id, secret=secret, region="auto", service="s3",
        # dt.timezone.utc, NICHT dt.UTC: letzteres gibt es erst ab
        # Python 3.11. Der Darwin-Lauf am 2026-09-14 starb daran, weil im
        # PATH des Runners ein 3.10 aus /Library/Frameworks vorn stand -
        # nach 314 MB fertig gepacktem und signiertem Cache, unmittelbar
        # vor dem Hochladen.
        now=dt.datetime.now(dt.timezone.utc),
        extra={"content-type": _content_type(file.name),
               "x-amz-content-sha256": payload_hash})
    request = urllib.request.Request(
        endpoint.rstrip("/") + path, data=payload, method="PUT",
        headers=headers)
    with urllib.request.urlopen(request, timeout=300) as response:
        if response.status not in (200, 201):
            raise SystemExit(f"{file.name}: HTTP {response.status}")
    print(f"  {file.name:52s} {len(payload):9d} bytes  sha256 {payload_hash}")


def _schon_veroeffentlicht(file: pathlib.Path, key: str) -> bool:
    """Liegt unter dieser unveraenderlichen Adresse schon etwas?

    Dann bleibt es liegen. NICHT weil ein zweiter Bau nichts wert waere - der
    woechentliche Lauf prueft, ob die Bauanleitung auf einer fortgeschriebenen
    MSYS2-Toolchain noch traegt, und das ist sein Ertrag. Sondern weil das Zip
    dieser Version schon jemand zitiert haben koennte.

    KEIN Abbruch, sondern eine Meldung: der Unterschied besteht heute aus
    Zeitstempeln, nicht aus anderem Verhalten. Ein Lauf, der deswegen jeden
    Montag rot waere, bringt man allen nur bei zu ignorieren - dieselbe
    Begruendung, aus der der Upload in die Paketregistry eine 409 als
    "unveraendert" verbucht hat. Abweichende Bytes werden trotzdem GENANNT,
    als ::warning::, damit die Drift im Log steht.

    Wer eine veroeffentlichte Adresse wirklich ersetzen muss, loescht sie
    vorher von Hand. Das ist die Reibung, die es braucht.
    """
    da, etag = liegt_schon_da(key)
    if not da:
        return False
    md5 = hashlib.md5(file.read_bytes()).hexdigest()
    if etag == md5:
        print(f"  {file.name:52s} unveraendert (schon veroeffentlicht)")
    elif "-" in etag or not etag:
        print(f"  {file.name:52s} liegt schon da (ETag nicht vergleichbar)")
    else:
        print(f"::warning::{key} liegt bereits mit anderen Bytes "
              f"(veroeffentlicht md5 {etag}, hier md5 {md5}). Die "
              f"veroeffentlichte Fassung bleibt - sie koennte zitiert sein.")
        print(f"  {file.name:52s} NICHT ersetzt (andere Bytes)")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET", "zqel"))
    parser.add_argument("--endpoint", default=os.environ.get("R2_ENDPOINT", ""))
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    key_id = os.environ.get("R2_ID", "")
    secret = os.environ.get("R2_SECRET", "")
    if not (key_id and secret and args.endpoint and args.bucket):
        raise SystemExit(
            "R2_ID, R2_SECRET, R2_ENDPOINT and R2_BUCKET must be set")

    for name in args.files:
        file = pathlib.Path(name)
        if not file.is_file():
            raise SystemExit(f"missing file: {file}")
        key = f"{args.prefix}/{file.name}"
        if key.startswith(UNVERAENDERLICH) and _schon_veroeffentlicht(file, key):
            continue
        put(file, bucket=args.bucket, key=key,
            endpoint=args.endpoint, key_id=key_id, secret=secret)
    print(f"  -> https://dl.zqel.org/{args.prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
