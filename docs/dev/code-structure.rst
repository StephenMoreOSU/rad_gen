Code Structure 
==============



Overview
----------

.. code-block:: text

    src
    ├── asic_dse
    │   ├── __init__.py
    │   ├── asic_dse.py
    │   ├── custom_flow.py
    │   ├── hammer_flow.py
    │   └── sram_compiler.py
    ├── coffe
    │   ├── __init__.py
    │   ├── basic_subcircuits.py
    │   ├── ble.py
    │   ├── carry_chain.py
    │   ├── cb_mux.py
    │   ├── circuit_baseclasses.py
    │   ├── coffe.py
    │   ├── constants.py
    │   ├── cost.py
    │   ├── data_structs.py
    │   ├── debug.py
    │   ├── ff_subcircuits.py
    │   ├── fpga.py
    │   ├── gen_routing_loads.py
    │   ├── hardblock.py
    │   ├── load_subcircuits.py
    │   ├── logic_block.py
    │   ├── lut.py
    │   ├── lut_subcircuits.py
    │   ├── memory_subcircuits.py
    │   ├── mux.py
    │   ├── mux_subcircuits.py
    │   ├── parsing.py
    │   ├── plotting.py
    │   ├── ram.py
    │   ├── sb_mux.py
    │   ├── spice.py
    │   ├── top_level.py
    │   ├── tran_sizing.py
    │   ├── utils.py
    │   └── vpr.py
    ├── common
    │   ├── __init__.py
    │   ├── constants.py
    │   ├── data_structs.py
    │   ├── gds_fns.py
    │   ├── rr_parse.py
    │   ├── spice_parser.py
    │   └── utils.py
    ├── ic_3d
    │   ├── __init__.py
    │   ├── buffer_dse.py
    │   ├── ic_3d.py
    │   ├── pdn_modeling.py
    │   └── sens_study_plot.py
    └── rad_gen
        ├── __init__.py
        └── main.py


The modules that make up RAD-Gen are organized into subdirectories based on their functionality. 
The main subdirectories are asic_dse, coffe, ic_3d, and common. Each of these subdirectories contains a set of Python modules that implement the functionality of the subtool. 
The rad_gen directory contains the main entry point for the RAD-Gen tool.

It consists of the following submodules:

* ``rad_gen``: Contains the main entry point for the RAD-Gen tool in ``main.py``.
* ``asic_dse``: Used for performing design space exploration and running designs through a standard cell ASIC flow.
* ``coffe``: Used for circuit / transistor level design space exploration, PPA analysis of parameterized FPGA architectures, and transistor sizing on FPGA circuitry. 
* ``ic_3d``: Used for modeling 3D Die-to-die connections / drivers and Power Delivery Networks (PDNs) for 2D & 3D integrated circuits.
* ``common``: Contains modules that are shared across the different subtools, such as data structures, utility functions, and initialization logic.

Data structures, initialization, and utilities: common
-------------------------------------------------------

* ``data_structs.py``: Contains data structures used across RAD-Gen.
* ``utils.py``: Contains generic utility functions and those used for struct initialization across RAD-Gen.
* ``rr_parse.py``: Has functionality for parsing a VPR generated RRG and outputting result statistics to csv that can be injested by COFFE.
* ``spice_parser.py``: Contains functions for parsing spice netlists and extracting information from them.
* ``gds_fns.py``: Functions for manipulating GDS files in python.

ASIC flow + SRAM compiler: ASIC-DSE
--------------------------------------

The following modules in this package are used to run a standard cell ASIC flow with the hammer backend.

* ``hammer_flow.py``: Functions to run a standard cell ASIC flow with the hammer backend.
* ``custom_flow.py``: Functions to run a standard cell ASIC flow with custom tcl scripts backend, using design_compiler, innovus, and primetime.
* ``sram_compiler.py``: Functions for running SRAM macros through standard cell ASIC flow and generating larger SRAMs from smaller ones.
* ``asic_dse.py``: Top level functionality for running standard cell ASIC flows, design space exploration, sweeps, and parsers.

FPGA circuit level DSE + transistor sizing: COFFE
--------------------------------------------------

The following modules in this package are used to model circuitry that exists in the FPGA. 
They all are classes that inherit from the ``SizeableCircuit`` object.

* ``mux.py``: Base implementation for mux circuits inherited by other mux circuits like (``cb_mux.py``, ``sb_mux.py``, ...).
* ``cb_mux.py``: Connection block mux circuit & testbench implementation(s)
* ``sb_mux.py``: Switch block mux circuit & testbench implementation(s)
* ``ble.py``: BLE and related circuitry & testbench implementation(s)
* ``carry_chain.py``: Carry chain circuit & testbench implementation(s)
* ``gen_routing_loads.py``: General programmable routing loads implementations(s)
* ``hardblock.py``: Hardblock custom circuitry and testbench implementation(s)
* ``logic_block.py``: Logic cluster circuitry and testbench implementation(s)
* ``lut.py``: Lookup table circuitry and testbench implementation(s)
* ``ram.py``: BRAM and related circuitry & testbench implementation(s)

Following modules are used to write out raw spice netlists for each legal mode of operation.
The majority of COFFE creates the spice netlists libs from data structure objects, however, 
because of time constraints to refactoring, the below files still write out raw spice.

* ``basic_subcircuits.py``: Writes out basic subcircuits, like transistor, inverter, nand, etc primatives.
* ``ff_subcircuits.py``: flip-flop subcircuits.
* ``lut_subcircuits.py``: lookup table subcircuits.
* ``load_subcircuits.py``: load related subcircuits.

The following modules are for data structures used in COFFE

* ``constants.py``: Constsants used in COFFE
* ``data_structs.py``: Data structures used in COFFE
* ``circuit_baseclasses.py``: Base classes for (legacy) circuit objects in COFFE 

The following modules are for parsing outputs, plotting results, and debugging.

* ``plotting.py``: Generates pie plots for area, delay, power breakdowns of COFFE results.
* ``parsing.py``: Parses the COFFE output report to be processed or plotted downstream.
* ``debug.py``: Debugging functionality for COFFE.

3D Die-to-die connections + PDN modeling: IC-3D
-------------------------------------------------

* ``ic_3d.py``: Top level entry point for IC-3D functionality. Contains main function for running each mode of operation of IC-3D.
* ``buffer_dse.py``: Functions for running buffer design space exploration on 3D ICs. 
* ``pdn_modeling.py``: Functions for modeling the power delivery network on FPGAs for 2/3D ICs.



