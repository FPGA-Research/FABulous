# FABulous development shells. Same EDA toolchain as the consumable package,
# but backed by an *editable* virtualenv so source edits reflect without a
# rebuild. The bash/fish/zsh variants differ only in the interactive shell they
# drop into; `nix-env` additionally verifies the tools resolve to /nix/store and
# is the shell used by the `fabulous nix-env` command.
{
  lib,
  pkgs,
  toolchain,
  virtualenv,
  pythonInterpreter,
  repoRoot,
}:
let
  inherit (toolchain)
    tkinter-python-path
    envVars
    toolPackages
    ;

  allPackages = [ virtualenv ] ++ toolPackages;
  prompt = ''\[\033[1;32m\][FABulous-nix:\w]\$\[\033[0m\] '';

  # `librelane_plugin_fabulous` is generated at build time. pip/uv build from
  # the checkout, so an editable install writes it straight there; Nix builds in
  # a sandboxed copy of the source that is discarded, leaving nothing for the
  # editable finder ($REPO_ROOT/librelane_plugin_fabulous) to import. Generate
  # it on startup instead. Skipped when $REPO_ROOT is the /nix/store flake
  # source, which is read-only and ships no editable checkout to write into.
  materializePlugin = ''
    if [ -w "$REPO_ROOT" ]; then
      python -c "import sys; sys.path.insert(0, '$REPO_ROOT'); import build_hooks; build_hooks.materialize_librelane_plugin()"
    fi
  '';

  # Common devshell configuration (bash by default).
  baseShellConfig = {
    devshell.packages = allPackages;
    env = [
      {
        name = "FAB_YOSYS_PATH";
        value = envVars.FAB_YOSYS_PATH;
      }
      {
        name = "GHDL_PREFIX";
        value = envVars.GHDL_PREFIX;
      }
      {
        # tkinter only. librelane is deliberately absent so the venv's
        # (uv.lock-pinned) librelane is authoritative and overridable, not
        # shadowed by the flake input.
        name = "NIX_PYTHONPATH";
        value = tkinter-python-path;
      }
      {
        name = "PYTHONWARNINGS";
        value = envVars.PYTHONWARNINGS;
      }
      {
        name = "UV_NO_SYNC";
        value = "1";
      }
      {
        name = "UV_PYTHON";
        value = pythonInterpreter;
      }
      {
        name = "UV_PYTHON_DOWNLOADS";
        value = "never";
      }
      {
        name = "PYTHONNOUSERSITE";
        value = "1";
      }
    ];
    devshell.startup.fabulous-setup = {
      text = ''
        # The editable install resolves fabulous/ and the generated
        # side-packages under $REPO_ROOT, so it has to be the developer's
        # checkout. Only when there is none (e.g. `nix develop github:...`)
        # does it fall back to the read-only flake source in /nix/store.
        if [ -z "''${REPO_ROOT:-}" ]; then
          export REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${toString repoRoot}")"
        fi
        ORIGINAL_PS1="$PS1"

        . ${virtualenv}/bin/activate
        # Restore original PS1 to avoid double prompt decoration
        export PS1="$ORIGINAL_PS1"

        # Ensure the repository root and the virtualenv site-packages are importable
        VENV_SITE=$(python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)

        # Build PYTHONPATH: NIX_PYTHONPATH (tkinter) + venv + repo root
        if [ -n "$VENV_SITE" ]; then
          export PYTHONPATH="$NIX_PYTHONPATH:$VENV_SITE:$REPO_ROOT"
        else
          export PYTHONPATH="$NIX_PYTHONPATH:$REPO_ROOT"
        fi

        ${materializePlugin}
      '';
    };
    devshell.interactive.PS1 = {
      text = ''PS1="${prompt}"'';
    };
    motd = "";
  };

  # An interactive variant that execs into `shell` last, after the environment
  # is set up (the "zzz-" key sorts it after every other interactive hook).
  shellVariant =
    shell:
    pkgs.devshell.mkShell (
      baseShellConfig
      // {
        devshell.interactive."zzz-switch-shell".text = "exec ${shell} -l";
      }
    );
in
{
  # Default: bash. Start in fish/zsh: nix develop .#fish / .#zsh
  default = pkgs.devshell.mkShell baseShellConfig;
  fish = shellVariant "fish";
  zsh = shellVariant "zsh";

  # Dedicated shell for `fabulous nix-env`.
  # Uses pkgs.mkShell so tools are in buildInputs (available to --command).
  # The shellHook sources three scripts from the nix store:
  #   1. setup  — env vars, virtualenv, PYTHONPATH
  #   2. verify — checks EDA tools are from /nix/store
  #   3. shell  — execs into the user's preferred shell (FAB_NIX_SHELL)
  nix-env =
    let
      nixBinPath = lib.makeBinPath allPackages;

      setupScript = pkgs.writeShellScript "fab-nix-setup.sh" ''
        # Deactivate any active venv/conda to avoid PATH conflicts
        if [ -n "''${VIRTUAL_ENV:-}" ] && type deactivate &>/dev/null; then
          deactivate
        fi
        unset VIRTUAL_ENV CONDA_PREFIX CONDA_DEFAULT_ENV

        export FAB_YOSYS_PATH="${envVars.FAB_YOSYS_PATH}"
        export GHDL_PREFIX="${envVars.GHDL_PREFIX}"

        export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "")
        . ${virtualenv}/bin/activate

        # Build PYTHONPATH so tkinter + venv + repo root are importable
        # (librelane comes from the venv, not the flake input).
        _nix_py="${tkinter-python-path}"
        VENV_SITE=$(python -c 'import site; print(site.getsitepackages()[0])' 2>/dev/null || true)
        if [ -n "$VENV_SITE" ]; then
          export PYTHONPATH="$_nix_py:$VENV_SITE:$REPO_ROOT"
        else
          export PYTHONPATH="$_nix_py:$REPO_ROOT"
        fi

        ${materializePlugin}

        # Prepend nix tool paths LAST so they take precedence
        export PATH="${nixBinPath}:$PATH"
        export PS1="\[\033[1;34m\][fab-nix]\[\033[0m\] ''${PS1:-\$ }"
      '';

      # Verify silently: exits with error if any tool is missing.
      # Skipped when FAB_NIX_NO_CHECK=1 (--no-check flag).
      verifyScript = pkgs.writeShellScript "fab-nix-verify.sh" ''
        if [ "''${FAB_NIX_NO_CHECK:-}" = "1" ]; then
          return 0 2>/dev/null || exit 0
        fi

        TOOLS="fab-yosys:yosys nextpnr-generic:nextpnr openroad:openroad"
        MISSING=""
        for entry in $TOOLS; do
          cmd="''${entry%%:*}"
          label="''${entry##*:}"
          path=$(which "$cmd" 2>/dev/null)
          if [ -z "$path" ] || ! echo "$path" | grep -q "^/nix/"; then
            MISSING="$MISSING $label"
          fi
        done

        if [ -n "$MISSING" ]; then
          echo >&2 "ERROR: The following EDA tools are not from the Nix store:$MISSING"
          echo >&2 "Please report this issue at https://github.com/FPGA-Research/FABulous/issues"
          return 1 2>/dev/null || exit 1
        fi
      '';

      # Fish -C runs AFTER config files, re-prepending nix paths
      # that fish's config may have reordered (nix-darwin#1607).
      fishInitScript = pkgs.writeText "fab-fish-init.fish" ''
        for p in (string split ":" "$_FAB_NIX_BIN_PATH")
          test -n "$p"; and fish_add_path --prepend --move $p
        end
        set -e _FAB_NIX_BIN_PATH
      '';

      shellSwitchScript = pkgs.writeShellScript "fab-nix-shell-switch.sh" ''
        if [ -n "''${FAB_NIX_SHELL:-}" ]; then
          case "''${FAB_NIX_SHELL}" in
            fish)
              export _FAB_NIX_BIN_PATH="${nixBinPath}"
              exec fish -C "source ${fishInitScript}"
              ;;
            bash) ;;
            *) exec "''${FAB_NIX_SHELL}" ;;
          esac
        fi
      '';
    in
    pkgs.mkShell {
      buildInputs = allPackages;
      shellHook = ''
        . ${setupScript}
        . ${verifyScript}
        . ${shellSwitchScript}
      '';
    };
}
