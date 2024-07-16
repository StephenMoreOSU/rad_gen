Examples (How to Run)
============================


All examples shown here will have an equivalent test (using pytest) to perform the same action and verify the results. 
If you want to ensure your repo and environment have been setup correctly its strongly reccomended to run all pytests with the following command.

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ # -vv is for very verbose and -s captures stdout
   $ # List all tests
   $ pytests --collect-only tests
   $ # Runs all tests
   $ pytests -vv -s tests


ALU ASIC Flow Example
--------------------------------


ALU Clock Frequency Sweep
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This example demonstrates how a user can sweep an ALU across a range of target clock frequencies specified in a configuration file and run a hammer based asic flow for one of the sweep data points. 

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py --override_outputs --project_name alu --subtools asic_dse --sweep_conf_fpath tests/data/alu_vlsi_sweep/inputs/alu_sweep.yml


**Corresponding pytest**

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
      --flow_conf_fpaths tests/data/asic_dse/cad_tools/cadence_tools.yml tests/data/asic_dse/pdks/asap7.yml projects/alu/configs/gen/alu_base__period_0ns__core_util_0.7__effort_standard.json \
      --tool_env_conf_fpaths tests/data/asic_dse/env.yml \ 
      --common_asic_flow.flow_stages.par.run \
      --common_asic_flow.flow_stages.pt.run \
      --common_asic_flow.flow_stages.syn.run
.. 
   Notice how some of the command line arguments are specified hierarchically. RAD-Gen supports many different ways for users to provide configuration parameters.

**Corresponding pytest**

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py::test_alu_sw_pt_asic_flow

It can be useful to breakdown some of the cli arguments to better understand what the tool is doing.
More information about each one of these commands/configurations can be found in the :ref:`ASIC-DSE` section of the documentation.

At the end of the flow you should get an output report that looks something like the below: 

.. code-block:: bash

    # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------
    #  Target Freq  |    Slack     |    Delay     |  Timing SRC  |Top Level Inst|  Total Area  |   Area SRC   | Total Power  |  Power SRC   |   GDS Area   
    # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------
    #      0 ns     |   -356.45    |    357.45    |      pt      |   alu_ver    |   1743.768   |     par      |    0.0609    |      pt      |  341.194428  
    # --------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+-------------- 

This is a summary of the results of the flow. There will be one of these summaries printed for each flow stage (synthesis, place & route, timing, power, etc).
It has sections for PPA, `The parameter that was swept (Target Freq in this case)`, and design information. 
There are also sections for what stage of the ASIC flow the PPA results come from (see Area/Timing/Power SRC). 

SRAM Generator Example
--------------------------------

When using open source PDKs, it is common to not have a memory compiler capable of generating high quality SRAMs for a design. 
If one were to run a design that infers memory with its behavioral HDL through ASIC synthesis tools, the memory would usually mapped to flip flops. 
For larger memories, mapping to flip flops would result in siginificantly more area and may lead to incorrect conclusions about the design.
Because RAD-Gen aims to be a higher level tool to get PPA estimates at various process technologies, it's important to be able to at least get a reasonable idea of the PPA cost of SRAMs.

For a user defined SRAM (the SRAM a user would like to insantiate in thier design) RAD-Gen will look at all available SRAM macros in a pdk,
try to find an optimized combination of such macros to meet the user defined SRAM requirements, and then stitch the primative macros together using muxing & decoding logic to create the user defined SRAM.
This will result in a suboptimal SRAM compared to that which may come out of a dedicated SRAM compiler, yet it will be a reasonable estimate of the PPA cost of the SRAM.

To run the SRAM generator for a range of SRAM widths, depths, and read write ports we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ 

**Corresponding pytest**

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_sram_gen.py::test_sram_gen

SRAM Single Macro ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After running the SRAM generation sweep, required input files are created to run SRAMs either as a single macro or as a stitched SRAM.

For this example we are using a macro with 2 read/write ports, a depth of 128 words and 32 bits per word.

To run a single macro SRAM through an ASIC flow we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py \
      --manual_obj_dir \
      tests/data/sram_gen/outputs/SRAM2RW128x32_wrapper \
      --project_name \
      sram \
      --subtools \
      asic_dse \
      --compile_results \
      --flow_conf_fpaths tests/data/asic_dse/cad_tools/cadence_tools.yml tests/data/asic_dse/pdks/asap7.yml shared_resources/sram_lib/configs/gen/sram_SRAM2RW128x32.json \
      --tool_env_conf_fpaths tests/data/asic_dse/env.yml \
      --common_asic_flow.flow_stages.par.run \
      --common_asic_flow.flow_stages.pt.run \
      --common_asic_flow.flow_stages.sram.run \
      --common_asic_flow.flow_stages.syn.run                                                                                                                                    


**Corresponding pytest**

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_sram_gen.py::test_single_macro_asic_flow


SRAM Stitched Macro ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For this example we are running a stitched SRAM with 2 RW ports, 512 words, and 256 bits per word.

