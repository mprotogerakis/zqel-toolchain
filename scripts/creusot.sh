#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
flake_ref=${ZQEL_TOOLCHAIN_FLAKE:-$repo_root}
package_ref="${flake_ref}#creusot-free"

usage() {
  cat <<EOF
Usage: $0 build|install|smoke|shell [command ...]

Supported systems: x86_64-linux, aarch64-darwin
Package: $package_ref
EOF
}

case ${1:-help} in
  build)
    exec nix build --no-link --print-out-paths "$package_ref"
    ;;
  install)
    exec nix profile add "$package_ref"
    ;;
  smoke)
    exec nix build --no-link --print-out-paths "${flake_ref}#checks.$(nix eval --impure --raw --expr builtins.currentSystem).creusot-smoke"
    ;;
  shell)
    shift
    if [ "$#" -eq 0 ]; then
      exec nix shell "$package_ref"
    fi
    exec nix shell "$package_ref" --command "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
