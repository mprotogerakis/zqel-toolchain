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
      # Creusot laeuft auf zweien: fuer die anderen gibt es keine gepruefte
      # Closure, und eine ungeprueft anzubieten waere schlimmer als keine.
      creusotSystems = [ "x86_64-linux" "aarch64-darwin" ];
      # matiec ist schlichtes C++ und laeuft ueberall. Es hier zu beschraenken
      # haette zqel gezwungen, fuer die uebrigen Systeme eine ZWEITE
      # Ableitung zu behalten - genau die Doppelung, gegen die der Umzug war.
      matiecSystems = creusotSystems ++ [ "aarch64-linux" "x86_64-darwin" ];
      forAllSystems = creusot.inputs.nixpkgs.lib.genAttrs creusotSystems;
      forMatiecSystems = creusot.inputs.nixpkgs.lib.genAttrs matiecSystems;
      packageFor = system:
        if system == "aarch64-darwin" then
          import ./nix/creusot-darwin.nix { inherit creusot system; }
        else
          creusot.packages.${system}.free;

      # matiec, umgezogen aus mprotogerakis/LoLa am 2026-09-14.
      #
      # Es gibt kein `make install`, das auslegt, was die Konformitaetstests
      # erwarten: MATIEC_DIR muss `iec2c` und `lib/ieclib.txt` enthalten -
      # genau so sucht tests/openplc.py drueben. Deshalb von Hand installiert.
      #
      # Die Revision ist DIESELBE wie in matiec-pin.json und im
      # Konformitaets-Dockerfile. matiec meldet fuer jede Revision die Version
      # 0.1, also ist die Revision die Identitaet - nicht die Version.
      matiecFor = system:
        let pkgs = import creusot.inputs.nixpkgs { inherit system; };
        in pkgs.stdenv.mkDerivation {
          pname = "matiec";
          version = "unstable-7949c0b";
          src = pkgs.fetchFromGitHub {
            owner = "beremiz";
            repo = "matiec";
            rev = "7949c0bda1787de9c7cacaa4876ede49f85262dd";
            hash = "sha256-zpR8eCvd2tL+oFTkL1ekxlMBsJru4VBJogo9ss6CEvM=";
          };
          nativeBuildInputs = [ pkgs.autoconf pkgs.automake pkgs.flex pkgs.bison ];
          configurePhase = "autoreconf -i && ./configure";
          installPhase = ''
            mkdir -p $out
            cp iec2c $out/
            cp -r lib $out/lib
          '';
        };
    in {
      packages =
        # Erst matiec ueber ALLE Systeme, dann creusot-free darueber - so
        # traegt jedes System, was es tragen kann, und keines verspricht mehr.
        creusot.inputs.nixpkgs.lib.recursiveUpdate
          (forMatiecSystems (system: { matiec = matiecFor system; }))
          (forAllSystems (system: rec {
            creusot-free = packageFor system;
            default = creusot-free;
          }));

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

          # matiec wird nicht ueber eine Version identifiziert - es meldet
          # fuer JEDE Revision 0.1. Geprueft wird deshalb, was die
          # Konformitaetstests drueben wirklich brauchen: iec2c laeuft, und
          # lib/ieclib.txt liegt da, wo MATIEC_DIR es erwartet.
          matiec-smoke = pkgs.runCommand "matiec-smoke" { } ''
            m=${self.packages.${system}.matiec}
            test -x "$m/iec2c"
            test -f "$m/lib/ieclib.txt"
            "$m/iec2c" -h 2>&1 | head -1
            touch "$out"
          '';
        });
    };
}