To run a stitched SRAM through an asic flow we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py \
      --manual_obj_dir tests/data/sram_gen/outputs/sram_macro_map_2x256x512 \
      --project_name sram \
      --subtools asic_dse \
      --compile_results \
      --flow_conf_fpaths tests/data/asic_dse/cad_tools/cadence_tools.yml tests/data/asic_dse/pdks/asap7.yml shared_resources/sram_lib/configs/gen/sram_config_sram_macro_map_2x256x512.json \
      --tool_env_conf_fpathstests/data/asic_dse/env.yml \
      --common_asic_flow.flow_stages.par.run \
      --common_asic_flow.flow_stages.pt.run \
      --common_asic_flow.flow_stages.sram.run \
      --common_asic_flow.flow_stages.syn.run

**Corresponding pytest**

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_sram_gen.py::test_stitched_sram_asic_flow


Network-on-Chip (NoC) RTL Parameter Sweep Example
------------------------------------------------------------------------

This demonstrates how users can sweep NoC RTL parameters and run one of the genenerated sweep points through an ASIC flow.
This particular functionality is useful, as in the RAD-Sim tool users will be modifying NoC and finding the configuration candidates that could work for thier RAD architecture and application(s).

When trying to sweep RTL parameters on a design like the example NoC, `from here <https://stacks.stanford.edu/file/druid:wr368td5072/thesis-augmented.pdf>`_.
it can be difficult to modify the parameters we are interested for many sweep points as manually editing an HDL header file can be time consuming and error prone.

RAD-Gen's (imperfect) solution to this is for users to provide thier desired value for each RTL parameter at each sweep point.
For parameters with dependencies on others (like the number of virtual channels being dependant on the NoC topology) users will
have to calculate the values that the dependancies should have to get downstream desired value.

For more detail on this lets go over a configuration file one would use to sweep NoC RTL parameters.

.. code-block:: yaml

   # shared env configs for all sweeps
   tool_env_conf_fpaths: [ ${RAD_GEN_HOME}/tests/data/asic_dse/env.yml]
   flow_conf_fpaths: [ ${RAD_GEN_HOME}/tests/data/asic_dse/pdks/asap7.yml, ${RAD_GEN_HOME}/tests/data/asic_dse/cad_tools/cadence_tools.yml]

   # base config is the hammer config file which is used as a template for designs which will be swept over
   # output configs currently written to same directory to the base_config_path
   base_config_path: ${RAD_GEN_HOME}/tests/data/asic_dse/dummy/dummy_base.yml
   # These two args are required for each run of hammer flow
   top_lvl_module: router_wrap_bk
   # This path contains all RTL except the parameters.v file which will be swept over
   hdl_dpath: ${RAD_GEN_HOME}/tests/data/noc_rtl_sweep/inputs/rtl/src
   type: rtl
   # Number of parallel asic flow threads being run concurrently Ex. [syn -> par, syn -> par]
   flow_threads: 2
   rtl_params:
   # Path to file containing parameters which we will manipulate to propegate desired values to other parameters
   base_header_fpath: ${RAD_GEN_HOME}/tests/data/noc_rtl_sweep/inputs/rtl/parameters.v
   sweep:
      {
         # In the parameters we set the number of message classes to be equal to the number of vcs we want
         # If parameters can be directly assigned a value they can just have lists
         ################### THESE SETTINGS WILL RECREATE RESULTS IN FPL'23 PAPER ###################
         num_vcs:
         {
            # These are the values we want the variable to be swept over
            "vals": [5, 5, 5],
            "num_message_classes": [5, 5, 5],
            "buffer_size": [20, 40, 80],
            "num_nodes_per_router": [1, 1, 1],
            "num_dimensions": [2, 2, 2],
            "flit_data_width": [124, 196, 342]
         },
         # We use these variables to print out the parsed values for these parameters to make sure the above settings do what we want 
         num_ports: [],
         flit_data_width: [],
         buffer_size: []
      }

The fields in the ``sweep`` dict are lists of sweep points to be generated. In this case we want to set the number of virtual channels stored in the ``num_vcs`` parameter to 5.
Looking over the ``router_wrap_bk.v`` HDL for a NoC router, we can see the following ``localparam`` definitions:

.. code-block:: verilog

   // total number of packet classes
   localparam num_packet_classes = num_message_classes * num_resource_classes;
   
   // number of VCs
   localparam num_vcs = num_packet_classes * num_vcs_per_class;

``num_vcs`` depends on ``num_message_classes`` and ``num_vcs_per_class``. In this case, we are setting ``num_vcs`` to 5, so we need to set ``num_message_classes`` to 5 and ``num_vcs_per_class`` to 1.
The ``num_vcs_per_class`` param: using the default parameters will calculate to 1, so we only need to set ``num_message_classes``.

The other parameter values (i.e, ``buffer_size``, ``flit_data_width``, etc) don't have dependancies so they can be set directly. 


RAD-Gen uses these values provided to generate a new ``parameters.v`` file for each sweep point. 
To ensure that these parameters are actually correct, saving the long runtime of an ASIC flow, RAD-Gen evaluates the values of all RTL parameters & localparams in the ``router_wrap_bk.v`` file and prints them to the console.

