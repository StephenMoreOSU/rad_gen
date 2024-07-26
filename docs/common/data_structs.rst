..    include:: <isonum.txt>

Data Structures
#######################################


Top Level
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

RAD-Gen offers flexible user configuration of tools and provides a common interface for users to pass in thier data and control input parameters for the various modes of operation.

At the highest level, a user can provide either convensional command line (CLI) arguments and/or 
a YAML / JSON configuration file (using the ``--top_config_fpath`` CLI key).

CLI / Structs / Tool Invocation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Each group of command line arguments maps directly to a data structure specified in ``src/common/data_structs.py``.
These data structures are responsible for holding all necessary parameters, derived from user inputs, to run the various tools in RAD-Gen.

Command line arguments need to be defined in dedicated structs as they are often used 
to write scripts, invoke other tools, or perform verification.

So to recap, if a user wanted to define a new tool in RAD-Gen's suite they would create the following:

* CLI Struct: e.g. ``MyToolCLI``
* Data Struct: e.g. ``MyTool``
* Initialization Function: e.g. ``init_my_tool_structs(my_tool_conf: dict, common: Common) -> MyTool``
* Invocation: e.g. ``def run_my_tool(my_tool: MyTool)``

.. mermaid::

   graph LR
      A[User Input] --> B[Initalized Struct];
      B --> C[Tool Invocation];
      C --> D[Results] 



In this section, we will focus on the portion of the diagram from ``User Input`` to ``Initalized Struct``.

Current Existing Mappings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* CLI Struct |rarr| Tool Data Struct
* ``RadGenCLI`` |rarr| ``Common``
* ``AsicDseCLI`` |rarr| ``AsicDSE``
* ``CoffeCLI`` |rarr| ``Coffe``
* ``Ic3dCLI`` |rarr| ``Ic3d``



Format of CLI args, structs, and config file(s)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

From ``src/common/data_structs.py::Common``

.. code-block:: python
    
    @dataclass
    class Common:
        # ...
        just_config_init: bool = None # flag to determine if the invocation of RAD Gen will just initialze data structures and not run any tools.
        override_outputs: bool = False # If true will override any files which already exist in the output directory
        manual_obj_dir: str = None # If set will use this as the object directory for the current run
        # ...

.. In the above subset of fields from the ``Common`` data struct we can observe two things:
..     * The datatype of each field is specified
..     * The ``default_factory`` attribute of each field has an initial value being passed to the dataclass. Factory defaults are convenient way to set the 'inactive' state for a dataclass.

Corresponding CLI args from ``src/common/data_structs.py::RadGenCLI``:

.. code-block:: python
    
    @dataclass
    class RadGenCLI(ParentCLI):
        # ...
        GeneralCLI(key = "override_outputs", shortcut = "-l", datatype = bool, action = "store_true", help_msg = "Uses latest obj / work dir / file paths found in the respective output dirs, overriding existing files"),
        GeneralCLI(key = "manual_obj_dir", shortcut = "-o", datatype = str, help_msg = "Uses user specified obj dir"),
        GeneralCLI(key = "just_config_init", datatype = bool, action = "store_true", help_msg = "Flag to return initialized data structures for whatever subtool is used, without running anything")
        # ...


From the above CLI struct we can pass the command line arguments in a familiar way:

.. code-block:: bash

   $ python3 rad_gen.py --subtools <subtool_option> --override_outputs --manual_obj_dir path/to/obj_dir --just_config_init



Corresponding ``rg_top_lvl_conf.yml``

.. code-block:: yaml

    # ...
    common:
        just_config_init: True
        override_outputs: True
        manual_obj_dir: path/to/obj_dir
    # ...


.. This is the general idea of keeping everything consisent in terms of keys, while also providing multiple entry points for the user to provide data.

We can see the corresponding keys across the ``Common`` struct, the ``rg_top_lvl_conf.yml`` file, and command line arguments in the ``RadGenCLI`` struct.
The general idea is to keep naming consistent across all possible user entry points, ideally avoiding confusion.


Hierarchically Defined Parameters
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Data structures are often nested and have multiple levels of hierarchy, so there is additional logic to deal with this.
Let's go over a slightly more complex example with the ``asic_dse`` subtool.

Focusing in on the :class:`common.data_structs.CommonAsicFlow` data struct contained in :class:`common.data_structs.AsicDSE`:

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

With respect to above definitions, lets say we want to set the ``run`` field within ``FlowStages`` at ``asic_dse.common_asic_flow.flow_stages.syn.run`` to run only the synthesis stage in a standard cell ASIC flow.
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


Initialization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
With multiple entry points for parameters to be passed in, a priority is required for cases of overlapping values.



Top Level Priority Order
++++++++++++++++++++++++++++

In order of highest to lowest priority:

1. Command line arguments
2. top level config file
3. CLI default values (defined within CLI structs)

Having such a priority order adds complexity but provides useful functionality for tools using large numbers of user input parameters (most tools in RAD-Gen).

Single Field Example
++++++++++++++++++++++

.. figure:: rg_field_init.png
    :figwidth: 700
    :align: center

    Initialization flow for each field


