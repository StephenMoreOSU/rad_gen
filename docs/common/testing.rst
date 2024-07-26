..    include:: <isonum.txt>

Testing
----------------------

This page is a guide on testing in RAD-Gen.
Tests uses the ``pytest`` framework, which is explained in detail at the `pytest documentation <https://docs.pytest.org/en/stable/>`_.


Usage
^^^^^^^^^^^^^^^^^^^^^^^^^

In brief, pytest can be invoked in the following ways (from root of the repo):

.. code-block:: bash

   $ # From <RAD_GEN_HOME>
   $ # Runs all tests in a particular directory
   $ pytest tests/
   $ # Runs all tests in a particular file
   $ pytest tests/test_alu_vlsi_sweep.py
   $ # Runs a specific test in a file
   $ pytest tests/test_alu_vlsi_sweep.py::test_alu_vlsi_sweep_gen
   $ # To view all available tests in a directory / file use the --collect-only flag
   $ pytest --collect-only tests/
   $ # -vv is for very verbose and -s captures stdout (useful for debugging)
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py
   $ # -m allows us to filter tests based on markers
   $ # Markers can have boolean expressions, below command will run all tests that have both 'parse' and 'init' markers
   $ pytest tests/ -m 'parse and init'

Comprehensive usage of pytest can be found `here <https://docs.pytest.org/en/6.2.x/usage.html>`_.

The following are custom modes specific to RAD-Gen for invoking pytest:

.. code-block:: bash
   
   $ # From <RAD_GEN_HOME>
   $ # Will run test fixtures for any test with 'asic_flow' tag, but will NOT run the test itself
   $ pytest tests/ --fixtures-only -m 'asic_flow'



Code Structure
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: text

   tests
   ├── conftest.py
   ├── test_alu_vlsi_sweep.py
   ├── test_sram_gen.py
   ├── test_noc_rtl_sweep.py
   ├── test_stratix_iv.py
   ├── test_stratix_10.py
   ├── test_ic_3d.py
   ├── common
   │   ├── common.py
   ├── data
   │   ├── alu_vlsi_sweep
   │   │   ├── fixtures
   │   │   ├── golden_results
   │   │   ├── inputs
   │   │   └── outputs
   │   ├── sram_gen
   │   │   ├── fixtures
   │   │   ├── golden_results
   │   │   ├── inputs
   │   │   └── outputs
   │   ├── noc_rtl_sweep
   │   │   ├── fixtures
   │   │   ├── golden_results
   │   │   ├── inputs
   │   │   └── outputs
   │   ├── stratix_iv
   │   │   ├── fixtures
   │   │   ├── golden_results
   │   │   ├── inputs
   │   │   └── outputs
   │   ├── stratix_10
   │   │   ├── fixtures
   │   │   ├── golden_results
   │   │   ├── inputs
   │   │   └── outputs
   │   ├── ic_3d
   │   │   ├── fixtures
   │   │   ├── golden_results
   │   │   ├── inputs
   │   │   └── outputs
   │   ├── env
   │   │   └── golden_results
   │   ├── meta
   │   │   └── test_fixture_mapping.json
   ├── env_test.py
   └── scripts
       ├── pytest_wrapper.py
       ├── rec_csvs_print.sh
       └── update_golden_results.py

Top Level Python Files
+++++++++++++++++++++++++

* ``conftest.py``: Any pytest functionality that should be applied across all tests should be defined here. This includes common fixtures, custom hooks, or changes to the way pytest executes.

Any file that exists in the top level of the ``tests/`` directory is a test file. 
They must be named in the convension ``test_*.py``.

* ``test_alu_vlsi_sweep.py``: ALU VLSI Sweep + stdcell flow 
* ``test_sram_gen.py``: SRAM generation + stdcell flow
* ``test_noc_rtl_sweep.py``: NoC RTL Sweep + stdcell flow
* ``test_stratix_iv.py``: COFFE FPGA fabric custom transistor sizing flow for Altera Stratix IV architecture
* ``test_stratix_10.py``: COFFE FPGA fabric custom transistor sizing flow for Altera Stratix 10 architecture
* ``test_ic_3d.py``: 3D Die-to-die drivers + PDN flows

For each top level test file above, there exists a corresponding directory in the ``tests/data``.
Naming convension is the same as the file name, but without the ``test_`` prefix.

* e.g. test_alu_vlsi_sweep.py |rarr| tests/data/alu_vlsi_sweep

