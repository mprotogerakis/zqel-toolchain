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
import urllib.request

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


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
        put(file, bucket=args.bucket, key=f"{args.prefix}/{file.name}",
            endpoint=args.endpoint, key_id=key_id, secret=secret)
    print(f"  -> https://dl.zqel.org/{args.prefix}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
