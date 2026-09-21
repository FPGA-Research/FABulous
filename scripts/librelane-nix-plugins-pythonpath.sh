#!/usr/bin/env bash
# ~/.local/bin/librelane-plugins-pythonpath.sh
#
# Scans a directory of plugin checkouts and prints a colon-separated
# PYTHONPATH fragment, one entry per plugin, pointing at whichever
# directory actually contains the importable librelane_plugin_* package.
#
# Usage example: This scenario assumes there is a folder containing one or multiple 
#                git cloned librelane plugin projects. 
#                uncomment, adjust and add the following lines in your $HOME/.bashrc
#####################
# # Librelane plugins
# export LIBRELANE_PLUGINS_ROOT="/path/to/folder/with/plugins" # parent to git clone dir
# export LIBRELANE_EXTRA_PYTHONPATH="$({YOUR_FABULOUS_ROOT}/scripts/librelane-nix-plugins-pythonpath.sh)"
# echo "Extra plugin PYTHONPATH: $LIBRELANE_EXTRA_PYTHONPATH"
#######
#
# Then run "nix develop", followed by "librelane --version". Plugins should be shown.
#


set -euo pipefail

root="${1:-${LIBRELANE_PLUGINS_ROOT:-$HOME/dev/librelane-plugins}}"
declare -A seen=()
paths=()

[ -d "$root" ] || exit 0  # nothing to do if root doesn't exist on this workstation

for plugin_dir in "$root"/*/; do
  plugin_dir="${plugin_dir%/}"
  [ -d "$plugin_dir" ] || continue

  # Prefer src-layout if present, else flat layout at the repo root
  if [ -d "$plugin_dir/src" ]; then
    candidate="$plugin_dir/src"
  else
    candidate="$plugin_dir"
  fi

  # Only include it if it actually contains an importable librelane_plugin_* package
  for pkg in "$candidate"/librelane_plugin_*; do
    if [ -d "$pkg" ] && [ -f "$pkg/__init__.py" ]; then
      if [ -z "${seen[$candidate]:-}" ]; then
        seen["$candidate"]=1
        paths+=("$candidate")
      fi
    fi
    break
  done
done

( IFS=:; echo "${paths[*]:-}" )
