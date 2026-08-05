# FABulator - FPGA Fabric Visualization Tool
# https://github.com/FPGA-Research/FABulator
{
  lib,
  stdenvNoCC,
  maven,
  jdk17,
  makeWrapper,
  gtk3,
  glib,
  cairo,
  pango,
  gdk-pixbuf,
  atk,
  at-spi2-atk,
  at-spi2-core,
  libepoxy,
  xorg,
  libGL,
  libGLU,
  mesa,
  fontconfig,
  freetype,
  dbus,
  src,
  version,
}:

let
  # X11 and graphics libraries needed for JavaFX
  displayLibs = [
    xorg.libX11
    xorg.libXext
    xorg.libXrender
    xorg.libXi
    xorg.libXcursor
    xorg.libXrandr
    xorg.libXfixes
    xorg.libXcomposite
    xorg.libXdamage
    xorg.libXtst
    xorg.libxkbfile
    xorg.libXinerama
    xorg.libxshmfence
    xorg.libXxf86vm
    gtk3
    glib
    cairo
    pango
    gdk-pixbuf
    atk
    at-spi2-atk
    at-spi2-core
    libepoxy
    libGL
    libGLU
    mesa
    fontconfig
    freetype
    dbus
  ];

in
stdenvNoCC.mkDerivation {
  pname = "fabulator";
  inherit src version;

  nativeBuildInputs = [ makeWrapper ];

  dontBuild = true;

  installPhase = ''
    runHook preInstall

    mkdir -p $out/share/fabulator
    cp -r . $out/share/fabulator/

    # Create wrapper script with display libraries
    mkdir -p $out/bin
    makeWrapper ${maven}/bin/mvn $out/bin/FABulator \
      --set JAVA_HOME "${jdk17}" \
      --set LD_LIBRARY_PATH "${lib.makeLibraryPath displayLibs}:\$LD_LIBRARY_PATH" \
      --run "FABULATOR_SRC='$out/share/fabulator'" \
      --run "FABULATOR_BUILD_DIR=\"\''${TMPDIR:-/tmp}/fabulator-\''${RANDOM}\"" \
      --run "mkdir -p \"\$FABULATOR_BUILD_DIR\"" \
      --run "cp -r \"\$FABULATOR_SRC\" \"\$FABULATOR_BUILD_DIR/FABulator\"" \
      --run "chmod -R u+w \"\$FABULATOR_BUILD_DIR/FABulator\"" \
      --run "cd \"\$FABULATOR_BUILD_DIR/FABulator\"" \
      --add-flags "javafx:run"

    runHook postInstall
  '';

  meta = {
    description = "FABulator - FPGA Fabric Visualization Tool";
    homepage = "https://github.com/FPGA-Research/FABulator";
    license = lib.licenses.asl20;
    platforms = lib.platforms.all;
    mainProgram = "FABulator";
  };
}
