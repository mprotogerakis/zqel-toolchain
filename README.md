# zqel-toolchain

Public, reproducible Nix packages for external verifier toolchains used by
zqel. This repository carries compatibility packaging, not forks of the
verifier sources.

## Creusot

The `creusot-free` output uses Creusot's official `v0.13.0` flake unchanged on
`x86_64-linux`. On `aarch64-darwin` it retains the same source and toolchain
pins while fixing the Nix build closure for why3find, CVC4, CVC5 and CoCoALib.

Install the complete wrapper persistently:

```sh
nix profile add github:mprotogerakis/zqel-toolchain/v0.1.0#creusot-free
```

Or use it without changing a profile:

```sh
nix shell github:mprotogerakis/zqel-toolchain/v0.1.0#creusot-free
```

From a checkout:

```sh
scripts/creusot.sh build
scripts/creusot.sh smoke
scripts/creusot.sh shell why3find --version
```

Supported systems are `x86_64-linux` and `aarch64-darwin`. The GitHub Actions
matrix builds and smoke-tests the full closure on both native architectures.

## Upstreaming

The compatibility changes belong upstream in Creusot's
`nix/deps/why3find.nix`, `cvc4.nix` and `cvc5.nix`. This repository remains the
stable installation source until a compatible tagged Creusot release contains
them; it should then reduce to aliases of the upstream outputs.

## License

No license has been assigned yet. Choose one before inviting third-party
contributions or redistributing code from this repository.
