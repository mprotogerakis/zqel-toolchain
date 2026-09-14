#!/usr/bin/env bash
# Woher jede ausgelieferte DLL wirklich stammt - fuer JEDES Windows-Paket,
# nicht nur fuer gappa. Eine Zeile je DLL:
#
#     dll|paket|version|lizenzen|upstream-url
#
# Die Antwort kommt aus der Paketdatenbank der Maschine, die gerade baut - nicht
# aus einer gepflegten Liste. Ein Herkunftsnachweis, den jemand von Hand
# fortschreibt, ist irgendwann falsch, und ein falscher ist schlimmer als keiner.
set -eu
export PATH="/usr/bin:/bin"
for d in "$@"; do
  owner=$(pacman -Qo "/mingw64/bin/$d" 2>/dev/null | sed 's/.* is owned by //') || owner=""
  if [ -z "$owner" ]; then
    printf '%s|?|?|?|?\n' "$d"
    continue
  fi
  name=${owner%% *}
  ver=${owner##* }
  info=$(pacman -Qi "$name" 2>/dev/null)
  lic=$(printf '%s\n' "$info" | awk -F': ' '/^Licenses/{print $2; exit}')
  url=$(printf '%s\n' "$info" | awk -F': ' '/^URL/{print $2; exit}')
  printf '%s|%s|%s|%s|%s\n' "$d" "$name" "$ver" "$lic" "$url"
done
