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
