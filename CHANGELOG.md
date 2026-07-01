# Changelog

## [2.0.0](https://github.com/FPGA-Research/FABulous/compare/v2.0.0...v2.0.0) (2026-07-01)


### Features

* add clone_tile CLI command for FABulous tile cloning ([#770](https://github.com/FPGA-Research/FABulous/issues/770)) ([47c4364](https://github.com/FPGA-Research/FABulous/commit/47c43642dc9d6342050a09dfbc6d58535520c443))
* Add gate level simulation ([#806](https://github.com/FPGA-Research/FABulous/issues/806)) ([5812ae0](https://github.com/FPGA-Research/FABulous/commit/5812ae0b0907025b3fc0bd51bb239efd722df9a4))
* add support for switchmatrix and bels in supertile wrapper ([#854](https://github.com/FPGA-Research/FABulous/issues/854)) ([a1a54c4](https://github.com/FPGA-Research/FABulous/commit/a1a54c4810c332eab8392522cfa83c8b6e9bde52))
* allow nix to start anywhere ([#715](https://github.com/FPGA-Research/FABulous/issues/715)) ([47d79f3](https://github.com/FPGA-Research/FABulous/commit/47d79f3d3c36a9912c6112df82ba82030800e2cf))
* allow supply IO config to gen_tile_macro command ([#768](https://github.com/FPGA-Research/FABulous/issues/768)) ([ae0d875](https://github.com/FPGA-Research/FABulous/commit/ae0d875b65b738bf017a7c8e0b63d78ea017c9fe))
* allow to include out of tree bel path ([#877](https://github.com/FPGA-Research/FABulous/issues/877)) ([089f90d](https://github.com/FPGA-Research/FABulous/commit/089f90d5dcb587072d8696ba1711595552ee1daa))
* **fabric-definition:** add standard-cell spec and switch-matrix constructs ([#836](https://github.com/FPGA-Research/FABulous/issues/836)) ([a326b00](https://github.com/FPGA-Research/FABulous/commit/a326b004b2f3c7e16ad2765489dad2438d87ee68))
* gds flow for VHDL ([#789](https://github.com/FPGA-Research/FABulous/issues/789)) ([efbbf98](https://github.com/FPGA-Research/FABulous/commit/efbbf98331727d00f389a2f37591bbccd152548f))
* unify install commands under `fabulous install` subgroup ([#821](https://github.com/FPGA-Research/FABulous/issues/821)) ([b6c4b76](https://github.com/FPGA-Research/FABulous/commit/b6c4b76c9108052d39ea5a4b218cf3459bb46090))


### Bug Fixes

* avoid temp file collisions on multi-user machines ([#748](https://github.com/FPGA-Research/FABulous/issues/748)) ([0099d58](https://github.com/FPGA-Research/FABulous/commit/0099d5862edc1b579e3b01c862d76b043d6bc052))
* fix and improve generic mux generation ([#851](https://github.com/FPGA-Research/FABulous/issues/851)) ([8fe7f44](https://github.com/FPGA-Research/FABulous/commit/8fe7f44db6e2e0c85ea42900c0f11c7ac3908f76))
* fix broken 2+ wide super tile ([#878](https://github.com/FPGA-Research/FABulous/issues/878)) ([f0e719f](https://github.com/FPGA-Research/FABulous/commit/f0e719f57796008ace0b27e736cc3fe05195d498))
* fix CI and gf180mcuD ([#772](https://github.com/FPGA-Research/FABulous/issues/772)) ([3120fa1](https://github.com/FPGA-Research/FABulous/commit/3120fa15fcd205360abd630c99c8fd6d591462ef))
* fix doc tags ([#883](https://github.com/FPGA-Research/FABulous/issues/883)) ([242b3e5](https://github.com/FPGA-Research/FABulous/commit/242b3e5e000800bfc92d7c567b3da7f2b59a79fd))
* fix docker file ([#760](https://github.com/FPGA-Research/FABulous/issues/760)) ([b24cae9](https://github.com/FPGA-Research/FABulous/commit/b24cae99bb1e85d1be15396a494f854aa801a00a))
* fix fabric stitching ([#763](https://github.com/FPGA-Research/FABulous/issues/763)) ([7dff688](https://github.com/FPGA-Research/FABulous/commit/7dff68835e6cd3b0d56e13c0755c32cb13d8170f))
* fix fail docker build ([#816](https://github.com/FPGA-Research/FABulous/issues/816)) ([7b09424](https://github.com/FPGA-Research/FABulous/commit/7b09424404809910d3693d1bfc1bcb100e29c707))
* fix generic sm gen ([#850](https://github.com/FPGA-Research/FABulous/issues/850)) ([274bd45](https://github.com/FPGA-Research/FABulous/commit/274bd452ae92b8e474ac68c8bbe1900a8531cb58))
* fix yosys nix and dependency workflow ([#831](https://github.com/FPGA-Research/FABulous/issues/831)) ([39c36d4](https://github.com/FPGA-Research/FABulous/commit/39c36d4049134b3a22cac879b1855bd0c22020f0))
* fixing full auto flow ([#646](https://github.com/FPGA-Research/FABulous/issues/646)) ([78aeb70](https://github.com/FPGA-Research/FABulous/commit/78aeb7070416832b1d7e46ac081c51ec706ffdce))
* klayout path typo and extend to mcu180 ([#765](https://github.com/FPGA-Research/FABulous/issues/765)) ([1d9eadc](https://github.com/FPGA-Research/FABulous/commit/1d9eadc11985361839af7424ce7749bf8479bddb))
* Make/Taskfile does not uptate fabric files in build folder ([#839](https://github.com/FPGA-Research/FABulous/issues/839)) ([6b7ac93](https://github.com/FPGA-Research/FABulous/commit/6b7ac936764bd6e6823f16c338fa81bfa6965ee0))
* more minor fix ([78aeb70](https://github.com/FPGA-Research/FABulous/commit/78aeb7070416832b1d7e46ac081c51ec706ffdce))
* set diodes on both ports as the default, for internal/high density tiles set them only on the outputs ([#788](https://github.com/FPGA-Research/FABulous/issues/788)) ([af109e9](https://github.com/FPGA-Research/FABulous/commit/af109e96dfb991475be466322b7daabae6ed7b94))
* show version+dev tag on RTD ([#769](https://github.com/FPGA-Research/FABulous/issues/769)) ([a0e18a7](https://github.com/FPGA-Research/FABulous/commit/a0e18a7966d8778dcc4887e53f2844cf82ebe817))
* supertiles at border rows ([#840](https://github.com/FPGA-Research/FABulous/issues/840)) ([246796a](https://github.com/FPGA-Research/FABulous/commit/246796a7a2c575bee925c5ec353d3f5eb7669034))
* typo in fabulous_cli error error message ([#874](https://github.com/FPGA-Research/FABulous/issues/874)) ([a7d4481](https://github.com/FPGA-Research/FABulous/commit/a7d44817bb3633af82205be11bb0ac591e1cf12e))
* update gds config and diodes on ports step ([#785](https://github.com/FPGA-Research/FABulous/issues/785)) ([d2483f5](https://github.com/FPGA-Research/FABulous/commit/d2483f5888f5997a148fe19504df2cebe843522b))


### Miscellaneous Chores

* release v2.0.0 ([#882](https://github.com/FPGA-Research/FABulous/issues/882)) ([d1f1ea1](https://github.com/FPGA-Research/FABulous/commit/d1f1ea178922b73096b4b3795fc26c52b1f468c8))

## [1.3.1](https://github.com/FPGA-Research/FABulous/compare/v1.3.0...v1.3.1) (2025-09-04)


### Bug Fixes

* **docs:** RTD build broken ([#451](https://github.com/FPGA-Research/FABulous/issues/451)) ([43bb5e0](https://github.com/FPGA-Research/FABulous/commit/43bb5e0ef19ce995880bb656200b918c0b456729))
* **docs:** Switch to default RTD theme, since the old one was broken  ([#453](https://github.com/FPGA-Research/FABulous/issues/453)) ([cd9f2a8](https://github.com/FPGA-Research/FABulous/commit/cd9f2a8d3169e758346f1bc32072feb30aa9668b))
