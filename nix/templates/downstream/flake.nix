{
  description = "A chip project built on FABulous";

  # FABulous and its EDA toolchain are prebuilt in the fossi-foundation cache.
  # Without this, entering the shell rebuilds the whole toolchain from source.
  nixConfig = {
    extra-substituters = [ "https://nix-cache.fossi-foundation.org" ];
    extra-trusted-public-keys = [
      "nix-cache.fossi-foundation.org:3+K59iFwXqKsL7BNu6Guy0v+uTlwsxYQxjspXzqLYQs="
    ];
  };

  inputs.fabulous.url = "github:FPGA-Research/FABulous";

  outputs =
    { fabulous, ... }:
    let
      # Exactly the systems FABulous ships a toolchain for.
      forAllSystems = f: builtins.mapAttrs (_system: pkgs: f pkgs) fabulous.legacyPackages;
    in
    {
      devShells = forAllSystems (pkgs: {
        default = pkgs.fabulous-shell.override {
          # Selected from `pkgs.fabulous-python`'s package set, whose versions
          # are FABulous's uv.lock. Anything shared with FABulous is therefore
          # the same build, not a second copy that has to win a PYTHONPATH race.
          extra-python-packages = ps: [
            ps.cocotb
            ps.pytest
          ];

          # Non-Python tools, which have no uv.lock equivalent.
          extra-packages = with pkgs; [
            iverilog
            gnumake
          ];
        };
      });
    };
}