The ``vals`` field in the ``num_vcs`` dict is a list of values that ``num_vcs`` should be for each sweep point.
If RAD-Gen evaluates the params and finds that ``num_vcs`` is not equal to the value in the ``vals`` list, it will error out and exit. 


NoC RTL Parameter Sweep
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To generate NoC RTL parameter headers + config files for each sweep point.
Sweep points used are the same ones evaluated in `this FPL'23 paper <https://ieeexplore.ieee.org/document/10296237>`_.

Command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py \
      --override_outputs \
      --project_name NoC \
      --subtools asic_dse \
      --sweep_conf_fpath tests/data/noc_rtl_sweep/inputs/noc_sweep.yml

**Corresponding pytest**


.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_noc_rtl_sweep::test_noc_rtl_sweep



NoC RTL Sweep Point ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After generation of sweep points we can run them through the asic flow.
To run a NoC RTL sweep point through an ASIC flow we will use the below command:


.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py \
      --manual_obj_dir tests/data/noc_rtl_sweep/outputs/router_wrap_bk \
      --project_name \
      NoC \
      --subtools \
      asic_dse \
      --compile_results \
      --flow_conf_fpathstests/data/asic_dse/cad_tools/cadence_tools.yml tests/data/asic_dse/pdks/asap7.yml \  
      projects/NoC/configs/gen/dummy_base_num_message_classes_5_buffer_size_20_num_nodes_per_router_1_num_dimensions_2_flit_data_width_124_num_vcs_5.json \
      --tool_env_conf_fpathstests/data/asic_dse/env.yml \
      --common_asic_flow.flow_stages.par.run \
      --common_asic_flow.flow_stages.pt.run \
      --common_asic_flow.flow_stages.syn.run \
      --common_asic_flow.hdl_pathprojects/NoC/rtl/src \
      --common_asic_flow.top_lvl_module router_wrap_bk



COFFE Stratix IV FPGA Fabric Example
----------------------------------------------------------------

We will use the COFFE subtool in RAD-Gen to size a FPGA fabric using the Free45 process. 
To model commercial architectures with more complex routing architectures,
we need to first parse its routing-resource-graph (RRG) generated from VPR and generate statistics about the circuit / loading information in the fabric.

Parsing Stratix IV RRG
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To parse an existing RRG xml file we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 src/common/rr_parse.py \
      --rr_xml_fpath tests/data/stratix_iv/inputs/rr_graph_ep4sgx110.xml \
      --out_dpath tests/data/stratix_iv/outputs/rr_graph_ep4sgx110 \
      --generate_plots
   
The fpga fabric statistics are generated in the `out_dpath` directory, along with plots.
Those interested should look here for detailed fabric loading information.

**Corresponding pytest**

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_stratix_iv.py::test_stratix_iv_rrg_parse



Running Stratix IV through COFFE Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To perform automatic transistor sizing on a Stratix IV like architecture using the Free45 process we will use the below command:

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ python3 rad_gen.py \
      --override_outputs \
      --project_name \
      stratix_iv \
      --subtools coffe \
      --checkpoint_dpaths tests/data/stratix_iv/inputs/checkpoints/part1 tests/data/stratix_iv/inputs/checkpoints/part2 \
      --delay_opt_weight 2 \
      --fpga_arch_conf_path tests/data/stratix_iv/inputs/stratix_iv_rrg.yml \
      --max_iterations 1 \
      --rrg_data_dpath tests/data/stratix_iv/inputs/rr_graph_ep4sgx110

**Corresponding pytest**
   .. code-block:: bash

      $ # from <RAD_GEN_HOME>
      $ pytest -vv -s tests/test_stratix_iv.py::test_stratix_iv
   

.. COFFE FPGA Fabric w/ALU hardblock Flow Example
.. ----------------------------------------------------------------

.. We will use the COFFE subtool in RAD-Gen to size a 7nm FPGA fabric with an ALU hardblock. 
.. COFFE will perform transistor sizing for fpga custom circuit logic and muxing required to interact with the ALU hardblock. 
.. The hardblock will be ran through a hammer based asic flow using ASAP7.

.. .. code-block:: bash

..    $ python3 rad_gen.py --subtools coffe --max_iterations 1 --fpga_arch_conf_path unit_tests/inputs/coffe/finfet_7nm_fabric_w_hbs/finfet_7nm_fabric_w_hbs.yml --hb_flows_conf_path unit_tests/inputs/coffe/finfet_7nm_fabric_w_hbs/hb_flows.yml


.. IC 3D Flow Example
.. ----------------------------------------------------------------

.. The below example calls the IC_3D subtool, the flags determine if buffer DSE, PDN modeling, or other options are performed.

.. .. code-block:: bash

..    $ python3 rad_gen.py --subtools ic_3d --input_config_path unit_tests/inputs/ic_3d/3D_ic_explore.yaml --buffer_dse
..    $ # to run PDN modeling replace the --buffer_dse flag with the --pdn_modeling flag as shown below:
..    $ python3 rad_gen.py --subtools ic_3d --input_config_path unit_tests/inputs/ic_3d/3D_ic_explore.yaml --pdn_modeling
