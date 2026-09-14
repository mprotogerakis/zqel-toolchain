from __future__ import annotations

import ast
import pathlib
import sys
import tarfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pack_flake  # noqa: E402


def test_same_content_has_same_artifact_hash(tmp_path):
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    assert pack_flake.packe(first) == pack_flake.packe(second)
    assert first.read_bytes() == second.read_bytes()


def test_every_path_named_by_the_flake_is_in_the_artifact(tmp_path):
    artifact = tmp_path / "flake.tar.gz"
    pack_flake.packe(artifact)
    with tarfile.open(artifact) as archive:
        members = {name.split("/", 1)[1]
                   for name in archive.getnames() if "/" in name}
    for relative in pack_flake.referenzierte_pfade(
            (ROOT / "flake.nix").read_text(encoding="utf-8")):
        source = ROOT / relative
        if source.is_file():
            assert relative in members
        else:
            assert any(name.startswith(relative + "/") for name in members)
    assert set(pack_flake.GRUNDSTOCK) <= members


def _instructions_without_docstrings(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)
                if not body:
                    body.append(ast.Pass())
    return ast.unparse(ast.fix_missing_locations(tree))


def test_the_public_probe_is_actually_anonymous():
    source = (ROOT / "tools" / "probe_public_toolchain.py").read_text(
        encoding="utf-8")
    instructions = _instructions_without_docstrings(source)
    for forbidden in ("Authorization", "netrc", "GITHUB_TOKEN", "gh api",
                      "HTTPBasicAuth", "api.github.com"):
        assert forbidden not in instructions


def test_a_missing_flake_path_fails_closed(tmp_path):
    (tmp_path / "flake.nix").write_text(
        'outputs = { x = ./missing/input; };', encoding="utf-8")
    (tmp_path / "flake.lock").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="missing/input"):
        pack_flake.sammle(tmp_path)
