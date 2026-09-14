# Migration from the private zqel repository

The public repository contains no deployment secrets. GitHub builds and tests;
the internal Forgejo mirror owns R2 and package credentials and performs
publishing. A workflow that publishes must never run for a pull request and
must fail closed when required credentials are absent on a publishing event.

Migration proceeds in independently green steps:

1. Move `mirror-pin.json`, the mirror/publish/verification programs, their
   redistribution report and their tests.
2. Move the Gappa and matiec pins, complete `tools/windows/` directory,
   packaging workflows and licence dossier.
3. Bind zqel to this flake through the content-addressed artifact mechanism.

The source of migration is a merged zqel revision. In particular,
`verify_public_mirror.py` must not be copied from the unmerged
`issue-335-verify-served-bytes` branch.

## Release identity

`main`, `latest.json` and Git tags are navigation. A proof or artifact record
must cite the SHA-256-named tarball under
`https://dl.zqel.org/flake/<sha256>.tar.gz`. `tools/pack_flake.py` creates that
deterministic artifact and `tools/probe_public_toolchain.py` verifies it from
the consumer side without credentials.

The generated `toolchain-lock.json` is intentionally pending the
`ToolArtifactRecord` design in zqel issue #324. No release tag should be called
proof identity, and zqel must not switch its verdict identity to this separate
repository before that binding and its published-byte test exist.

## Open operational work

- #324: define and bind `ToolArtifactRecord` / `toolchain-lock.json`.
- #327: choose and operate a signed binary cache for the expensive closure.
- #330: add a native `aarch64-darwin` runner to Forgejo. GitHub Actions is
  disabled and must not be used as a paid substitute.
- #335: migrate the post-upload public-byte verification after it is merged.

Do not copy `z3-pin.json`, `zqel/toolchain_registry.py`,
`zqel/doctor_cmd.py`, or `tools/build_dist.py`; those describe or build the
consumer rather than this toolchain.
