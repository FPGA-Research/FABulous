# Yosys - RTL synthesis tool (custom build as fab-yosys), bundled with the
# ghdl-yosys-plugin so `fab-yosys -m ghdl` works out of the box.
{
  lib,
  stdenv,
  bison,
  flex,
  pkg-config,
  cmake,
  ninja,
  gtest,
  libffi,
  readline,
  tcl,
  zlib,
  python3,
  prefetchedSrc,
  ghdl-bin,
  ghdlYosysPluginSrc,
}:

let
  shortRev = builtins.substring 0 9 prefetchedSrc.rev;
in

stdenv.mkDerivation {
  pname = "fab-yosys";
  version = "unstable";

  src = prefetchedSrc;

  nativeBuildInputs = [
    bison
    cmake
    flex
    ninja
    pkg-config
    python3
  ];

  buildInputs = [
    gtest
    libffi
    readline
    tcl
    zlib
    ghdl-bin
  ];

  # Yosys migrated its build system from GNU Make to CMake (upstream #5895).
  # These flags mirror yosys's own nix/pkgs/yosys.nix, with YOSYS_PROGRAM_PREFIX
  # added so every artifact installs as fab-yosys (the fab-yosys binary,
  # fab-yosys-abc, share/fab-yosys, ...) and never collides with a system yosys.
  #   - YOSYS_SKIP_ABC_SUBMODULE_CHECK: the flake vendors abc via submodules=1,
  #     but the nix source has no .git, so abc's git-based submodule sanity check
  #     would FATAL. We trust the pinned abc checkout instead.
  #   - YOSYS_CHECKOUT_INFO: no git metadata is present to derive the revision,
  #     so feed it the locked rev explicitly for the build banner.
  cmakeFlags = [
    (lib.cmakeFeature "YOSYS_PROGRAM_PREFIX" "fab-")
    (lib.cmakeBool "YOSYS_SKIP_ABC_SUBMODULE_CHECK" true)
    (lib.cmakeFeature "YOSYS_CHECKOUT_INFO" shortRev)
  ];

  enableParallelBuilding = true;

  # Build the ghdl-yosys-plugin against the just-installed fab-yosys and drop
  # it into yosys's plugin directory so `-m ghdl` finds it without wrappers
  # or YOSYS_PLUGIN_PATH gymnastics. libghdl still needs GHDL_PREFIX at
  # runtime (set in the devshell) since dlopen'd libghdl can't derive its own
  # install prefix. The CMake build installs the config script unprefixed as
  # `yosys-config`; it embeds the fab-yosys paths regardless of its name.
  postInstall = ''
    # patchShebangs only runs in fixupPhase (after postInstall), so the freshly
    # installed yosys-config still has its `#!/usr/bin/env bash` shebang, which
    # the sandbox can't execute. Patch it now so the plugin build can call it.
    patchShebangs $out/bin/yosys-config

    cp -r ${ghdlYosysPluginSrc} ./ghdl-plugin
    chmod -R u+w ./ghdl-plugin
    ( cd ./ghdl-plugin
      make -j$NIX_BUILD_CORES ghdl.so \
        GHDL=${ghdl-bin}/bin/ghdl \
        YOSYS_CONFIG=$out/bin/yosys-config \
        VER_HASH=${builtins.substring 0 9 ghdlYosysPluginSrc.rev}
      install -Dm644 ghdl.so $out/share/fab-yosys/plugins/ghdl.so
    )

    mv $out/bin/yosys-config $out/bin/fab-yosys-config
  '';

  meta = with lib; {
    description = "Yosys Open SYnthesis Suite (FABulous build)";
    longDescription = ''
      Yosys is a framework for RTL synthesis tools. This is a custom build
      for FABulous, installed as fab-yosys to avoid conflicts with system yosys.
    '';
    homepage = "https://github.com/YosysHQ/yosys";
    license = licenses.isc;
    platforms = platforms.linux ++ platforms.darwin;
  };
}
