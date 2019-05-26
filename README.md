wb_intercon
===========

Wishbone interconnect utilities

Files
-----

- *wb_mux.v* Wishbone multiplexer
- *wb_arbiter.v* Wishbone round-robin arbiter
- *wb_data_resize.v* Converts 32-bit accesses from master to 8-bit slaves
- *wb_upsizer.v* Converts accesses from a master to a slave with N times wider data path

wb_intercon also implements a FuseSoC generator called wb_intercon_gen. More info and usage can be found by running `fusesoc gen show wb_intercon_gen` once wb_intercon is added to the FuseSoC library
