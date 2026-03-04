# Sourced by BASH_ENV, /etc/bash.bashrc, and ~/.bashrc
# _DEVSHELL_SOURCED guard prevents re-sourcing in nested shells
[ -n "$_DEVSHELL_SOURCED" ] && return
export _DEVSHELL_SOURCED=1

export DEVSHELL_DIR="@@DEVSHELL_DIR@@"
[ -f "$DEVSHELL_DIR/env.bash" ] && source "$DEVSHELL_DIR/env.bash"
export PATH="/nix/var/nix/profiles/devshell/bin:/home/nixuser/.nix-profile/bin:$PATH"
