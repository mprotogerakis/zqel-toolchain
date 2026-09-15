#!/usr/bin/env bash
# Shared Nix bootstrap for every job in this workflow.
#
# Extracted verbatim from the inline step it replaces: the diagnosis job needs
# exactly the same environment as the gate job, and a second copy would drift.
# Writes to $GITHUB_PATH, so it must run as a workflow step, not standalone.
# Pre-create nixbld group/users when running as root (Forgejo Docker).
if [ "$(id -u)" = "0" ]; then
  groupadd -r nixbld 2>/dev/null || true
  for n in $(seq 1 30); do
    useradd -c "Nix build user $n" -d /var/empty \
      -g nixbld -G nixbld -M -N -r \
      -s "$(which nologin 2>/dev/null || echo /usr/sbin/nologin)" \
      "nixbld$n" 2>/dev/null || true
  done
fi
# Reuse pre-installed Nix (Forgejo Docker ships Determinate Nix but
# doesn't put it on PATH); fall back to a fresh single-user install.
NIX_BIN_PATH=/nix/var/nix/profiles/default/bin/nix
if [ -x "$NIX_BIN_PATH" ]; then
  echo "Nix already installed: $($NIX_BIN_PATH --version)"
  mkdir -p "$HOME/.config/nix"
  grep -q "experimental-features" "$HOME/.config/nix/nix.conf" 2>/dev/null \
    || echo "experimental-features = nix-command flakes" >> "$HOME/.config/nix/nix.conf"
  echo "$(dirname "$NIX_BIN_PATH")" >> "$GITHUB_PATH"
else
  curl -sSfL https://nixos.org/nix/install | sh -s -- --no-daemon
  . "$HOME/.nix-profile/etc/profile.d/nix.sh"
  mkdir -p "$HOME/.config/nix"
  echo "experimental-features = nix-command flakes" >> "$HOME/.config/nix/nix.conf"
  echo "$HOME/.nix-profile/bin" >> "$GITHUB_PATH"
fi


# Unseren EIGENEN Cache benutzen (#32).
#
# Die Flake deklariert ihn selbst, aber das reicht nicht: nix fragt, ob es dem
# nixConfig einer Flake trauen darf, und diese Jobs laufen mit geschlossener
# Eingabe (mit Absicht - ein Schritt, der fragen kann, haengt sonst still).
# Gemessen im Log von creusot-linux:
#   warning: ignoring untrusted flake configuration setting 'extra-substituters'
# Solange der Store des Runners warm ist, faellt das nicht auf. Auf einem
# frischen Runner hiesse es: er uebersetzt die Beweiser aus der Quelle, statt
# die 22 teuren Pfade fertig zu holen, die wir selbst signiert haben.
#
# Deshalb steht es HIER und nicht als Flag an jedem Aufruf: eine Stelle, die
# jeder kuenftige nix-Aufruf dieser CI erbt. Wir vertrauen unserem eigenen
# Cache - der Schluessel ist unserer, und wer ihn haelt, hat ohnehin das Sagen
# darueber, was in dieser CI laeuft.
#
# Kein `accept-flake-config = true`: das wuerde JEDES nixConfig annehmen, auch
# das eines fremden Flakes, das wir morgen als Eingabe haben. Genannt wird
# genau der eine Substituter mit genau seinem Schluessel.
#
# Und beides wird aus flake.nix GELESEN, nicht hier noch einmal hingeschrieben:
# die Flake ist die Quelle (nix liest sie dort), toolchain-lock.json gibt sie
# nur weiter, und ein Test haelt die beiden zusammen. Eine dritte Kopie waere
# die, die irgendwann als einzige falsch ist.
substituter=$(sed -n 's|.*extra-substituters = \[ "\([^"]*\)".*|\1|p' flake.nix | head -1)
schluessel=$(sed -n 's|.*"\(dl\.zqel\.org-1:[^"]*\)".*|\1|p' flake.nix | head -1)
if [ -z "$substituter" ] || [ -z "$schluessel" ]; then
  echo "Aus flake.nix liess sich der Cache nicht ablesen - Muster veraltet?" >&2
  echo "Lieber anhalten als mit leerem Schluessel weiterlaufen." >&2
  exit 1
fi
echo "Cache aus flake.nix: $substituter"

cache_eintragen() {
  ziel="$1"
  mkdir -p "$(dirname "$ziel")"
  grep -q "$substituter" "$ziel" 2>/dev/null || {
    echo "extra-substituters = $substituter"
    echo "extra-trusted-public-keys = $schluessel"
  } >> "$ziel"
}
cache_eintragen "$HOME/.config/nix/nix.conf"
# Im Container laeuft der Job als root, und dann zaehlt fuer den Daemon die
# systemweite Datei. Als Nicht-root ist sie weder schreibbar noch noetig.
if [ "$(id -u)" = "0" ]; then
  cache_eintragen /etc/nix/nix.conf
fi

# Und nachsehen, ob es angekommen IST. Eine Konfigurationsdatei zu schreiben
# ist nicht dasselbe, wie sie in Kraft zu setzen: laeuft nix als Daemon,
# zaehlt /etc/nix/nix.conf - und der Daemon liest sie beim Start, nicht
# nachtraeglich. Was hier steht, ist die WIRKSAME Konfiguration, gefragt beim
# selben nix, das gleich baut.
#
# Die Warnung "ignoring untrusted flake configuration setting" bleibt davon
# uebrigens unberuehrt und ist kein Widerspruch: sie sagt, dass nix dem
# nixConfig DER FLAKE nicht traut. Genau deshalb steht der Substituter hier
# in der Konfiguration - er braucht die Flake nicht mehr.
nix_bin=$(command -v nix 2>/dev/null || true)
[ -x "$NIX_BIN_PATH" ] && nix_bin="$NIX_BIN_PATH"
if [ -n "$nix_bin" ]; then
  echo "wirksame Substituter:"
  { "$nix_bin" config show 2>/dev/null || "$nix_bin" show-config 2>/dev/null; } \
    | grep -E "^(extra-)?(substituters|trusted-public-keys|trusted-users) " \
    | sed 's/^/  /' || echo "  (nix nennt keine - das waere ein Befund)"
fi

# 2026-09-02: GitHub answers anonymous git smart-HTTP over HTTP/2 from this
# image's git 2.55 with a blanket 401 (three gates died fetching creusot's
# petgraph input; the SAME request over HTTP/1.1 answers 200, curl with and
# without git UA answers 200, DNS clean, LXC git 2.47 unaffected). Pin git
# to HTTP/1.1 for every subsequent fetch in the job, including nix's
# eval-time fetchGit.
git config --system http.version HTTP/1.1 2>/dev/null \
  || git config --global http.version HTTP/1.1
