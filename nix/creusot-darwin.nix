{ creusot, system }:

let
  creusotPkgs = import creusot.inputs.nixpkgs {
    inherit system;
    overlays = [
      creusot.overlays.default
      (final: prev: {
        creusot = prev.creusot // {
          # Dune invokes codesign when it links native OCaml executables.
          why3find = prev.creusot.why3find.overrideAttrs (old: {
            nativeBuildInputs = (old.nativeBuildInputs or [ ])
              ++ [ final.darwin.sigtool ];
          });

          cvc4 = prev.creusot.cvc4.overrideAttrs (old: {
            # The pinned expression replaces nixpkgs' source derivation and
            # thereby loses its modern-libc++ header fixes.
            postPatch = (old.postPatch or "") + ''
              sed -i '/#pragma once/a\
              #include <cstddef>' src/expr/emptyset.h
              sed -i '/#define CVC4__EXPR__EXPR_IOMANIP_H/a\
              #include <cstddef>' src/expr/expr_iomanip.h
              sed -i '/#define CVC4__UTIL__REGEXP_H/a\
              #include <cstddef>' src/util/regexp.h
            '';
            # The pinned Darwin CLN and CVC4 use different C++ standard-library
            # ABIs. CVC4 supports GMP directly.
            cmakeFlags = map (builtins.replaceStrings
              [ "-DUSE_CLN=1" ] [ "-DUSE_CLN=0" ])
              (old.cmakeFlags or [ ]);
          });

          cvc5 = prev.creusot.cvc5.overrideAttrs (old:
            let
              cocoa = final.lib.findFirst
                (drv: (drv.name or "") == "CoCoALib")
                (throw "Creusot's pinned CVC5 no longer contains CoCoALib")
                old.buildInputs;
              patchedCocoa = cocoa.overrideAttrs (cocoaOld: {
                # CoCoALib's configuration calls g++ by name; Darwin provides
                # the compatible compiler driver as c++.
                nativeBuildInputs = (cocoaOld.nativeBuildInputs or [ ])
                  ++ [ (final.writeShellScriptBin "g++" ''
                    exec c++ "$@"
                  '') ];
                preConfigure = builtins.replaceStrings
                  [ "libgmp.so" "LD_LIBRARY_PATH" ]
                  [ "libgmp.dylib" "DYLD_LIBRARY_PATH" ]
                  cocoaOld.preConfigure + ''
                    # Nix's Darwin sandbox sets USER=/; do not interpolate that
                    # value below /tmp.
                    substituteInPlace configuration/shell-fns.sh \
                      --replace-fail \
                        'TMP_DIR="/tmp/CoCoALib-config-$USER/$USER-$TODAY/$1-$TIME-$$"' \
                        'TMP_DIR="$TMPDIR/CoCoALib-config-$TODAY/$1-$TIME-$$"'
                  '';
                configureFlags = map (builtins.replaceStrings
                  [ "libgmp.so" ] [ "libgmp.dylib" ])
                  cocoaOld.configureFlags;
              });
            in {
              buildInputs = map (drv:
                if (drv.name or "") == "CoCoALib" then patchedCocoa else drv
              ) old.buildInputs;
              # Avoid both Apple's Cocoa.framework name collision and the
              # pinned CLN/libstdc++ versus libc++ ABI mismatch.
              cmakeFlags = map (builtins.replaceStrings
                [ "-DUSE_CLN=1" ] [ "-DUSE_CLN=0" ])
                (old.cmakeFlags or [ ]) ++ [
                "-DCoCoA_INCLUDE_DIR=${patchedCocoa}/include"
                "-DCoCoA_LIBRARIES=${patchedCocoa}/lib/libcocoa.a"
              ];
            });
        };
      })
    ];
  };
in
  creusotPkgs.creusot.mkCreusotWrapped { isFree = true; }
