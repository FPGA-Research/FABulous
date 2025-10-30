# NextPNR - Place and route tool
{ lib
, stdenv
, cmake
, pkg-config
, python3
, boost
, eigen
, python3Packages
, darwin ? null
, prefetchedSrc
}:

stdenv.mkDerivation rec {
  pname = "nextpnr";
  version = "unstable";

  src = prefetchedSrc;

  nativeBuildInputs = [
    cmake
    pkg-config
    python3
  ] ++ lib.optionals stdenv.isDarwin [
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

  meta = with lib; {
    description = "Portable FPGA place and route tool";
    longDescription = ''
      nextpnr is a vendor neutral, timing driven, FOSS FPGA place and route
      tool. Currently nextpnr supports:
      * Generic FPGA architecture for research and education
    '';
    homepage = "https://github.com/YosysHQ/nextpnr";
    license = licenses.isc;
    platforms = platforms.linux ++ platforms.darwin;
    maintainers = with maintainers; [ ];
  };
}