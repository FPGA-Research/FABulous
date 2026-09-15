"""Optimisations of the FABulous GDS flow.

`tile_area_opt` shrinks one tile's die around a clean implementation and
`fabric_area_opt` sizes every tile of a fabric at once from their explored
implementations. `placement` is the geometry a placed tile presents to the
optimisations that read it.
"""
