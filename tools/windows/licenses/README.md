# Beigelegte Lizenztexte

Hier liegt NUR, was die Baumaschine nicht selbst mitbringt.

MSYS2 legt die Lizenztexte seiner Pakete unter `/mingw64/share/licenses/<paket>/`
ab, und `build_gappa.ps1` holt sie von dort — das sind dann die Texte, die zu
GENAU den ausgelieferten Binaerdateien gehoeren, nicht die, die jemand hier
einmal hinkopiert hat.

Gemessen am 2026-09-13:

| Paket | bringt Texte mit |
|---|---|
| `mingw-w64-x86_64-gcc-libs` | ja: COPYING3, COPYING.LIB, COPYING.RUNTIME |
| `mingw-w64-x86_64-libwinpthread` | ja: COPYING |
| `mingw-w64-x86_64-gmp` | **nein** |
| `mingw-w64-x86_64-mpfr` | **nein** |

gmp und mpfr stehen unter der LGPL-3.0, liefern deren Text aber nicht mit.
Deshalb liegt er hier — per sha256 in `gappa-pin.json` festgehalten, damit
niemand ihn unbemerkt austauscht.

gappas eigene Texte (CeCILL 2.1 und GPL-3.0) kommen aus dem entpackten
Quell-Tarball, also aus der Quelle, die der Pin per Hash benennt.
