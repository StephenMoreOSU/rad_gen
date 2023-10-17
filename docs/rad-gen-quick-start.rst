Quick Start Guide
=================

Clone Repository
----------------

.. code-block:: bash

   $ cd ~ && git clone --recurse-submodules git@github.com:StephenMoreOSU/rad_gen.git
   $ cd rad_gen


Python Setup
------------

.. code-block:: bash

   $ # create conda env from yaml file
   $ conda env create -f conda_env/env.yaml
   $ # activate conda env with below command
   $ conda activate rad-gen-env
   $ # For developers its convenient to install some libraries as editable python libs
   $ # We can do this in hammer with the following commands:
   $ cd vlsi/hammer
   $ # Installs an editable version of hammer to the conda env
   $ python3 -m pip install -e .
   $ # source a script which adds hammer modules to PYTHONPATH
   $ source env_setup.sh

ASAP7 PDK Setup
---------------

#. The ASAP7 pdk is large so its not specified as a submodule to RAD-Gen. Users will have to clone this themselves, create a directory in a desired workspace that will be used to store ASAP7 and possibly other pdks:
#. Optional: after cloning the ASAP7 follow `instructions <https://github.com/The-OpenROAD-Project/asap7/blob/master/asap7PDK_r1p7/README_ASAP7PDK_INSTALL_201210a.txt>`_ to set it up for cadence virtuoso
    a. This is only needed if virtuoso GDS extraction / DRC / LVS is required (not needed for vanilla asic flow)

.. code-block:: bash

   $ cd ~ && mkdir -p pdks && cd pdk
   $ git clone git@github.com:The-OpenROAD-Project/asap7.git
   $ cd asap7

#. ASAP7 is supported for open source and commercial tools:
    * Commercial: Cadence
    * genus → Synthesis
    * innovus → Place & Route
    * tempus → Static Timing Analysis
    * Open Source: `OpenROAD <https://github.com/The-OpenROAD-Project/OpenROAD`_

++++++++++++++++++++++++++++++++++++++++++++++++++++++
RAD-Gen ASIC Flow ASAP7 Specific Dependencies
++++++++++++++++++++++++++++++++++++++++++++++++++++++

- `Cadence Genus <https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/synthesis/genus-synthesis-solution.html>`_ → Synthesis
- `Cadence Innovus <https://www.cadence.com/en_US/home/tools/digital-design-and-signoff/soc-implementation-and-floorplanning/innovus-implementation-system.html>`_ → Place & Route
- `Synopsys PrimeTime <https://www.synopsys.com/implementation-and-signoff/signoff/primetime.html>`_ → Timing & Power
- `(Optional) Cadence Virtuoso <https://www.cadence.com/en_US/home/tools/custom-ic-analog-rf-design/layout-design/virtuoso-layout-suite.html>`_ → Full custom + GDS manipulation

The above commercial tools are required for the below examples, however, due to hammers support for OpenROAD, it would be possible to run it was well with modification to config files. However this is **untested**.


If they are installed correctly the following commands should return executable paths:

.. code-block:: bash

   $ which genus
   $ which innovus
   $ which pt_shell
   $ # Below for COFFE / 3D IC flow
   $ which hspice
   $ # Below is Optional
   $ which virtuoso


Running RAD-Gen
--------------------------------
A library of unit tests can be found at <rad_gen_top>/unit_tests. They include all the relevant configuration files needed for RAD-Gen modes of operation.
Execution of the unit tests is shown in the following code block:

.. code-block:: bash

   $ # from <rad_gen_top>
   $ python3 unit_tests/ci_tests.py
   $ # If a user wants to print (and not run) the relevant CLI commands which will be executed for each test they can add the "-p" or "--just_print" flag 
   $ python3 unit_tests/ci_tests.py -p

The following examples are taken from the ci_tests.py script.

++++++++++++++++++++++++++++++++++++++++++++++++++++++
ALU ASIC FLOW EXAMPLE
++++++++++++++++++++++++++++++++++++++++++++++++++++++

