# zqel-toolchain

Public, reproducible Nix packages for external verifier toolchains used by
zqel. This repository carries compatibility packaging, not forks of the
verifier sources.

## Creusot

The `creusot-free` output uses Creusot's official `v0.13.0` flake unchanged on
`x86_64-linux`. On `aarch64-darwin` it retains the same source and toolchain
pins while fixing the Nix build closure for why3find, CVC4, CVC5 and CoCoALib.

Until the first content-addressed release has been published, use a checkout
for evaluation:

```sh
nix profile add .#creusot-free
```

Or use it without changing a profile:

```sh
nix shell .#creusot-free
```

From a checkout:

```sh
scripts/creusot.sh build
scripts/creusot.sh smoke
scripts/creusot.sh shell why3find --version
```

Create the deterministic, SHA-256-named flake artifact with:

```sh
python3 tools/pack_flake.py
```

There is deliberately no `v0.1.0` tag or remote Doctor recipe yet. `main`,
release tags and `latest.json` are navigation, not proof identity. A verdict
must cite the content-addressed tarball, and the Doctor recipe will be added
only together with that published artifact and its generated lock record. See
[`docs/MIGRATION.md`](docs/MIGRATION.md) for the staged move from the private
repository and the pending `toolchain-lock.json` binding.

Supported systems are `x86_64-linux` and `aarch64-darwin`. GitHub is the public
source host and has Actions disabled. The internal Forgejo mirror builds and
smoke-tests the Linux closure without exposing publication credentials. The
Darwin closure is locally proven; a native Forgejo macOS runner is still open
work.

## Upstreaming

The compatibility changes belong upstream in Creusot's
`nix/deps/why3find.nix`, `cvc4.nix` and `cvc5.nix`. This repository remains the
stable installation source until a compatible tagged Creusot release contains
them; it should then reduce to aliases of the upstream outputs.

## License

No repository license has been assigned yet. Choose one before inviting
third-party contributions. Redistributed third-party tools additionally retain
their own notices and corresponding source/provenance obligations.
