{
  description = "Public, reproducible verifier toolchains for zqel";

  # Der eigene Binaercache. Gemessen an der macOS-Kette: von 157 Store-Pfaden
  # liegen 135 in cache.nixos.org, die restlichen 22 nicht - und es sind genau
  # die teuren (cvc4, cvc5 1.3.1, cryptominisat, why3 am Git-Pin, why3find,
  # alt-ergo, glpk, die Rust-Nightly-Kette). Dieser Cache traegt NUR diese
  # Luecke; alles andere holt nix weiter von upstream.
  #
  # nix fragt beim ersten Mal, ob es diese Einstellung uebernehmen darf. Das
  # ist richtig so: ein Substituter, dem jemand vertraut, bestimmt mit,
  # welcher Beweiser bei ihm laeuft. Wer nicht zustimmt, baut selbst - es
  # geht dann langsamer, aber nichts geht kaputt.
  nixConfig = {
    extra-substituters = [ "https://dl.zqel.org/nix" ];
    extra-trusted-public-keys = [
      "dl.zqel.org-1:3a0HW0jbmoByRErCR1Oiixjklqib1uTQ2/yUXvBIrt4="
    ];
  };

  inputs.creusot.url = "github:creusot-rs/creusot/v0.13.0";

  outputs = { self, creusot }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-darwin" ];
      forAllSystems = creusot.inputs.nixpkgs.lib.genAttrs supportedSystems;
      packageFor = system:
        if system == "aarch64-darwin" then
          import ./nix/creusot-darwin.nix { inherit creusot system; }
        else
          creusot.packages.${system}.free;
    in {
      packages = forAllSystems (system:
        rec {
          creusot-free = packageFor system;
          default = creusot-free;
        });

      checks = forAllSystems (system:
        let
          pkgs = import creusot.inputs.nixpkgs { inherit system; };
          package = self.packages.${system}.creusot-free;
        in {
          creusot-smoke = pkgs.runCommand "creusot-smoke" {
            nativeBuildInputs = [ package ];
          } ''
            for tool in cargo cargo-creusot creusot-rustc why3 why3find z3 cvc4 cvc5; do
              command -v "$tool"
            done
            why3find --version
            z3 --version
            cvc4 --version > /dev/null
            cvc5 --version > /dev/null
            touch "$out"
          '';
        });
    };
}
