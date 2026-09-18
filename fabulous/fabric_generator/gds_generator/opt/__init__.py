"""Placement-driven optimisation of the FABulous GDS flow.

`config_mapping` moves each configuration bit to the frame crosspoint nearest
its latch, over the geometry `placement` loads; `placement_opt` is the loop that
runs it and carries its proposals from one iteration to the next. No hardening
flow uses any of it.
"""
