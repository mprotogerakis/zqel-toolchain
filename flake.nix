{
  description = "Public, reproducible verifier toolchains for zqel";

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