The below example demonstrates how a user can sweep an ALU across a range of target clock frequencies specified in a configuration file and run a hammer based asic flow for one of the sweep data points. 

.. code-block:: bash

   $ # from <rad_gen_top>
   $ python3 rad_gen.py --subtools asic_dse --env_config_path unit_tests/inputs/asic_dse/sys_configs/asic_dse_env.yml --design_sweep_config unit_tests/inputs/asic_dse/sweeps/alu_sweep.yml

The above command will create a few different configuration files in the unit_tests/inputs/asic_dse/alu/configs directory each of which has a different target clock frequency.
We will then execute the asic flow with a single one of these configurations.

.. code-block:: bash

   $ # from <rad_gen_top>
   $ python3 rad_gen.py --subtools asic_dse --env_config_path unit_tests/inputs/asic_dse/sys_configs/asic_dse_env.yml 
   --flow_mode hammer --top_lvl_module alu_ver --hdl_path unit_tests/inputs/asic_dse/alu/rtl --manual_obj_dir unit_tests/outputs/asic_dse/alu_ver/alu_ver_hammer_ci_test
   --flow_config_paths unit_tests/inputs/asic_dse/sys_configs/asap7.yml unit_tests/inputs/asic_dse/sys_configs/cadence_tools.yml unit_tests/inputs/asic_dse/alu/configs/alu_period_2.0.yaml 

At this point its useful to begin to breakdown some of the above cli arguments to better understand what the tool is doing.
More information about each one of these commands/configurations can be found in the :ref:`ASIC-DSE` section of the documentation.

At the end of the flow you should get an output report that looks something like below. This is a summary of the results of the flow.
It has sections for PPA, VLSI parameters, and hardware information. There are also sections for what stage of the asic flow the PPA results come from.
This gives users an idea of their accuracy.

.. code-block:: bash

   # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------
   #  Target Freq  |  Timing SRC  |    Slack     |    Delay     |Top Level Inst|  Total Area  |   Area SRC   |  Power SRC   | Total Power  |   GDS Area   
   # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------
   #     2.0 ns    |     par      |   1332.785   |   2016.213   |   alu_ver    |   1084.519   |     par      |     par      |  0.1590735   |  159.437394  
   # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------

++++++++++++++++++++++++++++++++++++++++++++++++++++++
COFFE FLOW EXAMPLE
++++++++++++++++++++++++++++++++++++++++++++++++++++++

We will use the COFFE subtool in RAD-Gen to size a 7nm FPGA fabric with an ALU hardblock. 
COFFE will perform transistor sizing for fpga custom circuit logic and muxing required to interact with the ALU hardblock. 
The hardblock will be ran through a hammer based asic flow using ASAP7.

.. code-block:: bash

   $ python3 rad_gen.py --subtools coffe --max_iterations 1 --fpga_arch_conf_path unit_tests/inputs/coffe/finfet_7nm_fabric_w_hbs/finfet_7nm_fabric_w_hbs.yml 
   --hb_flows_conf_path unit_tests/inputs/coffe/finfet_7nm_fabric_w_hbs/hb_flows.yml

++++++++++++++++++++++++++++++++++++++++++++++++++++++
IC 3D FLOW EXAMPLE
++++++++++++++++++++++++++++++++++++++++++++++++++++++

The below example calls the IC_3D subtool, the flags determine if buffer DSE, PDN modeling, or other options are performed.

.. code-block:: bash

   $ python3 rad_gen.py --subtools ic_3d --input_config_path unit_tests/inputs/ic_3d/3D_ic_explore.yaml --buffer_dse
   $ # to run PDN modeling replace the --buffer_dse flag with the --pdn_modeling flag as shown below:
   $ python3 rad_gen.py --subtools ic_3d --input_config_path unit_tests/inputs/ic_3d/3D_ic_explore.yaml --pdn_modeling
