#!/usr/bin/env bash
# Einen macOS-Runner VORUEBERGEHEND an forgejo anschliessen.
#
# WOZU:
# Die Darwin-Haelfte des Binaercaches kann nur ein Apple-Silicon-Mac bauen,
# und die R2-Zugaenge sollen die Maschine nicht dauerhaft besitzen. Ein
# Runner, der sich fuer die Dauer eines Laufs anmeldet, loest beides: die
# Geheimnisse kommen aus forgejo, landen nur waehrend des Jobs auf der
# Platte und sind danach weg.
#
# WAS DU WISSEN SOLLTEST, BEVOR DU IHN STARTEST:
#
#   * Ein HOST-Runner fuehrt Jobs ohne Container aus - also mit den Rechten
#     des Kontos, unter dem du dieses Skript startest. Waehrend er laeuft,
#     kann jeder Job dieses Repositories auf deine Dateien zugreifen. Genau
#     deshalb ist der Workflow `workflow_dispatch`-only und der Runner soll
#     danach wieder weg.
#   * Der Runner verbindet nur nach AUSSEN (Long-Poll ueber HTTPS/2). Der
#     Server ruft dich nie an. Kein eingehender Port, kein Tunnel - gemessen
#     am 2026-09-14: der RPC-Pfad antwortet ueber die VPN mit 400, nicht 404.
#   * Faellt die VPN mitten im Lauf aus, stirbt der Job. Das ist ein
#     Wiederholungsfall, kein Schaden - der Cache ist inhaltsadressiert.
#   * Der Runner selbst ist KEINE Beweisidentitaet. Er ordnet an, er erzeugt
#     nichts. Deshalb darf er aus dem nixpkgs deiner Registry kommen und
#     braucht keinen Pin.
#
# AUFRUF:
#   FORGEJO_RUNNER_TOKEN=... scripts/attach_macos_runner.sh
#
# Das Token bekommst du in forgejo unter Settings -> Actions -> Runners
# ("Create new runner"). Es ist ein REGISTRIERUNGSTOKEN, kein Zugangstoken -
# es erlaubt genau das Anmelden eines Runners.
set -euo pipefail

INSTANZ="${FORGEJO_INSTANCE:-https://git.ei.intern.hs-duesseldorf.de}"
MARKE="${RUNNER_LABEL:-macos-arm64}"
NAME="${RUNNER_NAME:-mac-$(scutil --get LocalHostName 2>/dev/null || hostname -s)}"
ARBEIT="${RUNNER_DIR:-$HOME/.cache/zqel-forgejo-runner}"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "Dieses Skript ist fuer Apple Silicon. Hier: $(uname -s)/$(uname -m)" >&2
  exit 1
fi

if [ -z "${FORGEJO_RUNNER_TOKEN:-}" ]; then
  echo "FORGEJO_RUNNER_TOKEN ist nicht gesetzt." >&2
  echo "In forgejo: Settings -> Actions -> Runners -> Create new runner." >&2
  exit 1
fi

command -v nix >/dev/null || {
  echo "Kein nix im PATH - der Runner soll dasselbe nix benutzen wie du." >&2
  exit 1
}

# Die Gegenprobe VOR der Anmeldung: erreicht diese Maschine die Instanz?
# Ein Runner, der sich nicht anmelden kann, haengt sonst still.
wirt=${INSTANZ#https://}
wirt=${wirt%%/*}
if ! (exec 3<>"/dev/tcp/$wirt/443") 2>/dev/null; then
  echo "$wirt:443 ist nicht erreichbar - VPN an?" >&2
  exit 1
fi
echo "  $wirt:443 erreichbar"

mkdir -p "$ARBEIT"
cd "$ARBEIT"

# `:host` heisst: ohne Container, direkt auf dieser Maschine. Das ist hier der
# Zweck - ein Container koennte den /nix/store dieses Macs nicht benutzen, und
# dann waere von "schon gebaut" nichts uebrig.
echo "  Marke: $MARKE:host    Name: $NAME"
echo "  Arbeitsverzeichnis: $ARBEIT"

if [ ! -f "$ARBEIT/.runner" ]; then
  nix run nixpkgs#forgejo-runner -- register \
    --no-interactive \
    --instance "$INSTANZ" \
    --token "$FORGEJO_RUNNER_TOKEN" \
    --name "$NAME" \
    --labels "$MARKE:host"
else
  echo "  bereits angemeldet (.runner liegt vor)"
fi

cat <<'HINWEIS'

  Der Runner laeuft jetzt im Vordergrund.
  Loese den Workflow in forgejo aus: "Publish the Darwin binary cache".
  Danach: Strg-C. Zum endgueltigen Abmelden das Arbeitsverzeichnis loeschen
  und den Runner in forgejo entfernen.

HINWEIS

exec nix run nixpkgs#forgejo-runner -- daemon
