# Changelog

## [3.0.0](https://github.com/FPGA-Research/FABulous/compare/v2.0.0...v3.0.0) (2026-02-19)


### ⚠ BREAKING CHANGES

* file rename ([#588](https://github.com/FPGA-Research/FABulous/issues/588))
* Changing getTile to be more general ([#564](https://github.com/FPGA-Research/FABulous/issues/564))

### Features

* add .sv suffix support ([#580](https://github.com/FPGA-Research/FABulous/issues/580)) ([565ba7b](https://github.com/FPGA-Research/FABulous/commit/565ba7bacf0189d26c661a3235df52fdd580b6ae))
* add fabulator to nix ([8cd1ce4](https://github.com/FPGA-Research/FABulous/commit/8cd1ce4bab001ebfa36f3bca91fbccde9599ae27))
* add fabulator to nix ([#556](https://github.com/FPGA-Research/FABulous/issues/556)) ([76531e0](https://github.com/FPGA-Research/FABulous/commit/76531e0ab2b4b9329624e211900780a66c03696d))
* add output dir for swtich matrix csv gen ([#583](https://github.com/FPGA-Research/FABulous/issues/583)) ([bbe17ec](https://github.com/FPGA-Research/FABulous/commit/bbe17ec423f3d34fbdcf3877146c29931eec7ed6))
* Add support for blackbox modules in BELs ([#599](https://github.com/FPGA-Research/FABulous/issues/599)) ([0af25ef](https://github.com/FPGA-Research/FABulous/commit/0af25efb44b270a42a08d2597cd4555c08fa8bce))
* allow disable UserCLK port adding ([#581](https://github.com/FPGA-Research/FABulous/issues/581)) ([4487838](https://github.com/FPGA-Research/FABulous/commit/4487838902a66c1ed3c90a8949f60457c5a1316a))
* Changing getTile to be more general ([#564](https://github.com/FPGA-Research/FABulous/issues/564)) ([aec7d93](https://github.com/FPGA-Research/FABulous/commit/aec7d930a9ab55403d1b7fd2997351bd270f6104))
* Extending CLI utils for gds flow ([#572](https://github.com/FPGA-Research/FABulous/issues/572)) ([993a940](https://github.com/FPGA-Research/FABulous/commit/993a94022d2505ec9eb855fa6abd472730e37887))
* extending gds helper and testing it ([#565](https://github.com/FPGA-Research/FABulous/issues/565)) ([162dd65](https://github.com/FPGA-Research/FABulous/commit/162dd65b283974143a65559e43f0786bb399ac72))
* Librelane flows and commands ([#500](https://github.com/FPGA-Research/FABulous/issues/500)) ([fce6d59](https://github.com/FPGA-Research/FABulous/commit/fce6d59fda03736d68d776ab623a4308af412307))
* nix based docker image ([#553](https://github.com/FPGA-Research/FABulous/issues/553)) ([834a2ca](https://github.com/FPGA-Research/FABulous/commit/834a2ca511b36f5ca8d68d99c999a302fcad3e0c))
* tile class helper for gds flow ([#571](https://github.com/FPGA-Research/FABulous/issues/571)) ([f81dcba](https://github.com/FPGA-Research/FABulous/commit/f81dcba5688db86ac9e1203dbf4f169ccce29b7f))


### Bug Fixes

* Add PDK env vars only if PDK exists ([#590](https://github.com/FPGA-Research/FABulous/issues/590)) ([b021aab](https://github.com/FPGA-Research/FABulous/commit/b021aab4bad38624abe35f4291f3824ddd529897))
* fix LVS error ([#593](https://github.com/FPGA-Research/FABulous/issues/593)) ([730d396](https://github.com/FPGA-Research/FABulous/commit/730d396d7ead62d85ab1c06d03c2ab7ea1700abd))
* fix stale error code ([#576](https://github.com/FPGA-Research/FABulous/issues/576)) ([1d80440](https://github.com/FPGA-Research/FABulous/commit/1d8044018020a2705c670e7d79b6ffb21fcb1b27))
* Fix tile io place script and extend script testing ([#566](https://github.com/FPGA-Research/FABulous/issues/566)) ([89058cd](https://github.com/FPGA-Research/FABulous/commit/89058cd2fa1c6e34cf299a7f323f747f95b3e431))
* fixes Nix env to include yosys ([#555](https://github.com/FPGA-Research/FABulous/issues/555)) ([2924b99](https://github.com/FPGA-Research/FABulous/commit/2924b99b7fd287f61d6fd7a49ee284f89b99d118))
* fixing steps that is for gds flow ([#570](https://github.com/FPGA-Research/FABulous/issues/570)) ([01e4aae](https://github.com/FPGA-Research/FABulous/commit/01e4aae5cbed01f92c9fab97bb251db25601ab71))
* hardcode user name to lower case ([834a2ca](https://github.com/FPGA-Research/FABulous/commit/834a2ca511b36f5ca8d68d99c999a302fcad3e0c))
* **parse_csv:** move tile finalisation out of item-parsing loop ([#604](https://github.com/FPGA-Research/FABulous/issues/604)) ([a93a7f1](https://github.com/FPGA-Research/FABulous/commit/a93a7f13aa0a08da4857d9eb14f9f17ad77601c0))
* validate tile name matches folder name and guard empty tile list ([#603](https://github.com/FPGA-Research/FABulous/issues/603)) ([11201c7](https://github.com/FPGA-Research/FABulous/commit/11201c7325e717f5a350fc904957b3bfb9871b97))


### Documentation

* Fix typo in CARRY attribute annotation ([#592](https://github.com/FPGA-Research/FABulous/issues/592)) ([70d8417](https://github.com/FPGA-Research/FABulous/commit/70d8417f6aa574da1a7d1121dcf94bddc0b39675))


### Miscellaneous Chores

* file rename ([#588](https://github.com/FPGA-Research/FABulous/issues/588)) ([21daada](https://github.com/FPGA-Research/FABulous/commit/21daada585aec3a08d4041470a75af1a8f0a6cbb))

## [1.3.1](https://github.com/FPGA-Research/FABulous/compare/v1.3.0...v1.3.1) (2025-09-04)


### Bug Fixes

* **docs:** RTD build broken ([#451](https://github.com/FPGA-Research/FABulous/issues/451)) ([43bb5e0](https://github.com/FPGA-Research/FABulous/commit/43bb5e0ef19ce995880bb656200b918c0b456729))
* **docs:** Switch to default RTD theme, since the old one was broken  ([#453](https://github.com/FPGA-Research/FABulous/issues/453)) ([cd9f2a8](https://github.com/FPGA-Research/FABulous/commit/cd9f2a8d3169e758346f1bc32072feb30aa9668b))
