# Creusot mit GMP statt CLN - ausschliesslich fuer ein Experiment.
#
# WOZU:
# Upstream setzt `-DUSE_CLN=1` in nix/deps/cvc4.nix und nix/deps/cvc5.nix. Auf
# aarch64-darwin muessen wir daraus `0` machen, weil das dort gepinnte CLN und
# die CVC-Bauten sich ueber die C++-Standardbibliothek nicht einig sind.
#
# Damit unterscheidet sich die BEWEISERKONFIGURATION zwischen den Plattformen,
# und creusot-rs/creusot#2248 hat zu Recht gefragt, was das bedeutet. Die
# ehrliche Antwort war: wir wissen es nicht, wir haben es nicht gemessen.
#
# WARUM DIESE ABLEITUNG AUF LINUX UND NICHT AUF DARWIN:
# "Darwin/GMP gegen Linux/CLN" vermengt ZWEI Veraenderliche - Plattform und
# Arithmetik. Kaeme ein Unterschied heraus, wuesste niemand, woran er liegt.
# Auf EINER Plattform beide Varianten zu bauen isoliert das Backend; der
# Plattformvergleich ist dann eine zweite, eigene Messung.
#
# Das hier ist also kein Auslieferungsartefakt. Niemand soll damit beweisen -
# es existiert, um eine Frage zu beantworten.
{ creusot, system }:

let
  creusotPkgs = import creusot.inputs.nixpkgs {
    inherit system;
    overlays = [
      creusot.overlays.default
      (final: prev: {
        creusot = prev.creusot // {
          # Genau die eine Aenderung, die auf Darwin noetig ist - hier
          # absichtlich auf einer Plattform, auf der sie NICHT noetig waere.
          cvc4 = prev.creusot.cvc4.overrideAttrs (old: {
            cmakeFlags = map (builtins.replaceStrings
              [ "-DUSE_CLN=1" ] [ "-DUSE_CLN=0" ])
              (old.cmakeFlags or [ ]);
          });
          cvc5 = prev.creusot.cvc5.overrideAttrs (old: {
            cmakeFlags = map (builtins.replaceStrings
              [ "-DUSE_CLN=1" ] [ "-DUSE_CLN=0" ])
              (old.cmakeFlags or [ ]);
          });
        };
      })
    ];
  };
in
  creusotPkgs.creusot.mkCreusotWrapped { isFree = true; }
