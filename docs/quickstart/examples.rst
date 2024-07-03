Running RAD-Gen
============================


All examples shown here will have an equivalent test (using pytest) to perform the same action and verify the results. 
If you want to ensure your repo and environment have been setup correctly its strongly reccomended to run all pytests with the following command.

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ # -vv is for very verbose and -s captures stdout
   $ pytests -vv -s tests


ALU ASIC Flow Example
--------------------------------


ALU Clock Frequency Sweep
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This example demonstrates how a user can sweep an ALU across a range of target clock frequencies specified in a configuration file and run a hammer based asic flow for one of the sweep data points. 

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py --override_outputs --project_name alu --subtools asic_dse --sweep_conf_fpath tests/data/alu_vlsi_sweep/inputs/alu_sweep.yml

** Corresponding test **

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py::test_alu_vlsi_sweep_gen

The above command will create a few different configuration files in the projects/alu/configs/gen directory, each of which has a different target clock frequency.
Now that our sweep configuration files have been generated we can use one of them to run the ALU design through an ASIC flow using commercial tools and the ASAP7 PDK.

ALU Hammer ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To run the ALU design with a target period of 0ns (as fast as the tools can make it) we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py \
   --manual_obj_dir tests/data/alu_vlsi_sweep/outputs/alu_ver \
   --project_name alu \
   --subtools asic_dse \
   --compile_results \
   --flow_conf_fpaths tests/data/asic_dse/cad_tools/cadence_tools.yml tests/data/asic_dse/pdks/asap7.yml projects/alu/configs/gen/alu_base_period_0.0.json 
   --tool_env_conf_fpaths tests/data/asic_dse/env.yml \ 
   --common_asic_flow.flow_stages.par.run \
   --common_asic_flow.flow_stages.pt.run \
   --common_asic_flow.flow_stages.syn.run
.. 
   Notice how some of the command line arguments are specified hierarchically. RAD-Gen supports many different ways for users to provide configuration parameters.

** Corresponding test **
.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py::test_alu_sw_pt_asic_flow

It can be useful to breakdown some of the cli arguments to better understand what the tool is doing.
More information about each one of these commands/configurations can be found in the :ref:`ASIC-DSE` section of the documentation.

At the end of the flow you should get an output report that looks something like the below: 

.. code-block:: bash

   # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------                                                                                                                                                                          
   #  Target Freq  |  Timing SRC  |    Slack     |    Delay     |Top Level Inst|  Total Area  |   Area SRC   | Total Power  |  Power SRC   |   GDS Area                                                                                                                                                                             
   # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------                                                                                                                                                                          
   #     0.0 ns    |     par      |   -158.569   |   154.969    |   alu_ver    |   1455.201   |     par      |    0.0597    |      pt      |  340.833654                                                                                                                                                                            
   # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------  

This is a summary of the results of the flow. There will be one of these summaries printed for each flow stage (synthesis, place & route, timing, power, etc).
It has sections for PPA, `The parameter that was swept (Target Freq in this case)`, and design information. 
There are also sections for what stage of the asic flow the PPA results come from (see Area/Timing/Power SRC). 

SRAM Generator Example
--------------------------------

When using open source PDKs, it is common to not have a memory compiler capable of generating high quality SRAMs for your design. 
If one were to run a design that infers memory with its behavioral HDL through ASIC synthesis tools, the memory would usually mapped to flip flops. 
For larger memories mapping to flip flops would result in siginificantly more area and may lead to incorrect conclusions about the design.
Because RAD-Gen aims to be a higher level tool to get PPA estimates at various process technologies, it's important to be able to at least get a reasonable idea of the PPA cost of SRAMs.

For a user defined SRAM (the SRAM a user would like to insantiate in thier design) RAD-Gen will look at all available SRAM macros in a pdk,
try to find an optimal combination of such macros to meet the user defined SRAM requirements, and then stitch the primative macros together using muxing & decoding logic to create the user defined SRAM.
This will result in a suboptimal SRAM compared to that which may come out of a dedicated SRAM compiler, yet it will be a reasonable estimate of the PPA cost of the SRAM.


To run the SRAM generator for a range of SRAM widths, depths, and read write ports we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ 
   python3 rad_gen.py --override_outputs --project_name sram --subtools asic_dse --sweep_conf_fpath tests/data/sram_generator/inputs/sram_sweep.yml








COFFE FPGA Fabric w/ALU hardblock Flow Example
----------------------------------------------------------------

We will use the COFFE subtool in RAD-Gen to size a 7nm FPGA fabric with an ALU hardblock. 
COFFE will perform transistor sizing for fpga custom circuit logic and muxing required to interact with the ALU hardblock. 
The hardblock will be ran through a hammer based asic flow using ASAP7.

.. code-block:: bash

   $ python3 rad_gen.py --subtools coffe --max_iterations 1 --fpga_arch_conf_path unit_tests/inputs/coffe/finfet_7nm_fabric_w_hbs/finfet_7nm_fabric_w_hbs.yml --hb_flows_conf_path unit_tests/inputs/coffe/finfet_7nm_fabric_w_hbs/hb_flows.yml


IC 3D Flow Example
----------------------------------------------------------------

The below example calls the IC_3D subtool, the flags determine if buffer DSE, PDN modeling, or other options are performed.

.. code-block:: bash

   $ python3 rad_gen.py --subtools ic_3d --input_config_path unit_tests/inputs/ic_3d/3D_ic_explore.yaml --buffer_dse
   $ # to run PDN modeling replace the --buffer_dse flag with the --pdn_modeling flag as shown below:
   $ python3 rad_gen.py --subtools ic_3d --input_config_path unit_tests/inputs/ic_3d/3D_ic_explore.yaml --pdn_modeling
