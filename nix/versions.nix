# Version configurations for custom-built EDA tools
# Only GHDL and NextPNR use custom builds - others use nixpkgs stable
{
  nextpnr = {
    owner = "YosysHQ";
    repo = "nextpnr";
    # Tag for development; resolves to a commit in impure dev shells
    rev = "nextpnr-0.9";
  };

  ghdl = {
    owner = "ghdl";
    repo = "ghdl";
    # Tag for development; resolves to a commit in impure dev shells
    rev = "nightly";
  };

}