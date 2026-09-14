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

## Binary cache

Without a cache, the first `nix shell` compiles the provers. Measured on the
Darwin closure: of 157 store paths, 135 are already in `cache.nixos.org` and
22 are not — and those 22 are exactly the expensive ones (CVC4, CVC5 1.3.1,
cryptominisat, why3 at its git pin, why3find, alt-ergo, glpk, the Rust
nightly chain).

This repository publishes a signed cache that carries **only that gap**;
everything else still comes from upstream. The difference is what makes it
affordable:

| | |
|---|---|
| whole closure | 3.36 GB |
| the gap alone | 1.09 GB uncompressed, roughly 0.38 GB as xz |

The flake declares the substituter itself, so `nix` will ask once whether to
accept it. Answering no is a legitimate choice — you then build from source,
which is slower but not broken. To configure it by hand instead:

```
extra-substituters = https://dl.zqel.org/nix
extra-trusted-public-keys = dl.zqel.org-1:3a0HW0jbmoByRErCR1Oiixjklqib1uTQ2/yUXvBIrt4=
```

A substituter you trust is load-bearing: whoever holds the key influences
which prover runs on your machine. The private half exists only as a CI
secret; nothing in this repository can sign.

Check what the cache actually serves, from anywhere, without credentials:

```sh
python3 tools/verify_nix_cache.py .#packages.x86_64-linux.creusot-free
```

### What is not published yet, and why

Only the `x86_64-linux` half. The Darwin closure can be **built** on a Mac and
is locally proven, but it cannot be **published** from one: R2 credentials
exist solely as Forgejo secrets, and Forgejo has no macOS runner (12 jobs on
`ubuntu-latest`, 3 on `windows-amd64`, none on macOS). So the one machine that
can produce those bytes cannot upload them, and the one place that can upload
cannot produce them.

### Publishing the Darwin half from a laptop

Until a dedicated Apple Silicon runner exists, a Mac can join Forgejo for the
length of one job. That keeps the rule intact rather than bending it: the
credentials still come from Forgejo, land on the machine only while the job
runs, and are gone afterwards. A laptop holding standing credentials would be
the worse trade.

```sh
FORGEJO_RUNNER_TOKEN=... scripts/attach_macos_runner.sh
```

Then trigger **Publish the Darwin binary cache** in Forgejo, and stop the
runner with Ctrl-C.

What makes this workable:

- The runner only ever connects **outward** — it long-polls over HTTPS/2, the
  server never calls back. No inbound port, no tunnel. Measured over the
  university VPN on 2026-09-14: the runner RPC path answers `400`, not `404`,
  so the route exists and only the payload was wrong.
- It registers with the `:host` label, so the job runs directly on the machine
  and uses its `/nix/store`. On a Mac that has already built `creusot-free`
  this turns hours of compiling into minutes of copying. A container would see
  an empty store and rebuild everything.
- The job installs nothing. It looks for the machine's own `nix`, and if the
  runner's account cannot see it, it says so and names the account — the
  failure mode that cost two Windows nightlies was exactly this.

What to weigh before starting it: a host runner executes jobs with the
privileges of whoever started it, and the workflow is therefore
`workflow_dispatch`-only. If the VPN drops mid-job the run dies; that is a
retry, not damage, because the cache is content-addressed.

## Upstreaming

The compatibility changes belong upstream in Creusot's
`nix/deps/why3find.nix`, `cvc4.nix` and `cvc5.nix`. This repository remains the
stable installation source until a compatible tagged Creusot release contains
them; it should then reduce to aliases of the upstream outputs.

## License

No repository license has been assigned yet. Choose one before inviting
third-party contributions. Redistributed third-party tools additionally retain
their own notices and corresponding source/provenance obligations.
