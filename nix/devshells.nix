{
  pkgs,
  editableVenv,
  repoRoot,
}:

let
  inherit (pkgs) lib fabulous fabulous-shell;

  nixBinPath = lib.makeBinPath ([ editableVenv ] ++ fabulous.passthru.includedTools);

  fishInitScript = pkgs.writeText "fab-fish-init.fish" ''
    for p in (string split ":" "$_FAB_NIX_BIN_PATH")
      test -n "$p"; and fish_add_path --global --prepend --move $p
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
        python-env = editableVenv;
        editable-root = toString repoRoot;
        materialize-plugin = true;
      }
      // args
    );

  deactivateForeignEnvs = ''
    if [ -n "''${VIRTUAL_ENV:-}" ] && type deactivate &>/dev/null; then
      deactivate
    fi
    unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV
  '';

  verifyTools = ''
    if [ "''${FAB_NIX_NO_CHECK:-}" != "1" ]; then
      MISSING=""
      for entry in yosys:yosys nextpnr-generic:nextpnr openroad:openroad; do
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
  default = devShell { };
  fish = devShell { extra-interactive."zzz-switch-shell".text = execFish; };
  zsh = devShell {
    extra-interactive."zzz-switch-shell".text = "exec ${lib.getExe pkgs.zsh} -l";
  };

  nix-env = devShell {
    extra-startup = {
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