Per-test Directory Structure
++++++++++++++++++++++++++++++


.. code-block:: text

   <test_name>
   ├── fixtures
   ├── golden_results
   ├── inputs
   └── outputs

* ``fixtures``: Contains output ``.json`` files generated from running test fixtures
  - These are used for ``init`` tests to verify that data structures were initialized correctly
* ``golden_results``: Contains golden results used to compare against test outputs and determine if the test passed
* ``inputs``: Contains input files used to run the test
* ``outputs``: Contains any outputs generated from test invocation

.. code-block:: text

    golden_results
    ├── <test_name>
    └── ...

* ``<test_name>``: Contains golden results for a particular test (using the standard naming convension)
  - e.g. ``test_alu_vlsi_sweep.py`` |rarr| ``golden_results/alu_vlsi_sweep``

Each \<test_name\> contains golden results to compare against, 
yet as different modes of RAD-Gen generate results in different formats the structure of the golden results directory will vary.

Golden result format types can be found at sections:

* :ref:`Configuration Initialization<CONF_INIT>`
* :ref:`ASIC stdcell flow<ASIC_STDCELL>`
.. * :ref:`COFFE<COFFE>`



Updating Golden Results
^^^^^^^^^^^^^^^^^^^^^^^^^^^

A common situation we may run into is making changes to the codebase and expecting an answer different than what exists in the golden results.
Of course when a test compares its new answers to these old golden results it will fail.

Once code changes have been made and we are confident that the new results are correct, the golden results can be updated.
This can be done via a script to prevent tedium and accidental errors.

The script is located at ``tests/scripts/update_golden_results.py`` and can be invoked as follows:

+++++++++++++++++++++++
Usage
+++++++++++++++++++++++

.. code-block:: bash 

    $ # From <RAD_GEN_HOME>
    $ # There are multiple run options depending on the type of golden results and file structure of the test which we are updating.
    $ # We can use the -t and -m flags for tests and markers respectively to filter which tests we want to update golden values for
    $ # Below command would perform the <run_option> for tests in test_alu_vlsi_sweep.py that have the 'asic_flow' marker
    $ python tests/scripts/update_golden_results.py <run_option> -t test_alu_vlsi_sweep.py -m 'asic_flow'

**Configuration Initialization**

How to override golden results for tests of :ref:`CONF_INIT` type.
Ideally there should be an ``init`` test for each existing (non ``init``) test for full coverage of data struct initialization.


.. code-block:: bash 

    $ # From <RAD_GEN_HOME>
    $ # To update conf init related golden results
    $ python tests/scripts/update_golden_results.py --struct_init


.. _ASIC_STDCELL: 
**ASIC Standard Cell Flow**

.. code-block:: bash

    $ # From <RAD_GEN_HOME>
    $ # To update conf init related golden results
    $ python tests/scripts/update_golden_results.py --asic_flow



.. _CONF_INIT:
Configuration Initialization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For every test A, in all ``test_*.py`` files there should be a corresponding test B which, w.r.t the test A's user provided input arguments, 
will verify that data structures were initialized correctly for the particular mode of operation. 

These exist to provide a meathod for developers to change the way in which data structures are initialized, and verify that such changes did not break various modes of the tool.

Test Standards
++++++++++++++++

* Config initialization tests should have the string ``_conf_init`` in function definitions.
* Marked with ``init``

Parsing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Many modes of operation in RAD-Gen will generate results and output them to ``*.csv`` or ``*.json`` files.
A useful test to verify that these files contain the expected results is to simply parse them and compare against golden values.
This is the purpose of parsing tests, and there should be a parse test counterpart for each test that generates output files.

Test Standards
++++++++++++++++

* Marked with ``parse``


If not explictly mentioned all below stdcell flow tests use the following:

* synthesis tool : ``genus``
* place and route tool : ``innovus``
* timing and power tool : ``primetime``
* GDS transformation tool : ``gdstk``
* PDK : ``asap7``
* Run mode: ``hammer``


ALU VLSI Sweep + Stdcell ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

src: ``tests/test_alu_vlsi_sweep.py``

This file contains tests to:

1. Generate config files for a few different VLSI related parameters with an ALU design
2. Run the stdcell flow


Golden Results
+++++++++++++++++

Generated by test command(s):

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ # Run the test
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py::test_alu_sw_pt_asic_flow
   $ # If results already exist, just run parse test
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py::test_alu_sw_pt_parse


