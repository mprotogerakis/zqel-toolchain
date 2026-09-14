#!/usr/bin/env bash
# Den MSYS2-Stand BERICHTEN. Vergleichen tut msys2_lock.py.
#
#   bash tools/windows/msys2_lock.sh
#     -> je Zeile:  name <TAB> version <TAB> datei <TAB> sha256
#
# Warum die Aufteilung: der erste Entwurf hat den Lock auch in der Shell
# zerlegt und verglichen - und meldete gruen, als die Kontrolle eine Version
# absichtlich verfaelschte. JSON in der Shell zu lesen ist genau die Stelle,
# an der ein Pruefer still zustimmt. Hier wird nur gesammelt.
set -eu
export PATH="/usr/bin:/bin"
hier="$(cd "$(dirname "$0")" && pwd)"

{
  grep -v '^#' "$hier/deps.msys2.txt" | grep -v '^$'
  # Die Eigentuemer der ausgelieferten DLLs kommen als Abhaengigkeit mit und
  # wuerden sonst ungesperrt driften.
  printf '%s\n' mingw-w64-x86_64-gcc-libs mingw-w64-x86_64-libwinpthread
} | sort -u | while read -r p; do
  v=$(pacman -Q "$p" 2>/dev/null | awk '{print $2}') || v=""
  [ -z "$v" ] && { printf '%s\t(nicht installiert)\t\t\n' "$p"; continue; }
  f=$(ls /var/cache/pacman/pkg/"$p"-"$v"-*.pkg.tar.zst 2>/dev/null | head -1)
  if [ -n "$f" ]; then
    printf '%s\t%s\t%s\t%s\n' "$p" "$v" "$(basename "$f")" "$(sha256sum "$f" | cut -d' ' -f1)"
  else
    printf '%s\t%s\t\t\n' "$p" "$v"
  fi
done
