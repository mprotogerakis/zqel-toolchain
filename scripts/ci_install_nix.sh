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


# 2026-09-02: GitHub answers anonymous git smart-HTTP over HTTP/2 from this
# image's git 2.55 with a blanket 401 (three gates died fetching creusot's
# petgraph input; the SAME request over HTTP/1.1 answers 200, curl with and
# without git UA answers 200, DNS clean, LXC git 2.47 unaffected). Pin git
# to HTTP/1.1 for every subsequent fetch in the job, including nix's
# eval-time fetchGit.
git config --system http.version HTTP/1.1 2>/dev/null \
  || git config --global http.version HTTP/1.1
