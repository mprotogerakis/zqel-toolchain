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

#: EINE ADRESSE TRAEGT DEN LETZTEN BAU. Umgestellt am 2026-09-23.
#:
#: Bis hierhin galt `tools/` als unveraenderlich: wer eine benannte Version
#: zitiert, meine bestimmte Bytes, also blieb die erste Fassung liegen. Der
#: Gedanke war richtig, die Wirkung nicht. Der Windows-Bau ist NICHT
#: reproduzierbar (gemessen: gappa.exe, gleiche Groesse, dreimal
#: verschiedener Hash), also weicht jeder Lauf ab, also blieb IMMER der alte
#: Stand liegen - und das Chocolatey-Paket daneben war der neue. Genau diese
#: Schere hat zqel-gappa 1.4.0 am 21.09. aus der Freigabe geworfen.
#:
#: Die Reibung sollte eine Entscheidung erzwingen. Sie hat stattdessen einen
#: Handgriff erzwungen - vier Objekte von Hand loeschen, vor jedem Lauf -
#: und ein vergessener Handgriff ist keine Entscheidung, sondern ein
#: Ausfall. Zweimal passiert, beide Male teuer.
#:
#: Jetzt gilt eine Regel fuer alles: hochgeladen wird, was der Lauf gebaut
#: hat, es sei denn, dort liegen schon genau dieselben Bytes. Ersetzen wird
#: GEMELDET, nicht verschwiegen.
#:
#: Was an die Stelle der Zusage tritt: wer bestimmte Bytes meint, nennt
#: ihren sha256, nicht ihre Adresse. Deshalb steht er seit dem 2026-09-23 in
#: VERIFICATION.txt, in den .sha256-Beilagen und in den winget-Manifesten.
#: Und damit eine Adresse sich nicht ungefragt bewegt, reicht der
#: Chocolatey-Schritt nur noch bei einem Lauf von Hand ein - der Cron baut
#: und misst, er veroeffentlicht nicht mehr nach draussen.


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
        # Eine 403 oder 500 heisst "wir wissen es nicht". Bis zum
        # 2026-09-23 hat das den Lauf angehalten, weil nicht ueberschrieben
        # werden durfte. Jetzt gilt umgekehrt: im Zweifel gilt, was der Lauf
        # gebaut hat - eine Stoerung beim LESEN darf die Auslieferung nicht
        # aufhalten.
        print(f"  {key}: HEAD antwortet HTTP {fehler.code} - wird geschrieben")
        return False, ""
    except OSError as fehler:
        print(f"  {key}: Adresse nicht lesbar "
              f"({type(fehler).__name__}: {fehler}) - wird geschrieben")
        return False, ""


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


def _liegt_schon_genau_so_da(file: pathlib.Path, key: str) -> bool:
    """Liegen dort schon GENAU diese Bytes? Nur dann wird nicht hochgeladen.

    Das ist eine Ersparnis, kein Schutz: derselbe Inhalt noch einmal zu
    schreiben kostet nur Zeit. Alles andere - andere Bytes, unklares ETag,
    Adresse nicht lesbar - fuehrt zum Upload. Im Zweifel gilt, was der Lauf
    gebaut hat.

    WARUM DER ZWEIFEL JETZT FUER DAS ERSETZEN SPRICHT (2026-09-23):
    Vorher hat er dagegen gesprochen, und das hat zweimal eine halbe
    Auslieferung hinterlassen. Am 2026-09-17 galten vier geloeschte Objekte
    als vorhanden, weil der Cloudflare-Cache sie noch kannte; zurueck blieben
    zwei .sha256-Beilagen ohne ihre Dateien. Am 2026-09-21 blieb das Zip vom
    17. liegen, waehrend das Chocolatey-Paket schon der neue Bau war.
    Beide Male war "nicht anfassen" die vorsichtige Wahl und trotzdem die
    falsche.
    """
    da, etag = liegt_schon_da(key)
    if not da:
        return False
    md5 = hashlib.md5(file.read_bytes()).hexdigest()
    if etag == md5:
        print(f"  {file.name:52s} unveraendert (schon veroeffentlicht)")
        return True
    if "-" in etag or not etag:
        print(f"  {file.name:52s} ETag nicht vergleichbar - wird ersetzt")
        return False
    # Laut, aber kein Abbruch: das ist der Normalfall eines zweiten Baus.
    print(f"  {file.name:52s} wird ERSETZT (veroeffentlicht md5 {etag}, "
          f"hier md5 {md5})")
    return False


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
        if _liegt_schon_genau_so_da(file, key):
            continue
        put(file, bucket=args.bucket, key=key,
            endpoint=args.endpoint, key_id=key_id, secret=secret)
    print(f"  -> https://dl.zqel.org/{args.prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
