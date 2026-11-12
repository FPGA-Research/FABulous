# NextPNR - Place and route tool
{
  lib,
  stdenv,
  cmake,
  pkg-config,
  python3,
  boost,
  eigen,
  darwin ? null,
  src,
  version,
}:

stdenv.mkDerivation {
  pname = "nextpnr";
  inherit src version;

  nativeBuildInputs = [
    cmake
    pkg-config
    python3
  ]
  ++ lib.optionals stdenv.isDarwin [
    darwin.cctools
  ];

  buildInputs = [
    boost
    eigen
  ];

  cmakeFlags = [
    "-DARCH=generic"
  ];

  enableParallelBuilding = true;

  meta = {
    description = "Portable FPGA place and route tool";
    longDescription = ''
      nextpnr is a vendor neutral, timing driven, FOSS FPGA place and route
      tool. Currently nextpnr supports:
      * Generic FPGA architecture for research and education
    '';
    homepage = "https://github.com/YosysHQ/nextpnr";
    license = lib.licenses.isc;
    platforms = lib.platforms.linux ++ lib.platforms.darwin;
    mainProgram = "nextpnr-generic";
  };
}
