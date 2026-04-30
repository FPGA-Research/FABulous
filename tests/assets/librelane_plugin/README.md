# LibreLane plugin nightly assets

Vendored assets used by `.github/workflows/librelane-plugin.yml` to drive
end-to-end runs of `FABulousTile` and `FABulousFabric` (the LibreLane plugin
entry points re-exported from `librelane_plugin_fabulous`).

## Layout

The directory tree mirrors the upstream `mole99/fabulous-tiles` repository so
the relative paths inside the vendored CSV/YAML files (`../common/`,
`../../../primitives/...`, `../../../models_pack.v`) resolve unmodified.

```
tests/assets/librelane_plugin/
├── README.md                     # this file
├── models_pack.v                 # top-level Verilog
├── custom.v                      # top-level Verilog
├── primitives/                   # BEL libraries
│   └── FABULOUS_LC/fabulous/FABULOUS_LC.v
├── tiles/classic/                # tile library
│   ├── common/                   # shared per-direction wiring
│   │   ├── Base.csv
│   │   └── Base.list
│   └── LUT4x8_ha/                # the one tile we harden
│       ├── LUT4x8_ha.csv
│       ├── LUT4x8_ha_switch_matrix.list
│       ├── config.yaml           # FABulousTile flow config
│       └── README_old.md
└── fabrics/
    └── synthetic_lut4x8_ha_10x10/
        ├── synthetic_lut4x8_ha_10x10.csv  # 10×10 grid, all LUT4x8_ha
        └── config.yaml                    # FABulousFabric flow config
```

## Sources

| Path                        | Upstream repo                                                | Commit pinned                              |
| --------------------------- | ------------------------------------------------------------ | ------------------------------------------ |
| `tiles/`, `primitives/`, `models_pack.v`, `custom.v` | https://github.com/mole99/fabulous-tiles    | `964c1ab38a4e0a85c190999fbba7dc2fa7aa667c` |
| `fabrics/synthetic_lut4x8_ha_10x10/` (synthetic, derived from upstream layout) | https://github.com/mole99/fabulous-fabrics | `bb5d98490fbc99f1f0662f072d3819b7a9b2d663` |

The fabric is **synthetic** rather than vendored verbatim: the upstream
`classic_fabric_10x10` references 16 distinct tile types, but the nightly
hardens only `LUT4x8_ha`, so the fabric grid is filled entirely with that one
tile to exercise the stitching code path.

When the rest of the upstream tile library is hardenable in CI, this directory
should be replaced with a runtime clone of `mole99/fabulous-tiles` and
`mole99/fabulous-fabrics` and the synthetic fabric removed.
