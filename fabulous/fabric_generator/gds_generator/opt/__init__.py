"""Optimisations of the FABulous GDS flow.

`tile_area_opt` shrinks one tile's die around a clean implementation and
`fabric_area_opt` sizes every tile of a fabric at once from their explored
implementations. The placement-driven optimisations read the placement
`FABulous.DumpPlacement` writes back out of OpenDB and propose the inputs of
the next iteration: `config_mapping` moves each configuration bit to the frame
crosspoint nearest its latch and `tile_interface` lays the border pins out by
the logic they feed. `loop` carries the proposals between iterations and
`placement_opt` is the area optimisation that runs them, which no hardening
flow uses.
"""
