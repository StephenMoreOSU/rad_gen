.. RAD Flow documentation master file, created by
   sphinx-quickstart on Tue Aug 15 16:35:52 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.



######################################
Welcome to RAD-Gen's Documentation
######################################

.. ======================================


RAD-Gen is a tool for silicon area/timing/power implementation results of hard (ASIC) components, FPGA fabric circuitry, and circuit modeling of 3D devices/packaging. It is part of the greater
RAD Flow, which is an open source academic architecture exploration and evaluation flow for novel beyond-FPGA reconfigurable accelerator devices (RADs).
Hard blocks may be network on chips (NoCs), tensor accelerators, or memory macros. RAD-Gen leverages the UC Berkeley `Hammer <https://hammer-vlsi.readthedocs.io/en/stable/index.html>`_ framework to enable a PDK & Tool agnostic ASIC flow.

RAD-Gen is made up of three subtools: ASIC-DSE, COFFE, and IC-3D.

RAD-Gen is under heavy development.


***********************************
Quick Start
***********************************

.. toctree::
   :maxdepth: 2

   quickstart/index


***********************************
Tools Overview
***********************************

.. toctree::
   :maxdepth: 2
   
   common/index
   asic_dse/index
   ic_3d/index
   coffe/index


***********************************
For Developers
***********************************

.. toctree::
   :maxdepth: 1
   
   api/out/modules
   dev/code-structure

.. * tb - testbench - Some logic defined to inject expected inputs to a hardware module,
  capture outputs and compare with some expected results to verify functionality.
   api/index








How to Cite
***********************************

The following paper may be used as a general citation for RAD-Gen:

.. code-block:: bibtex

<<<<<<< HEAD
   @inproceedings{rad-gen,
      title = {{Into the Third Dimension: Architecture Exploration Tools for 3D Reconfigurable Acceleration Devices}},
      author = {Boutros, Andrew and Mahmoudi, Fatemehsadat and Mohaghegh, Amin and More, Stephen and Betz, Vaughn},
      booktitle = {IEEE International Conference on Field-Programmable Technology (FPT)},
      year = {2023}
   }

=======
	@inproceedings{rad-gen,
	    title = {{Into the Third Dimension: Architecture Exploration Tools for 3D Reconfigurable Acceleration Devices}},
	    author = {Boutros, Andrew and Mahmoudi, Fatemehsadat and Mohaghegh, Amin and More, Stephen and Betz, Vaughn},
	    booktitle = {IEEE International Conference on Field-Programmable Technology (FPT)},
	    year = {2023}
	}
>>>>>>> master


Indices and tables
***********************************

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`





.. - **RAD-Sim:** A SystemC simulator for rapid design space exploration and architecture-application co-design

.. - **RAD-Gen:** A push button tool for silicon area/timing/power implementation results of hard (ASIC) RAD components, FPGA fabric circuitry, and different 3D considerations (Under development)

.. .. image:: _static/radflow.png
  :width: 1000
  :alt: RAD Flow Overview

<<<<<<< HEAD

.. .. automodule:: asic_dse.hammer_flow
..    :members:
..    :undoc-members:
..    :show-inheritance:

.. quickstart/index
=======
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
>>>>>>> master