The sweep point that is generated and run has the following VLSI parameters:

* ``period``: 0 ns
* ``core_util``: 0.7
* ``effort``: standard

Resulting in following golden results:

.. code-block:: text

   +--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+
   | Target Freq  |    Slack     |    Delay     |  Timing SRC  |Top Level Inst|  Total Area  |   Area SRC   | Total Power  |  Power SRC   |   GDS Area   |
   +--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+
   |     0 ns     |   -356.45    |    357.45    |      pt      |   alu_ver    |   1743.768   |     par      |    0.0609    |      pt      |  341.194428  |
   +--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+ 

SRAM Generation + Stdcell ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

src: ``tests/test_sram_gen.py``

This file contains tests to:

1. Generate SRAM RTL + configuration files to run range of single + stitched macro SRAMs through stdcell flow.
2. Run the stdcell flow for a single Macro SRAM
3. Run the stdcell flow for a stitched Macro SRAM


Golden Results
+++++++++++++++++

Generated by test command(s):

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ # Run the single macro test
   $ pytest -vv -s tests/test_sram_gen.py::test_single_macro_asic_flow
   $ # If results already exist, just run parse test
   $ pytest -vv -s tests/test_alu_vlsi_sweep.py::test_single_macro_parse
   $ # Run the stitched macro test
   $ pytest -vv -s tests/test_sram_gen.py::test_stitched_sram_asic_flow
   $ # If results already exist, just run parse test
   $ pytest -vv -s tests/test_sram_gen.py::test_stitched_sram_parse

For the single macro SRAM test, the generated SRAM has the following parameters:

* read / write ports: 2
* depth: 128 words
* width: 32 bits per word

Resulting in following golden results:

.. code-block:: text

   +---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+
   |     Target Freq     |        Slack        |        Delay        |     Timing SRC      |   Top Level Inst    |     Total Area      |      Area SRC       |     Total Power     |      Power SRC      |      GDS Area       |     SRAM Macros     |   SRAM LEF Areas    |
   +---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+
   |       0.0 ns        |       -130.03       |       131.03        |         pt          |SRAM2RW128x32_wrapper|      4621.625       |         par         |       0.0786        |         pt          |     2192.819206     |    SRAM2RW128x32    | 3715.3320959999996  |
   +---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+---------------------+


For the stitched SRAM test, the generated SRAM has the following parameters:

* read / write ports: 2
* depth: 512 words
* width: 256 bits per word

.. code-block:: text

   +------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+
   |      Target Freq       |         Slack          |         Delay          |       Timing SRC       |     Top Level Inst     |       Total Area       |        Area SRC        |      Total Power       |       Power SRC        |        GDS Area        |      SRAM Macros       |     SRAM LEF Areas     |
   +------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+
   |         0.0 ns         |        -213.95         |         214.95         |           pt           |sram_macro_map_2x256x512|       137720.755       |          par           |         1.8137         |           pt           |      32971.907365      |     SRAM2RW128x32      |   3715.3320959999996   |
   +------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+------------------------+


NoC RTL Sweep + Stdcell ASIC Flow
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

src: ``tests/test_noc_rtl_sweep.py``

This file contains tests to:

1. Generate RTL + configuration files to run NoC routers with a range of RTL parameters through stdcell flow.
2. Run the stdcell flow for a single NoC router

Golden Results
+++++++++++++++++

Generated by test command(s):

.. code-block:: bash

   $ # from <RAD_GEN_HOME>
   $ pytest -vv -s tests/test_noc_rtl_sweep.py::test_noc_sw_pt_asic_flow
   $ # If results already exist, just run parse test
   $ pytest -vv -s tests/test_noc_rtl_sweep.py::test_noc_sw_pt_parse

For the NoC router test, the generated NoC router has the following parameters:

* num_vcs: 5
* buffer_size: 20
* flit_data_width: 124 

.. code-block:: text

   +--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+                                                                                                                       
   | Target Freq  |    Slack     |    Delay     |  Timing SRC  |Top Level Inst|  Total Area  |   Area SRC   | Total Power  |  Power SRC   |   GDS Area   |                                                                                                                       
   +--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+                                                                                                                       
   |     0 ns     |   -567.53    |    568.53    |      pt      |router_wrap_bk|  162560.701  |     par      |    1.9456    |      pt      |30582.0793109 |                                                                                                                       
   +--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+--------------+  