Once fields have been merged through the priority order, we pass a newly created dictionary into the initialization function for the tool we are running.


Init Function Walkthrough
++++++++++++++++++++++++++++

Regardless of tool or mode of operation, the first initialization function that is called is :func:`common.utils.init_structs_top`.
Here, the arguments derived from the CLI, config file, and CLI defaults are merged into a single dictionary and passed to the initialization function of the tool being run.


We will continue the walkthrough using ``asic_dse`` subtool as an example.


For ``asic_dse`` we have the following:

* CLI Struct: :class:`common.data_structs.AsicDseCLI`
* Data Struct: :class:`common.data_structs.AsicDSE`
* Initialization Function: :func:`common.utils.init_asic_dse_structs`
* Invocation: :func:`asic_dse.run_asic_dse`


:class:`common.data_structs.AsicDSE`:

.. code-block:: python

    @dataclass
    class AsicDSE:
        common: Common # common settings for RAD Gen
        mode: AsicDseMode # mode in which asic_dse is running
        stdcell_lib: StdCellLib # technology information for the design
        scripts: ScriptInfo = None # script information for asic_dse
        sweep_conf_fpath: str = None # path to sweep configuration file containing design parameters to sweep
        result_search_path: str = None # path which will look for various output obj directories to parse results from
        common_asic_flow: CommonAsicFlow = None # common asic flow settings for all designs
        asic_flow_settings: HammerFlow = None # asic flow settings for single design
        custom_asic_flow_settings: Dict[str, Any] = None # custom asic flow settings
        design_sweep_info: DesignSweepInfo = None # sweep specific information for a single design
        sram_compiler_settings: SRAMCompilerSettings = None # paths related to SRAM compiler outputs


All of the above fields should be initialized to the values required for the mode of operation specified by the user. 
The struct containing mode of operation info is :class:`common.data_structs.AsicDseMode`.

The typical way to intialize a struct field is via the :func:`common.utils.init_dataclass` function. 

Using the ``mode`` field as an example, it would be initialized as follows within :func:`common.utils.init_asic_dse_structs`:

.. code-block:: python

    def init_asic_dse_structs(asic_dse_conf: Dict[str, Any], common: rg_ds.Common) -> rg_ds.AsicDSE:
        # ...
        sweep_conf_valid: bool = asic_dse_conf["sweep_conf_fpath"] != None
        flow_conf_valid: bool = asic_dse_conf["flow_conf_fpaths"] != None

        asic_dse_mode: rg_ds.AsicDseMode = init_dataclass(
            rg_ds.AsicDseMode, 
            strip_hier(asic_dse_conf, strip_tag="mode"),
        )
        # Perform post init operations to set fields requiring external / internal dependancies
        asic_dse_mode.init(
            sweep_conf_valid,
            compile_results_flag,
        )
        asic_dse_mode.vlsi.init(
            sweep_conf_valid,
            flow_conf_valid,
            top_lvl_valid,
        )
        # ...


We first call :func:`common.utils.init_dataclass` to initialize the ``mode`` field, then call the ``init`` function within the ``mode`` field to set any fields that require additional information to be derived from the user input.

It would be clean if we could simply directly pass the hierarchically defined dictionary key value pairs to the struct, 
however, during initialization there are a number of fields that have to be derived from the user input, and change depending on the mode of operation or other parameters.

An example of this behavior can be seen in the ``init`` function within :class:`common.data_structs.AsicDseMode`.

.. code-block:: python

    def init(
            self,
            sweep_conf_valid: bool, 
            compile_results: bool,
    ) -> None:
        """
            Args:
                sweep_conf_valid: from higher level init function, are preconditions met to run in sweep mode?
                compile_results: is the compile_results flag set? 
        """
        # If in sweep mode
        if sweep_conf_valid:
            # If result flat not set we generate sweeps
            if not compile_results:
                self.sweep_gen = True
                self.result_parse = False
            else:
                self.sweep_gen = False
                self.result_parse = True


Which takes control signals derived from user input and sets the ``sweep_gen`` and ``result_parse`` fields accordingly.

.. warning:: 
    Users CANNOT define pass in parameters that are initialized within ``init`` function. 

    For example, if a user were to pass in the following CLI arg, an error would be thrown.

    .. code-block:: bash

        $ python3 rad_gen.py --subtools asic_dse --mode.sweep_gen


Internal Init Priority Order
++++++++++++++++++++++++++++++

We can define a second stage of priority by which fields are initialized from within a tools initialization function (in previous example :func:`common.utils.init_asic_dse_structs`).

In order of highest to lowest priority:

1. Struct internal ``init`` functions
1. User Params Merged Dict
2. Field ``default_factory``

Priority examples:

* Struct internal ``init`` functions : e.g. :func:`common.data_structs.AsicDseMode.init`
* User Params Merged Dict: e.g. ``asic_dse_conf``
* Field ``default_factory``: e.g.  ``vlsi: VLSIMode = field(default_factory = VLSIMode)``

Note top two priorities both marked with 1. to denote they are of equal priority and mutually exclusive.































**Use Case:**

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