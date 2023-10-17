.. RAD Flow documentation master file, created by
   sphinx-quickstart on Tue Aug 15 16:35:52 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

RAD Gen
=============

Introduction
------------

RAD Gen is a tool for silicon area/timing/power implementation results of hard (ASIC) components, FPGA fabric circuitry, and circuit modeling of 3D devices/packaging. It is part of the greater
RAD Flow, which is an open source academic architecture exploration and evaluation flow for novel beyond-FPGA reconfigurable accelerator devices (RADs).
Hard blocks may be network on chips (NoCs), tensor accelerators, or memory macros. RAD-Gen leverages the UC Berkeley `Hammer <https://hammer-vlsi.readthedocs.io/en/stable/Hammer-Basics/Hammer-Overview.html>`_ framework to enable a PDK & Tool agnostic ASIC flow.

RAD Gen is made up of three subtools: ASIC-DSE, COFFE, and IC-3D.


#################
ASIC-DSE Features
#################

+++++++++++++++++++++++++++++++++++
Sweep RTL or VLSI design parameters
+++++++++++++++++++++++++++++++++++

- Designers may want to take a design and get PPA results across a range of VLSI parameters such as target clock frequency, # metal Layers, standard cell utilization, etc. They may also want to try different configurations for their parameterizable RTL. For example a NoC can have a range of virtual channels, flit widths, or depth of buffers depending on the application.
- RAD-Gen make above use case easier by creating a configuration file and executing a few commands.

++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
SRAM Mapper which stiches existing small macros to create larger ones
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
- There may be a case (as we found for ASAP7) in which a PDK has existing SRAM macros that are too small or have different numbers of ports than what a designer requires.
- RAD-Gen's quick and dirty solution to this problem is an SRAM mapper which inputs a user's SRAM specification and an existing library of SRAMs, using bit cell utilization as the cost function, outputting a larger SRAM stitched together with appropriate muxing & decoding logic.

++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
ASIC tool pre/post processing utilities
++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
- For each stage of the ASIC flow and subsequent post processing steps (such as GDS scaling) RAD-Gen outputs human readable & csv formatted outputs for easy integration / understanding of results


#################
COFFE Features
#################

COFFE is a tool which performs HSPICE driven automatic transistor sizing for FPGA circuitry. 
It can be used to get PPA estimates for a particular FPGA architecture. It does this by sizing transistors and optimizing PPA for the many custom circuitry that makes up an FPGA fabric.
FPGA hardblocks can be evaluated by running them through the ASIC-DSE tool and then using coffe to perform sizing on the custom logic which connects them to the programmable fabric.


#################
IC-3D Features
#################
RAD-Gen also includes tools which model 3D integrated circuits to be able to consider the affect of 3D on FPGA & RAD architectures. It includes automatic buffer chain generation using HSPICE to meet desired area / delay targets.
PDN modeling is performed by using user IR drop targets to determine how many TSVs are required for a particular configuration. This estimates the area taken up in the base die. 

- Die-to-die modeling by iteratively finding buffer chains to meet PPA targets w.r.t the driver load, defined by the 3D intergration process and packaging.
- PDN modeling to get IR drop estimates and area taken up by TSVs


.. - **RAD-Sim:** A SystemC simulator for rapid design space exploration and architecture-application co-design

.. - **RAD-Gen:** A push button tool for silicon area/timing/power implementation results of hard (ASIC) RAD components, FPGA fabric circuitry, and different 3D considerations (Under development)

.. .. image:: _static/radflow.png
  :width: 1000
  :alt: RAD Flow Overview






How to Cite
-----------

The following paper may be used as a general citation for RAD-Sim:

.. code-block:: bibtex

   @inproceedings{rad-flow-dlrm,
      title = {{A Whole New World: How to Architect Beyond?FPGA Reconfigurable Acceleration Devices?}},
      author = {Boutros, Andrew and More, Stephen and Betz, Vaughn},
      eventtitle = {2023 33nd International Conference on Field-Programmable Logic and Applications ({FPL})},
      booktitle = {2023 33nd International Conference on Field-Programmable Logic and Applications ({FPL})},
      date = {2023-09},
      publisher={IEEE}
   }

.. toctree::
   :caption: RAD-Gen Documentation
   :maxdepth: 3

   coffe-fpga-fabric
   rad-gen-quick-start
..   asic-dse
..   3d-ic-dse