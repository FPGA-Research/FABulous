# Changelog

## [3.0.0](https://github.com/FPGA-Research/FABulous/compare/v2.0.0...v3.0.0) (2026-04-10)


### ⚠ BREAKING CHANGES

* clean up break_comb_loop and buffered mux ([#630](https://github.com/FPGA-Research/FABulous/issues/630))
* file rename ([#588](https://github.com/FPGA-Research/FABulous/issues/588))
* Changing getTile to be more general ([#564](https://github.com/FPGA-Research/FABulous/issues/564))

### Features

* add .sv suffix support ([#580](https://github.com/FPGA-Research/FABulous/issues/580)) ([565ba7b](https://github.com/FPGA-Research/FABulous/commit/565ba7bacf0189d26c661a3235df52fdd580b6ae))
* add dev container ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* add fabulator to nix ([8cd1ce4](https://github.com/FPGA-Research/FABulous/commit/8cd1ce4bab001ebfa36f3bca91fbccde9599ae27))
* add fabulator to nix ([#556](https://github.com/FPGA-Research/FABulous/issues/556)) ([76531e0](https://github.com/FPGA-Research/FABulous/commit/76531e0ab2b4b9329624e211900780a66c03696d))
* add gen_io_pin_config cmd ([#635](https://github.com/FPGA-Research/FABulous/issues/635)) ([2b8278f](https://github.com/FPGA-Research/FABulous/commit/2b8278fee9a613a10b7d8f1a0a7735b7e159c929))
* add output dir for swtich matrix csv gen ([#583](https://github.com/FPGA-Research/FABulous/issues/583)) ([bbe17ec](https://github.com/FPGA-Research/FABulous/commit/bbe17ec423f3d34fbdcf3877146c29931eec7ed6))
* Add scripting possibilities for reference tests  ([#657](https://github.com/FPGA-Research/FABulous/issues/657)) ([b8a790c](https://github.com/FPGA-Research/FABulous/commit/b8a790ccb06b72a95df49cdf3fbac69b98d5c6fc))
* Add support for blackbox modules in BELs ([#599](https://github.com/FPGA-Research/FABulous/issues/599)) ([0af25ef](https://github.com/FPGA-Research/FABulous/commit/0af25efb44b270a42a08d2597cd4555c08fa8bce))
* allow disable UserCLK port adding ([#581](https://github.com/FPGA-Research/FABulous/issues/581)) ([4487838](https://github.com/FPGA-Research/FABulous/commit/4487838902a66c1ed3c90a8949f60457c5a1316a))
* auto pdk set up ([#606](https://github.com/FPGA-Research/FABulous/issues/606)) ([b9b530a](https://github.com/FPGA-Research/FABulous/commit/b9b530a591c121c738d55340c1acf9c802a1ccda))
* better cli opt mode complete ([#658](https://github.com/FPGA-Research/FABulous/issues/658)) ([47ccf73](https://github.com/FPGA-Research/FABulous/commit/47ccf736d05c9931a98f3d746efd3120986ddb52))
* better error msg on validation error ([#629](https://github.com/FPGA-Research/FABulous/issues/629)) ([5e42e9b](https://github.com/FPGA-Research/FABulous/commit/5e42e9b6055e454a2baeaa96691ef510c42e60f7))
* better model_pack.v relative path ([#675](https://github.com/FPGA-Research/FABulous/issues/675)) ([a50a6b3](https://github.com/FPGA-Research/FABulous/commit/a50a6b352034050e629339b17e638b6bf8350db1))
* Changing getTile to be more general ([#564](https://github.com/FPGA-Research/FABulous/issues/564)) ([aec7d93](https://github.com/FPGA-Research/FABulous/commit/aec7d930a9ab55403d1b7fd2997351bd270f6104))
* dev-container and VNC ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* Devcontainer and codespaces ([#559](https://github.com/FPGA-Research/FABulous/issues/559)) ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* Extending CLI utils for gds flow ([#572](https://github.com/FPGA-Research/FABulous/issues/572)) ([993a940](https://github.com/FPGA-Research/FABulous/commit/993a94022d2505ec9eb855fa6abd472730e37887))
* extending gds helper and testing it ([#565](https://github.com/FPGA-Research/FABulous/issues/565)) ([162dd65](https://github.com/FPGA-Research/FABulous/commit/162dd65b283974143a65559e43f0786bb399ac72))
* fabric name ([#627](https://github.com/FPGA-Research/FABulous/issues/627)) ([ed363d7](https://github.com/FPGA-Research/FABulous/commit/ed363d7692a25c76d1e96ae7f9ee45502edff6fe))
* fix image to have dev container support ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* from single image to dev/release ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* Librelane flows and commands ([#500](https://github.com/FPGA-Research/FABulous/issues/500)) ([fce6d59](https://github.com/FPGA-Research/FABulous/commit/fce6d59fda03736d68d776ab623a4308af412307))
* more flexible simulation command  ([#623](https://github.com/FPGA-Research/FABulous/issues/623)) ([0481ba6](https://github.com/FPGA-Research/FABulous/commit/0481ba6bc3a074c08b1991e837939b793838df00))
* nix based docker image ([#553](https://github.com/FPGA-Research/FABulous/issues/553)) ([834a2ca](https://github.com/FPGA-Research/FABulous/commit/834a2ca511b36f5ca8d68d99c999a302fcad3e0c))
* tile class helper for gds flow ([#571](https://github.com/FPGA-Research/FABulous/issues/571)) ([f81dcba](https://github.com/FPGA-Research/FABulous/commit/f81dcba5688db86ac9e1203dbf4f169ccce29b7f))


### Bug Fixes

* Add PDK env vars only if PDK exists ([#590](https://github.com/FPGA-Research/FABulous/issues/590)) ([b021aab](https://github.com/FPGA-Research/FABulous/commit/b021aab4bad38624abe35f4291f3824ddd529897))
* disable personal setup to save space ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* fix deprecated name leading to variable propagation failing ([#664](https://github.com/FPGA-Research/FABulous/issues/664)) ([cc9ffe4](https://github.com/FPGA-Research/FABulous/commit/cc9ffe46cd34cef2259bed560632855826a6fb2a))
* fix dev-container requirement ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* fix gui on docker ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* fix klayout command ([#671](https://github.com/FPGA-Research/FABulous/issues/671)) ([a83c103](https://github.com/FPGA-Research/FABulous/commit/a83c1036ea88b6d3fb046629c5e50637ab0b43b9))
* fix LVS error ([#593](https://github.com/FPGA-Research/FABulous/issues/593)) ([730d396](https://github.com/FPGA-Research/FABulous/commit/730d396d7ead62d85ab1c06d03c2ab7ea1700abd))
* fix matching ([#661](https://github.com/FPGA-Research/FABulous/issues/661)) ([39adb35](https://github.com/FPGA-Research/FABulous/commit/39adb35a78b5fbed6a22fd39b3ad0b6f64a0e4a7))
* fix PDK path resolution error ([#670](https://github.com/FPGA-Research/FABulous/issues/670)) ([7900a7d](https://github.com/FPGA-Research/FABulous/commit/7900a7d215f0af207c12fe8c54cf2ff69833e9c5))
* fix stale error code ([#576](https://github.com/FPGA-Research/FABulous/issues/576)) ([1d80440](https://github.com/FPGA-Research/FABulous/commit/1d8044018020a2705c670e7d79b6ffb21fcb1b27))
* Fix tile io place script and extend script testing ([#566](https://github.com/FPGA-Research/FABulous/issues/566)) ([89058cd](https://github.com/FPGA-Research/FABulous/commit/89058cd2fa1c6e34cf299a7f323f747f95b3e431))
* fix tile_io_place script ([#668](https://github.com/FPGA-Research/FABulous/issues/668)) ([e171ffd](https://github.com/FPGA-Research/FABulous/commit/e171ffd1ee5601695af3e3ae554eb5f270c0ac28))
* fix when ciel is never used before ([#617](https://github.com/FPGA-Research/FABulous/issues/617)) ([856654f](https://github.com/FPGA-Research/FABulous/commit/856654f96d7ba97effd42651ba148c43f9752b23))
* fixes Nix env to include yosys ([#555](https://github.com/FPGA-Research/FABulous/issues/555)) ([2924b99](https://github.com/FPGA-Research/FABulous/commit/2924b99b7fd287f61d6fd7a49ee284f89b99d118))
* fixing steps that is for gds flow ([#570](https://github.com/FPGA-Research/FABulous/issues/570)) ([01e4aae](https://github.com/FPGA-Research/FABulous/commit/01e4aae5cbed01f92c9fab97bb251db25601ab71))
* hardcode user name to lower case ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* hardcode user name to lower case ([834a2ca](https://github.com/FPGA-Research/FABulous/commit/834a2ca511b36f5ca8d68d99c999a302fcad3e0c))
* move from single to double config ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* **parse_csv:** move tile finalisation out of item-parsing loop ([#604](https://github.com/FPGA-Research/FABulous/issues/604)) ([a93a7f1](https://github.com/FPGA-Research/FABulous/commit/a93a7f13aa0a08da4857d9eb14f9f17ad77601c0))
* **pre-commit:** Reactivate pre-commit for new folder structure ([#655](https://github.com/FPGA-Research/FABulous/issues/655)) ([ff7e22c](https://github.com/FPGA-Research/FABulous/commit/ff7e22c18113aa5d7cbb94d4d15a8277ee544ac4))
* small typo in docstring of gen_fabric() in fabulous_api.py ([#637](https://github.com/FPGA-Research/FABulous/issues/637)) ([31630f9](https://github.com/FPGA-Research/FABulous/commit/31630f9f910829e625d899b9a4b2ce9fa5742f38))
* **tests:** isolate FAB_USER_CONFIG_DIR from real ~/.fabulous/.env ([#609](https://github.com/FPGA-Research/FABulous/issues/609)) ([f589b8c](https://github.com/FPGA-Research/FABulous/commit/f589b8c27a080bd0439445bc399f1d332729a09c))
* update base image requirement ([a5678f7](https://github.com/FPGA-Research/FABulous/commit/a5678f7bf320dd88b6fbf0c08229a59b495b3561))
* validate tile name matches folder name and guard empty tile list ([#603](https://github.com/FPGA-Research/FABulous/issues/603)) ([11201c7](https://github.com/FPGA-Research/FABulous/commit/11201c7325e717f5a350fc904957b3bfb9871b97))


### Documentation

* add BelMap attribute and SHARED_PORT limitation to primitives section ([#611](https://github.com/FPGA-Research/FABulous/issues/611)) ([3229fe1](https://github.com/FPGA-Research/FABulous/commit/3229fe1fd7a38bde49e23b648b5736846df46d2f)), closes [#560](https://github.com/FPGA-Research/FABulous/issues/560) [#561](https://github.com/FPGA-Research/FABulous/issues/561)
* add guidelines for AI and coding assistant usage ([#613](https://github.com/FPGA-Research/FABulous/issues/613)) ([7b5ac2d](https://github.com/FPGA-Research/FABulous/commit/7b5ac2dd21c125e1f383672a69b2fd58629cf051)), closes [#535](https://github.com/FPGA-Research/FABulous/issues/535)
* clarify purpose of simulation and emulation ([#614](https://github.com/FPGA-Research/FABulous/issues/614)) ([15dc628](https://github.com/FPGA-Research/FABulous/commit/15dc6280c99092841a05d39aa8121c4dcf044771))
* document the .FABulous directory and its importance ([#612](https://github.com/FPGA-Research/FABulous/issues/612)) ([148a96e](https://github.com/FPGA-Research/FABulous/commit/148a96e380cca8be60a8d41cf377590b92b64af4))
* Fix typo in CARRY attribute annotation ([#592](https://github.com/FPGA-Research/FABulous/issues/592)) ([70d8417](https://github.com/FPGA-Research/FABulous/commit/70d8417f6aa574da1a7d1121dcf94bddc0b39675))


### Miscellaneous Chores

* clean up break_comb_loop and buffered mux ([#630](https://github.com/FPGA-Research/FABulous/issues/630)) ([dfead01](https://github.com/FPGA-Research/FABulous/commit/dfead011528eeaa060d641a214ba0137cf052e0e))
* file rename ([#588](https://github.com/FPGA-Research/FABulous/issues/588)) ([21daada](https://github.com/FPGA-Research/FABulous/commit/21daada585aec3a08d4041470a75af1a8f0a6cbb))

## [1.3.1](https://github.com/FPGA-Research/FABulous/compare/v1.3.0...v1.3.1) (2025-09-04)


### Bug Fixes

* **docs:** RTD build broken ([#451](https://github.com/FPGA-Research/FABulous/issues/451)) ([43bb5e0](https://github.com/FPGA-Research/FABulous/commit/43bb5e0ef19ce995880bb656200b918c0b456729))
* **docs:** Switch to default RTD theme, since the old one was broken  ([#453](https://github.com/FPGA-Research/FABulous/issues/453)) ([cd9f2a8](https://github.com/FPGA-Research/FABulous/commit/cd9f2a8d3169e758346f1bc32072feb30aa9668b))
