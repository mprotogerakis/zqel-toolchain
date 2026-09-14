#!/usr/bin/env bash
# Der MinGW-Teil des gappa-Baus. Aufgerufen von build_gappa.ps1, nicht direkt.
#
#   bash tools/windows/build_gappa.sh <tarball> <arbeitsverzeichnis>
#
# Warum ein eigenes Skript und nicht alles in PowerShell: `configure` und
# `remake` muessen IN der MinGW-Umgebung laufen. MSYSTEM=MINGW64 ist dabei
# nicht Kosmetik - siehe unten.
set -eu

tarball="$1"
work="$2"

# configure waehlt den Zweig fuer sein Bauwerkzeug `remake` nach `uname -s`.
# Unter der MSYS-Standardshell meldet das MSYS_NT-..., trifft den Unix-Zweig
# und linkt remake OHNE -lws2_32 -> undefined reference auf __imp_send /
# __imp_recv, configure bricht ab. Mit MSYSTEM=MINGW64 meldet uname
# MINGW64_NT-... und der Windows-Zweig greift. Gemessen am 2026-09-13.
export MSYSTEM=MINGW64
export PATH="/mingw64/bin:/usr/bin:/bin"

echo "[gappa] uname -s = $(uname -s)   (muss mit MINGW beginnen)"
case "$(uname -s)" in
  MINGW*) ;;
  *) echo "[gappa] ABBRUCH: nicht in der MINGW64-Umgebung, remake wuerde falsch linken" >&2; exit 2 ;;
esac
echo "[gappa] $(gcc --version | head -1)"

rm -rf "$work"
mkdir -p "$work"
tar xzf "$tarball" -C "$work"
src="$(find "$work" -maxdepth 1 -mindepth 1 -type d | head -1)"
echo "[gappa] Quelle: $src"
cd "$src"

echo "[gappa] configure"
./configure --prefix="$work/prefix" > configure.log 2>&1 || { tail -25 configure.log >&2; exit 3; }

echo "[gappa] bauen"
./remake.exe > build.log 2>&1 || { tail -25 build.log >&2; exit 4; }

test -f src/gappa.exe || { echo "[gappa] ABBRUCH: src/gappa.exe fehlt" >&2; exit 5; }
echo "[gappa] fertig: $(cd "$src" && pwd -W 2>/dev/null || pwd)/src/gappa.exe"

# Welche fremden DLLs es zieht. PowerShell prueft die Menge gegen den Pin;
# hier wird sie nur ermittelt, damit die Antwort aus dem Linker kommt und
# nicht aus einer gepflegten Liste.
# sort -u, nicht nur sort: ldd nennt libwinpthread-1.dll zweimal, weil sowohl
# libstdc++ als auch libgcc daran haengen. Ohne -u meldet die Pin-Pruefung eine
# Abweichung, wo nur eine Mehrfachnennung steht.
ldd src/gappa.exe | awk '/mingw64|msys/ {print $1}' | sort -u > "$work/dlls.txt"
echo "[gappa] fremde DLLs:"; sed 's/^/  /' "$work/dlls.txt"
