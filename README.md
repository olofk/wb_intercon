wb_intercon
===========

Wishbone interconnect utilities

Files
-----

- *wb_mux.v* Wishbone multiplexer
- *wb_arbiter.v* Wishbone round-robin arbiter
- *wb_data_resize.v* Converts 32-bit accesses from master to 8-bit slaves
- *wb_upsizer.v* Converts accesses from a master to a slave with N times wider data path


TODO
----

Implement support for CDC between masters and slaves
wb_intercon_gen: Optionally disable wire generation in .vh
Allow arbitrary (byte granularity) width for masters and slaves
Add AXI4/AXI4-Lite converters
Write base address and size as parameters to a separate include file
Write documentation
