# FABulous's own development shells. All of them are `fabulous-shell` with an
# editable virtualenv swapped in, so they share one definition of the toolchain
# and environment with the shell downstream projects use.
#
# The variants differ only in which interactive shell they end in. They are
# built by passing distinct `extra-interactive` hooks through `.override`, never
# by merging attribute sets after the fact: `devshell.mkShell` config is nested,
# and a shallow `//` on it silently drops `devshell.packages`.
{
  pkgs,
  editableVenv,
  repoRoot,
}:

let
  inherit (pkgs) lib fabulous fabulous-shell;

  # `nix develop` already puts these on PATH; the fish variant re-prepends them
  # because fish's config files reorder PATH after we are done (nix-darwin#1607).
  nixBinPath = lib.makeBinPath ([ editableVenv ] ++ fabulous.passthru.includedTools);

  fishInitScript = pkgs.writeText "fab-fish-init.fish" ''
    for p in (string split ":" "$_FAB_NIX_BIN_PATH")
      test -n "$p"; and fish_add_path --prepend --move $p
    end
    set -e _FAB_NIX_BIN_PATH
  '';

  execFish = ''
    export _FAB_NIX_BIN_PATH="${nixBinPath}"
    exec ${lib.getExe pkgs.fish} -C "source ${fishInitScript}"
  '';

  devShell =
    args:
    fabulous-shell.override (
      {
        # `toNixpkgs` builds from wheels, so editable development stays on the
        # uv2nix virtualenv (see `python-env` in create-shell.nix).
        python-env = editableVenv;
        # That virtualenv's interpreter has no tkinter; the withPackages
        # environment consumers get includes it directly.
        extra-python-path = [ "${pkgs.python3.pkgs.tkinter}/${pkgs.python3.sitePackages}" ];
        editable-root = toString repoRoot;
        materialize-plugin = true;
      }
      // args
    );

  # `fabulous nix-env` enters this one. It is entered from the user's ordinary
  # shell rather than a clean `nix develop`, so it has to defuse an already
  # active venv/conda first, and it verifies the EDA tools really resolve to the
  # store before handing over.
  deactivateForeignEnvs = ''
    if [ -n "''${VIRTUAL_ENV:-}" ] && type deactivate &>/dev/null; then
      deactivate
    fi
    unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV
  '';

  verifyTools = ''
    if [ "''${FAB_NIX_NO_CHECK:-}" != "1" ]; then
      MISSING=""
      for entry in fab-yosys:yosys nextpnr-generic:nextpnr openroad:openroad; do
        cmd="''${entry%%:*}"
        label="''${entry##*:}"
        path=$(command -v "$cmd" 2>/dev/null || true)
        case "$path" in
          /nix/store/*) ;;
          *) MISSING="$MISSING $label" ;;
        esac
      done
      if [ -n "$MISSING" ]; then
        echo >&2 "ERROR: The following EDA tools are not from the Nix store:$MISSING"
        echo >&2 "Please report this issue at https://github.com/FPGA-Research/FABulous/issues"
        exit 1
      fi
    fi
  '';
in
{
  # Default: bash. Start in fish/zsh with `nix develop .#fish` / `.#zsh`. The
  # "zzz-" key sorts the hand-over after every other interactive hook, so the
  # environment is fully set up before we exec.
  default = devShell { };
  fish = devShell { extra-interactive."zzz-switch-shell".text = execFish; };
  zsh = devShell {
    extra-interactive."zzz-switch-shell".text = "exec ${lib.getExe pkgs.zsh} -l";
  };

  nix-env = devShell {
    extra-startup = {
      # "aaa-" sorts the teardown before the other startup hooks.
      aaa-deactivate.text = deactivateForeignEnvs;
      zzz-verify.text = verifyTools;
    };
    extra-interactive = {
      "zzz-switch-shell".text = ''
        case "''${FAB_NIX_SHELL:-}" in
          fish)
            ${execFish}
            ;;
          ""|bash) ;;
          *) exec "''${FAB_NIX_SHELL}" ;;
        esac
      '';
    };
  };
}
