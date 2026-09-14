# zqel-toolchain

The verifiers zqel calls, packaged so that the same versions run on your
machine as in the gate — and so that a verdict can name what produced it.

---

## Why this repository exists

A proof is only as trustworthy as the prover that produced it. If your Debian
ships Gappa 1.8.2 and the gate ran 1.4.0, the two of you are not checking the
same thing — and nothing in the output says so. This repository fixes the
verifiers by **pin**, builds them reproducibly, and publishes the results with
their licences and their sources, so that "which prover?" always has an answer.

Three things follow from that, and they shape everything below:

**A pin is an identity, not an update policy.** `main`, release tags and
`latest.json` are navigation. A verdict must cite the content-addressed
artifact — the SHA-256 URL — because that is the only name that cannot change
under it.

**The newest version is rarely the right one.** Gappa 1.8.3 exists; we pin
1.4.0 because that is what the development shell has. Moving the pin is a
decision someone makes, not something that happens.

**Redistribution carries obligations.** Every binary here travels with its
licence text and a pointer to the exact source it was built from. That is the
condition under which we may pass it on at all, not paperwork after the fact.

---

## The tools

| Tool | Version | What it does | Source | Licence |
|---|---|---|---|---|
| **Creusot** | 0.13.0 | proves the generated Rust deductively | [creusot-rs/creusot](https://github.com/creusot-rs/creusot) | LGPL-2.1 |
| **Why3** | git `54c92f9` | the proof platform Creusot talks to | [why3](https://why3.lri.fr/) | LGPL-2.1 |
| **why3find** | 1.3.0+dev | drives Why3 across a project | via Creusot | LGPL-2.1 |
| **Alt-Ergo** | 2.4.3-free | SMT solver for Why3 | [alt-ergo](https://alt-ergo.ocamlpro.com/) | Apache-2.0 |
| **Z3** | 4.15.3 | SMT solver for Why3 | [Z3Prover/z3](https://github.com/Z3Prover/z3) | MIT |
| **CVC5** | 1.3.1 · 1.2.0 mirrored | SMT solver | [cvc5/cvc5](https://github.com/cvc5/cvc5) | BSD-3-Clause |
| **CVC4** | 1.8 | SMT solver Why3 still uses | [CVC4](https://cvc4.github.io/) | BSD-3-Clause |
| **Gappa** | 1.4.0 | proves float64 rounding bounds | [gappa/gappa](https://gitlab.inria.fr/gappa/gappa) | CeCILL-2.1 **AND** GPL-3.0-or-later |
| **matiec** | 0.1 rev `7949c0b` | re-checks generated ST on an independent toolchain | [beremiz/matiec](https://github.com/beremiz/matiec) | GPL-3.0-or-later AND LGPL-3.0-or-later |
| **CBMC** | 6.4.0 | bounded model checking | [diffblue/cbmc](https://github.com/diffblue/cbmc) | BSD-4-Clause |
| **Kani** | 0.67.0 | model-checks the generated Rust | [model-checking/kani](https://github.com/model-checking/kani) | Apache-2.0 **OR** MIT |

Two notes that are easy to miss. matiec reports version `0.1` for *every*
revision, so it is pinned by revision, not by version. And Z3 appears twice in
zqel's world: 4.15.3 here for Why3, and a separately pinned build that travels
*inside* the zqel package — that one is pinned by artifact hash, not version.

### Where each one runs

Two different things are called "Nix" below, and the difference matters.
**This flake** is `tarball+https://dl.zqel.org/flake/<sha256>.tar.gz#<attr>` —
it carries what nixpkgs does not. **nixpkgs** carries Gappa and CBMC already,
and in release 24.11 it carries *exactly* the pinned versions — measured:
`gappa 1.4.0`, `cbmc 6.4.0`. That is not a coincidence: those versions are
pinned *because* that is what the development shell has.

| | Linux x86_64 | macOS arm64 | Windows x86_64 |
|---|---|---|---|
| Creusot, Why3, why3find, Alt-Ergo, CVC4 | this flake, `#creusot-free` | this flake, `#creusot-free` | builds, but Why3 is missing |
| matiec | this flake, `#matiec` | this flake, `#matiec` | [installer](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-0.1-7949c0b-win_amd64-setup.exe) · [zip](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-0.1-7949c0b-win_amd64.zip) · [source](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-7949c0b.tar.gz) |
| Gappa | nixpkgs 24.11 — `nix shell nixpkgs#gappa` | nixpkgs 24.11 | [installer](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0-win_amd64-setup.exe) · [zip](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0-win_amd64.zip) · [source](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0.tar.gz) |
| CBMC | nixpkgs 24.11 — `nix shell nixpkgs#cbmc` | nixpkgs 24.11 | [msi](https://dl.zqel.org/tools/cbmc/6.4.0/cbmc-6.4.0-win64.msi) · [licence](https://dl.zqel.org/tools/cbmc/6.4.0/cbmc-6.4.0-LICENSE.txt) |
| CVC5 (standalone) | via `#creusot-free` (1.3.1) | via `#creusot-free` (1.3.1) | [zip](https://dl.zqel.org/tools/cvc5/1.2.0/cvc5-Win64-x86_64-static.zip) (1.2.0) |

A **newer** nixpkgs is not automatically better here: current nixpkgs carries
`cbmc 6.10.0`, and that is a different prover from the one the gate ran. Pin
the nixpkgs release, not just the package.
| Kani | [x86_64](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz) · [arm64](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-aarch64-unknown-linux-gnu.tar.gz) | [x86_64](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-x86_64-apple-darwin.tar.gz) · [arm64](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-aarch64-apple-darwin.tar.gz) | upstream refuses Windows |

Every mirrored archive has a `.notice.txt` beside it naming the licence and
the exact upstream release. **CBMC derives its machine model from the host**,
so a Windows CBMC and a Linux CBMC do not answer the same question.

---

## The Nix flakes, and which is which

There are two, and confusing them is the most common mistake.

**This repository's flake** packages the *verifiers*. Its one output today is
`creusot-free` — Creusot with Why3, why3find and the solvers, as one closure.
On `x86_64-linux` it uses Creusot's own `v0.13.0` flake unchanged. On
`aarch64-darwin` it keeps the same source and toolchain pins but repairs the
build closure: `darwin.sigtool` for why3find (dune calls `codesign` when it
links native OCaml executables), `<cstddef>` includes for CVC4, CLN swapped
for GMP where the pinned Darwin CLN and CVC4 disagree about the C++ ABI, and a
patched CoCoALib for CVC5.

**zqel's own flake** is the development shell for working *on* zqel. It is a
different thing at a different address and you usually do not want it.

| | Address |
|---|---|
| this toolchain | `https://dl.zqel.org/flake/latest.json` → the SHA-256 URL |
| binary cache | `https://dl.zqel.org/nix` |
| zqel's dev shell | `https://dl.zqel.org/zqel/flake/latest.json` |

### The binary cache, and the one line that decides whether you get it

Without a cache the first run **compiles the provers**. Measured on the Darwin
closure: 157 store paths, of which 135 are already in `cache.nixos.org` and 22
are not — and those 22 are the expensive ones (CVC4, CVC5 1.3.1, cryptominisat,
Why3 at its git pin, why3find, Alt-Ergo, glpk, the Rust nightly chain).

This repository publishes a signed cache carrying **only that gap**; everything
else still comes from upstream. That is what keeps it small:

| | |
|---|---|
| whole closure | 3.36 GB |
| the gap alone | 1.09 GB uncompressed, roughly 0.38 GB as xz |

The flake declares the substituter itself — **but that only works if you are a
trusted user.** Everyone else sees

```
warning: ignoring untrusted flake configuration setting 'extra-substituters'
```

and builds from source anyway. On a default multi-user install `trusted-users`
is `root` alone, so this is the normal case, not the exception. The installation
steps below therefore configure the cache explicitly rather than relying on the
flake to do it.

---

## Installing it

### Linux (x86_64)

```console
$ sudo tee -a /etc/nix/nix.conf <<'EOF'
extra-substituters = https://dl.zqel.org/nix
extra-trusted-public-keys = dl.zqel.org-1:3a0HW0jbmoByRErCR1Oiixjklqib1uTQ2/yUXvBIrt4=
EOF
$ sudo systemctl restart nix-daemon
```

Then take the current pin and enter a shell with the verifiers on `PATH`:

```console
$ HASH=$(curl -s https://dl.zqel.org/flake/latest.json | sed -n 's/.*"sha256": "\([^"]*\)".*/\1/p')
$ nix shell "tarball+https://dl.zqel.org/flake/$HASH.tar.gz#creusot-free"
$ cargo-creusot --help && why3 --version && z3 --version
```

Cite `$HASH` when you record a verdict. `latest.json` tells you *which* pin is
current; it is not itself an identity.

### macOS (Apple Silicon)

Same cache configuration — macOS has no systemd, so the daemon is restarted
through launchd:

```console
$ sudo tee -a /etc/nix/nix.conf <<'EOF'
extra-substituters = https://dl.zqel.org/nix
extra-trusted-public-keys = dl.zqel.org-1:3a0HW0jbmoByRErCR1Oiixjklqib1uTQ2/yUXvBIrt4=
EOF
$ sudo launchctl kickstart -k system/org.nixos.nix-daemon
```

```console
$ HASH=$(curl -s https://dl.zqel.org/flake/latest.json | sed -n 's/.*"sha256": "\([^"]*\)".*/\1/p')
$ nix shell "tarball+https://dl.zqel.org/flake/$HASH.tar.gz#creusot-free"
$ cargo-creusot --help && why3find --version
```

Both halves of the cache are published, so this fetches rather than builds.

### Windows

There is no flake. Take the installers from the table above, then point zqel at
matiec:

```powershell
PS> setx MATIEC_DIR "C:\Program Files\matiec"
```

Kani does not run on Windows at all, and Creusot builds but has no Why3 there.
For those two, use Linux.

### Check what you actually got

```console
$ python3 tools/verify_nix_cache.py .#packages.x86_64-linux.creusot-free
```

This asks the public address, without credentials, whether every path we are
supposed to carry is there and carries our signature. It runs from any machine
with Python — including one that has never seen our network.

---

### What the mirror carries

Third-party binaries are mirrored from their upstream releases, never repacked.
Each archive travels with a `.notice.txt` naming its licence and the exact
release it came from — that is the condition under which we may pass it on.

`mirror-pin.json` holds the pinned versions and their SHA-256; the mirror runs
only when that file changes. Afterwards the workflow **re-reads the public
address** and checks the bytes it actually serves against the pin, because
until then only the *downloaded* artifact had been verified.

```console
$ python3 tools/verify_public_mirror.py          # reachability and size
$ python3 tools/verify_public_mirror.py --hash   # and the content, ~600 MB
```

## For maintainers

```console
$ scripts/creusot.sh build      # build the closure
$ scripts/creusot.sh smoke      # run the flake's own smoke check
$ python3 tools/pack_flake.py   # the deterministic, SHA-256-named artifact
```

Publication happens on the internal Forgejo mirror, which holds the credentials;
GitHub is the public source host and has Actions disabled. Nothing in this
repository can sign or upload.

A substituter you trust is load-bearing: whoever holds the key influences which
prover runs on your machine. The private half exists only as a CI secret.

---

## Open work

**The Darwin cache is published by hand.** Linux is filled automatically on
every `publish-flake`; macOS needs someone to attach a Mac and trigger
*Publish the Darwin binary cache*. It works — verified from outside the
network on 2026-09-14: `cache.nixos.org` answers 404 for
`creusot-wrapped`, this cache answers 200 with our signature, and the NAR is
retrievable — but it does not happen on its own, so the Darwin half can fall
behind the flake without anything going red.

Until a dedicated Apple Silicon runner exists, `scripts/attach_macos_runner.sh`
attaches a laptop for the length of one job. Four things only showed up there,
because a **host runner has a terminal and a container does not**: `git` did
not know the instance CA and `NIX_SSL_CERT_FILE` pointed at a Linux path;
`git log` opened a pager and waited; `nix` asked whether to accept our own
`nixConfig` and waited; and the runner's `PATH` had a Python 3.10 in front,
where `datetime.UTC` does not exist. All four are fixed and pinned by tests —
but they are the reason a real runner is worth more than a careful guess.

**The lock is generated, but zqel does not read it yet.**
`toolchain-lock.json` now names what this repository publishes — versions,
licences, the finished addresses, the flake hash and the cache key — and CI
refuses to publish if it has drifted from the pins. The other half is still
open: zqel must vendor it and check against it, so that a verdict names the
toolchain that produced it by more than convention.

**Upstreaming.** The Darwin compatibility changes belong in Creusot's
`nix/deps/why3find.nix`, `cvc4.nix` and `cvc5.nix`. This repository should
shrink to aliases of the upstream outputs once a tagged Creusot release carries
them.

---

## Licence

No repository licence has been assigned yet — choose one before inviting
outside contributions. Redistributed third-party tools keep their own notices
and their source-and-provenance obligations regardless.

---

<!-- downloads:anfang -->

## Everything we publish on `dl.zqel.org`

Generated by `tools/write_download_table.py`, which derives every
address from the pins and then **measures it anonymously** — one
unauthenticated `HEAD` per row, the way an outsider fetches it. A row
marked `missing` is something this project promises and does not
currently deliver; that is deliberate, so the gap is visible here
rather than in someone's terminal.

45 of 47 addresses answered, 903.0 MB in total.

| Group | File | Platform | Size (measured 2026-09-14) |
| --- | --- | --- | --- |
| cbmc 6.4.0 (mirrored) | [cbmc-6.4.0-win64.msi](https://dl.zqel.org/tools/cbmc/6.4.0/cbmc-6.4.0-win64.msi) | Windows | 25.7 MB |
|  | [cbmc-6.4.0-win64.msi.notice.txt](https://dl.zqel.org/tools/cbmc/6.4.0/cbmc-6.4.0-win64.msi.notice.txt) | — | 1 KB |
|  | [cbmc-6.4.0-LICENSE.txt](https://dl.zqel.org/tools/cbmc/6.4.0/cbmc-6.4.0-LICENSE.txt) | — | 2 KB |
| cvc5 1.2.0 (mirrored) | [cvc5-Win64-x86_64-static.zip](https://dl.zqel.org/tools/cvc5/1.2.0/cvc5-Win64-x86_64-static.zip) | Windows x86_64 | 26.1 MB |
|  | [cvc5-Win64-x86_64-static.zip.notice.txt](https://dl.zqel.org/tools/cvc5/1.2.0/cvc5-Win64-x86_64-static.zip.notice.txt) | — | 1 KB |
| kani 0.67.0 (mirrored) | [kani-0.67.0-aarch64-apple-darwin.tar.gz](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-aarch64-apple-darwin.tar.gz) | macOS arm64 | 99.3 MB |
|  | [kani-0.67.0-aarch64-apple-darwin.tar.gz.notice.txt](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-aarch64-apple-darwin.tar.gz.notice.txt) | — | 1 KB |
|  | [kani-0.67.0-aarch64-unknown-linux-gnu.tar.gz](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-aarch64-unknown-linux-gnu.tar.gz) | Linux arm64 | 131.4 MB |
|  | [kani-0.67.0-aarch64-unknown-linux-gnu.tar.gz.notice.txt](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-aarch64-unknown-linux-gnu.tar.gz.notice.txt) | — | 1 KB |
|  | [kani-0.67.0-x86_64-apple-darwin.tar.gz](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-x86_64-apple-darwin.tar.gz) | macOS x86_64 | 104.5 MB |
|  | [kani-0.67.0-x86_64-apple-darwin.tar.gz.notice.txt](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-x86_64-apple-darwin.tar.gz.notice.txt) | — | 1 KB |
|  | [kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz) | Linux x86_64 | 136.7 MB |
|  | [kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz.notice.txt](https://dl.zqel.org/tools/kani/0.67.0/kani-0.67.0-x86_64-unknown-linux-gnu.tar.gz.notice.txt) | — | 1 KB |
| gappa 1.4.0 (our build) | [gappa-1.4.0-win_amd64.zip](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0-win_amd64.zip) | Windows x86_64 | 6.6 MB |
|  | [gappa-1.4.0-win_amd64.zip.sha256](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0-win_amd64.zip.sha256) | Windows x86_64 | 93 B |
|  | [gappa-1.4.0-win_amd64-setup.exe](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0-win_amd64-setup.exe) | Windows x86_64 | 6.7 MB |
|  | [gappa-1.4.0-win_amd64-setup.exe.sha256](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0-win_amd64-setup.exe.sha256) | Windows x86_64 | 99 B |
|  | [gappa-1.4.0.tar.gz](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0.tar.gz) | source | 379 KB |
|  | [gappa-1.4.0.tar.gz.sha256](https://dl.zqel.org/tools/gappa/1.4.0/gappa-1.4.0.tar.gz.sha256) | source | 86 B |
| matiec 0.1-7949c0b (our build) | [matiec-0.1-7949c0b-win_amd64.zip](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-0.1-7949c0b-win_amd64.zip) | Windows x86_64 | 4.5 MB |
|  | [matiec-0.1-7949c0b-win_amd64.zip.sha256](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-0.1-7949c0b-win_amd64.zip.sha256) | Windows x86_64 | 100 B |
|  | [matiec-0.1-7949c0b-win_amd64-setup.exe](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-0.1-7949c0b-win_amd64-setup.exe) | Windows x86_64 | 4.8 MB |
|  | [matiec-0.1-7949c0b-win_amd64-setup.exe.sha256](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-0.1-7949c0b-win_amd64-setup.exe.sha256) | Windows x86_64 | 106 B |
|  | [matiec-7949c0b.tar.gz](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-7949c0b.tar.gz) | source | 713 KB |
|  | [matiec-7949c0b.tar.gz.sha256](https://dl.zqel.org/tools/matiec/0.1-7949c0b/matiec-7949c0b.tar.gz.sha256) | source | 89 B |
| toolchain flake | [6820409c349b….tar.gz](https://dl.zqel.org/flake/6820409c349bb527cb9dc738ed6ac6736f496013095ae89d715e1c12b5121140.tar.gz) | Linux, macOS | 5 KB ·moves |
|  | [latest.json](https://dl.zqel.org/flake/latest.json) | — | 551 B |
|  | [probe_public_toolchain.py](https://dl.zqel.org/flake/probe_public_toolchain.py) | — | 7 KB |
| nix binary cache | [nix-cache-info](https://dl.zqel.org/nix/nix-cache-info) | Linux, macOS | 21 B |
| zqel devShell flake | [fe62a13d860c….tar.gz](https://dl.zqel.org/zqel/flake/fe62a13d860c2d80181107e9b62eac74f24c07a119d5805db6479ff9d09d0bd7.tar.gz) | Linux, macOS | 11 KB ·moves |
|  | [latest.json](https://dl.zqel.org/zqel/flake/latest.json) | — | 566 B |
| zqel (latest) | zqel-latest-linux-x86_64.tar.gz | Linux x86_64 | **missing (404)** |
|  | zqel-latest-linux-x86_64.tar.gz.sha256 | Linux x86_64 | **missing (404)** |
|  | [zqel-latest-windows-amd64.zip](https://dl.zqel.org/zqel/latest/zqel-latest-windows-amd64.zip) | Windows x86_64 | 59.9 MB |
|  | [zqel-latest-windows-amd64.zip.sha256](https://dl.zqel.org/zqel/latest/zqel-latest-windows-amd64.zip.sha256) | Windows x86_64 | 66 B |
| Z3 pin (z3-nightly-0d4a2db) | [z3-pin.json](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3-pin.json) | — | 9 KB |
|  | [z3-src-0d4a2dbb188d.tar.gz](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3-src-0d4a2dbb188d.tar.gz) | — | 6.5 MB |
|  | [z3_solver-5.1.0.0-py3-none-macosx_11_0_arm64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-macosx_11_0_arm64.whl) | macOS arm64 | 37.9 MB |
|  | [z3_solver-5.1.0.0-py3-none-macosx_11_0_x86_64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-macosx_11_0_x86_64.whl) | macOS x86_64 | 40.3 MB |
|  | [z3_solver-5.1.0.0-py3-none-macosx_13_3_arm64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-macosx_13_3_arm64.whl) | macOS arm64 | 37.9 MB |
|  | [z3_solver-5.1.0.0-py3-none-macosx_13_3_x86_64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-macosx_13_3_x86_64.whl) | macOS x86_64 | 40.3 MB |
|  | [z3_solver-5.1.0.0-py3-none-manylinux_2_27_x86_64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-manylinux_2_27_x86_64.whl) | Linux x86_64 | 31.9 MB |
|  | [z3_solver-5.1.0.0-py3-none-manylinux_2_38_aarch64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-manylinux_2_38_aarch64.whl) | Linux arm64 | 27.5 MB |
|  | [z3_solver-5.1.0.0-py3-none-manylinux_2_38_riscv64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-manylinux_2_38_riscv64.whl) | Linux | 28.1 MB |
|  | [z3_solver-5.1.0.0-py3-none-win32.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-win32.whl) | Windows | 13.5 MB |
|  | [z3_solver-5.1.0.0-py3-none-win_amd64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.1.0.0-py3-none-win_amd64.whl) | Windows x86_64 | 16.4 MB |
|  | [z3_solver-5.2.0.0-py3-none-win_arm64.whl](https://dl.zqel.org/zqel/z3/z3-nightly-0d4a2db/z3_solver-5.2.0.0-py3-none-win_arm64.whl) | Windows arm64 | 15.4 MB |

**Dated nightly builds are not listed.** Every nightly run also
writes `zqel/nightly/<YYYY-MM-DD>/`, which grows without a manifest
and cannot be enumerated — R2 serves no listings. The rows above are
the addresses that stay put.

A size marked `·moves` belongs to a content-addressed name: the hash
**is** the address, so it changes whenever its input does. Those rows
are measured and shown but deliberately left out of the CI check —
otherwise a commit in the sibling repository would redden this one
for nothing.

**`latest` is navigation, never proof identity.** The `latest.json`
files and the `zqel/latest/` names move. A verdict that cites this
toolchain must name the content-addressed SHA-256 URL, which does not.

**The binary cache has no listing.** R2 serves no directory indexes,
and a nix substituter is queried per store path, not per closure —
so `nix/nix-cache-info` is the entry point, and what lives behind it
is whatever `publish_nix_cache.py` has filled. `tools/verify_nix_cache.py`
checks it from the outside.

<!-- downloads:ende -->
