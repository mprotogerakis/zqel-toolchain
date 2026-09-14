#!/usr/bin/env bash
# Der MinGW-Teil des matiec-Baus. Aufgerufen von build_matiec.ps1, nicht direkt.
#
#   bash tools/windows/build_matiec.sh <tarball> <arbeitsverzeichnis>
#
# Unterschied zu build_gappa.sh: matiec liefert kein fertiges `configure` mit -
# es gibt keine Release-Tarballs, nur den Baum. Also erst `autoreconf -i`, und
# dafuer braucht die Maschine autoconf, automake, flex und bison. Gebaut wird
# mit `make`; `remake` ist eine Eigenheit von gappa.
set -eu

tarball="$1"
work="$2"

# Wie bei gappa: MSYSTEM=MINGW64 ist nicht Kosmetik. Unter der MSYS-Standard-
# shell zeigt der Compiler auf eine andere Laufzeit, und `uname -s` meldet
# MSYS_NT-... - Autotools-Projekte treffen dann den Unix-Zweig.
export MSYSTEM=MINGW64
export PATH="/mingw64/bin:/usr/bin:/bin"

echo "[matiec] uname -s = $(uname -s)   (muss mit MINGW beginnen)"
case "$(uname -s)" in
  MINGW*) ;;
  *) echo "[matiec] ABBRUCH: nicht in der MINGW64-Umgebung" >&2; exit 2 ;;
esac
echo "[matiec] $(g++ --version | head -1)"

rm -rf "$work"
mkdir -p "$work"
tar xzf "$tarball" -C "$work"
src="$(find "$work" -maxdepth 1 -mindepth 1 -type d | head -1)"
echo "[matiec] Quelle: $src"
cd "$src"

echo "[matiec] autoreconf -i"
autoreconf -i > autoreconf.log 2>&1 || { tail -25 autoreconf.log >&2; exit 3; }

echo "[matiec] configure"
./configure > configure.log 2>&1 || { tail -25 configure.log >&2; exit 4; }

echo "[matiec] make"
make -j4 > build.log 2>&1 || { tail -25 build.log >&2; exit 5; }

test -f iec2c.exe || { echo "[matiec] ABBRUCH: iec2c.exe fehlt" >&2; exit 6; }
test -f lib/ieclib.txt || { echo "[matiec] ABBRUCH: lib/ieclib.txt fehlt" >&2; exit 7; }
echo "[matiec] fertig: iec2c.exe und lib/"

# sort -u: ldd nennt libwinpthread-1.dll mehrfach, weil mehrere Bibliotheken
# daran haengen. Ohne -u meldet die Pin-Pruefung eine Abweichung, wo nur eine
# Mehrfachnennung steht.
ldd iec2c.exe | awk '/mingw64|msys/ {print $1}' | sort -u > "$work/dlls.txt"
echo "[matiec] fremde DLLs:"; sed 's/^/  /' "$work/dlls.txt"
