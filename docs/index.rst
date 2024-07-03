.. RAD Flow documentation master file, created by
   sphinx-quickstart on Tue Aug 15 16:35:52 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. api/asic_dse/index
   api/ic_3d/index
   api/coffe/index


======================================
Welcome to RAD-Gen's Documentation
======================================


RAD-Gen is a tool for silicon area/timing/power implementation results of hard (ASIC) components, FPGA fabric circuitry, and circuit modeling of 3D devices/packaging. It is part of the greater
RAD Flow, which is an open source academic architecture exploration and evaluation flow for novel beyond-FPGA reconfigurable accelerator devices (RADs).
Hard blocks may be network on chips (NoCs), tensor accelerators, or memory macros. RAD-Gen leverages the UC Berkeley `Hammer <https://hammer-vlsi.readthedocs.io/en/stable/index.html>`_ framework to enable a PDK & Tool agnostic ASIC flow.

RAD-Gen is made up of three subtools: ASIC-DSE, COFFE, and IC-3D.

RAD-Gen is under heavy development.


+++++++++++++++++++++++++++++++++++
Quick Start
+++++++++++++++++++++++++++++++++++

.. toctree::
   :maxdepth: 2
   :caption: Quick Start

   quickstart/index

+++++++++++++++++++++++++++++++++++
API Reference
+++++++++++++++++++++++++++++++++++

.. toctree::
   :maxdepth: 1
   :caption: Subtools
   
   api/index

* tb - testbench - Some logic defined to inject expected inputs to a hardware module,
  capture outputs and compare with some expected results to verify functionality.




+++++++++++++++++++++++++++++++++++
RAD-Gen Use Cases
+++++++++++++++++++++++++++++++++++

**FPGA Fabric Evaluation**

If one wanted to evaluate an FPGA fabric on a new process technology (maybe the new ASAP5), they could use the COFFE subtool in RAD-Gen to perform automatic transistor sizing for the custom FPGA circuitry.
Custom hardblocks such as BRAMs or DSPs or any user customized RTL can be included in the user defined FPGA fabric. The COFFE subtool will call the ASIC-DSE subtool to run the standard cell ASIC flow for RTL hardblocks.
A classic evaluation that could be done would be to raise the question of what is the PPA of an FPGA at new process technology using either pass transistors or transmission gates, one could compare the PPA outputs of the two different FPGA fabrics and determine which is better for the new process technology.

**Asic Flow**

If a user wanted to compare the performance of something like a Network-on-Chip across different target clock frequencies (or other VLSI parameters), or across different numbers of virtual channels (or other RTL parameters), they could use the ASIC-DSE subtool in RAD-Gen to perform a sweep of the RTL parameters and get PPA results for each configuration.
This would allow the user to determine which configuration is best for their application or RAD Device. 

**3D IC Modeling**

If one wanted to be able to evaluate a RAD device or FPGA fabric which includes multiple dies using 3D integration, they would need to know a few things.

1. How does the 3D Power Delivery Network (PDN) affect the area available for logic and routing for each die? 

In 3D PDNs (depending on the type of bonding) often TSVs need to be put through the substrate of a die to deliver power, ground, and I/O signals going off chip. 
These TSVs act as holes in the substrate in which transistors cannot be placed, they can be thought of as a "swiss cheese". 
To know how many and where these "swiss cheese" holes are we need to try to estimate the amount of holes required to meet the IR drop targets of the RAD/FPGA device.

2. How large should the driver circuits be to communicate between dies?

Dies can be connected through solder microbumps, hybrid bonding, or a combination of them and TSVs (depending on if using Face-to-Back, Face-to-Face, etc bonding).
To be able to understand the timing, power, and area cost of these connections we would want to perform design space exploration on these drivers while they drive the inter-die connections. 

With the IC-3D subtool in RAD-Gen we can perform both of these tasks, and be able to evaluate 3D RAD/FPGA devices.
We can also create floorplans respecting the "swiss cheese" holes and enabling easier integration of our new 3D device into something like `VTR <https://docs.verilogtorouting.org/en/latest/>`_  for 3D CAD-tool evaluations. 





How to Cite
-----------

The following paper may be used as a general citation for RAD-Gen:

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
   :caption: Contents:
   :maxdepth: 4
   :numbered:

   asic_dse/index

   ic_3d/index

   coffe/index

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`



.. - **RAD-Sim:** A SystemC simulator for rapid design space exploration and architecture-application co-design

.. - **RAD-Gen:** A push button tool for silicon area/timing/power implementation results of hard (ASIC) RAD components, FPGA fabric circuitry, and different 3D considerations (Under development)

.. .. image:: _static/radflow.png
  :width: 1000
  :alt: RAD Flow Overview


.. .. automodule:: asic_dse.hammer_flow
..    :members:
..    :undoc-members:
..    :show-inheritance:

.. quickstart/index