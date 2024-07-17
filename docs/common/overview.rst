..    include:: <isonum.txt>

Overview
----------------------------------------------------------

RAD-Gen offers flexible user configuration of tools and provides a common interface for users to pass in thier data and control input parameters for the various modes of operation.

At the highest level, a user can provide either traditional command line (CLI) arguments and/or a ``top_config_fpath`` key to a YAML / JSON configuration file path.

Each group of command line arguments matches directly with a data structure specified in ``src/common/data_structs.py``.

**Examples:**

* ``RadGenCLI`` |rarr| ``Common``
* ``AsicDSECLI`` |rarr| ``AsicDSE``
* ``CoffeCLI`` |rarr| ``Coffe``
* ``Ic3dCLI`` |rarr| ``Ic3d``

Format of CLI args + ``top_config_fpath`` file
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

From ``src/common/data_structs.py::Common``:

.. code-block:: python
    
    @dataclass
    class Common:
        # ...
        just_config_init: bool = None # flag to determine if the invocation of RAD Gen will just initialze data structures and not run any tools.
        override_outputs: bool = False # If true will override any files which already exist in the output directory
        manual_obj_dir: str = None # If set will use this as the object directory for the current run
        # ...

In the above subset of fields from the ``Common`` data struct we can observe two things:
    * The datatype of each field is specified
    * The ``default_factory`` attribute of each field has an initial value being passed to the dataclass. Factory defaults are convenient way to set the 'inactive' state for a dataclass.

Corresponding ``rg_top_lvl_conf.yml``:

.. code-block:: yaml

    # ...
    common:
        just_config_init: True
        override_outputs: True
        manual_obj_dir: path/to/obj_dir
    # ...

Corresponding CLI args from ``src/common/data_structs.py::RadGenCLI``:

.. code-block:: python
    
    @dataclass
    class RadGenCLI(ParentCLI):
        # ...
        GeneralCLI(key = "override_outputs", shortcut = "-l", datatype = bool, action = "store_true", help_msg = "Uses latest obj / work dir / file paths found in the respective output dirs, overriding existing files"),
        GeneralCLI(key = "manual_obj_dir", shortcut = "-o", datatype = str, help_msg = "Uses user specified obj dir"),
        GeneralCLI(key = "just_config_init", datatype = bool, action = "store_true", help_msg = "Flag to return initialized data structures for whatever subtool is used, without running anything")
        # ...


One can see that each of the fields in the ``Common`` struct has corresponding keys in the ``rg_top_lvl_conf.yml`` file and command line arguments in the ``RadGenCLI`` struct.
This is the general idea of keeping everything consisent in terms of keys, while also providing multiple entry points for the user to provide data.

Hierarchically Defined Parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For the flat case, the above explanation is sufficient. However, data structures are often nested and have multiple levels of hierarchy.
Let's go over a more complex example with the "asic_dse" subtool.

**Hierarchically defined parameters can be passed in as follows:**

Focusing in on the ``CommonAsicFlow`` data struct contained in ``AsicDSE``, the main struct used for "asic_dse" subtool.

From ``src/common/data_structs.py::AsicDSE``:

.. code-block:: python
    
    @dataclass
    class AsicDSE:
        # ...
        common_asic_flow: CommonAsicFlow = None # common asic flow settings for all designs
        # ...

From ``src/common/data_structs.py::CommonAsicFlow``:

.. code-block:: python

    @dataclass
    class CommonAsicFlow:
        # ...
        flow_stages: FlowStages = field(
            default_factory = lambda: FlowStages() # flow stages being run 
        )
        # ...

From ``src/common/data_structs.py::FlowStages``:

.. code-block:: python

    @dataclass
    class FlowStages:
        # ...
        syn: FlowStage = field(
            default_factory = lambda: FlowStage(
                tag = "syn", run = False, tool = "cadence")
        )
        par: FlowStage = field(
            default_factory = lambda: FlowStage(
                tag = "par", run = False, tool = "cadence")
        )
        pt: FlowStage = field(
            default_factory = lambda: FlowStage(
                tag = "pt", run = False, tool = "synopsys")
        )
        # ... 

From ``src/common/data_structs.py::CommonAsicFlow``:

.. code-block:: python

    @dataclass
    class FlowStages:
        # ...
        run: bool = None # Should this stage be run?
        # ...

Now using the above struct definitions, how do we set a field in the struct ``asic_dse.common_asic_flow.flow_stages.syn.run`` to run only the synthesis stage in a standard cell ASIC flow?
The inline code block in the previous sentence is the way to access such a parameter in python syntax, so for simplicity hierarchical CLI params are specified in equivalent syntax.

The hierarhical CLI arg definitions are defined in ``src/common/data_structs.py::AsicDSECLI``:

.. code-block:: python
    
    @dataclass
    AsicDseCLI(ParentCLI):
        # ...
        GeneralCLI(key = "common_asic_flow.flow_stages.sram.run", shortcut = "-sram", datatype = bool, action = "store_true", help_msg = "Flag that must be provided if sram macros exist in design (ASIC-DSE)"),
        GeneralCLI(key = "common_asic_flow.flow_stages.syn.run", shortcut = "-syn", datatype = bool, action = "store_true", help_msg = "Flag to run synthesis"),
        GeneralCLI(key = "common_asic_flow.flow_stages.par.run", shortcut = "-par", datatype = bool, action = "store_true", help_msg = "Flag to run place & route"),
        GeneralCLI(key = "common_asic_flow.flow_stages.pt.run", shortcut = "-pt", datatype = bool, action = "store_true", help_msg = "Flag to run primetime (timing & power)"),


We can then manually change the values in this deeply nested struct by passing the data structure hierarhical path as a CLI arg.  

.. code-block:: bash

    $ # To run only synthesis
    $ python3 rad_gen.py --top_config_fpath rg_top_lvl_conf.yml --common_asic_flow.flow_stages.sram.run


Initialization Priority Order
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
With multiple entry points for parameters to be passed in, a priority is required for cases of overlapping values.

**The priority order is as follows:**

1. Command line arguments
2. top level config file
3. CLI default values
4. Dataclass ``default_factory`` values

Having such a priority order adds complexity but provides useful functionality for tools using large numbers of user input parameters (most tools in RAD-Gen).

**For Example:**
We may be running the COFFE flow with at a particular process technlogy and many additional FPGA architecture parameters. 
Lets say, for this architecture, we want to evaluate the PPA differences with and without logic block carry chains.
Enablement of carry chains is done with a single parameter. 

We could duplicate our input configuration file we use, and change the line for the carry chain parameter, but this option is not ideal as it requires manual change and duplication of config files.
Instead, if we keep the same base configuration file, and pass in the carry chain parameter as a command line argument, we can easily switch between the two configurations without duplicating files.



.. Walkthrough
.. ----------------------------------------------------------

.. Starting from the top. The ``rad_gen.py`` script is the top level entry point to run RAD-Gen

.. .. code-block:: python

..     # Parse command line arguments
..     args, default_arg_vals = rg_utils.parse_rad_gen_top_cli_args(args)
..     rad_gen_info = rg_utils.init_structs_top(args, default_arg_vals)
..     arg_dict = vars(args)


.. The above lines parse the command line 