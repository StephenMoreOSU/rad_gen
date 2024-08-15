# This file defines an HSPICE interface class. An object if this class is can be used to 
# run HSPICE jobs and parse the output of those jobs.

import os
import subprocess
import re
from typing import Dict, List
import src.coffe.utils as utils

# All .sp files should be created to use sweep_data.l to set parameters.
HSPICE_DATA_SWEEP_PATH = "sweep_data.l"

# The contents of 
DATA_SWEEP_PATH = "data.txt"


class SpiceInterface(object):
    """
    Defines an HSPICE interface class. 
    An object of this class can be used to run HSPICE jobs and parse the output of those jobs.
    """
    def __init__(self, useNgSpice):
        self.useNgSpice = False
        if useNgSpice:
            self.useNgSpice = True

        # This simulation counter keeps track of number of HSPICE sims performed.
        self.simulation_counter = 0

        return


    def get_num_simulations_performed(self):
        """
        Returns the total number of HSPICE sims performed by this SpiceInterface object.
        """

        return self.simulation_counter


    def _setup_data_sweep_file(self, parameter_dict):
        """
        Create an HSPICE .DATA statement with the data from parameter_dict.
        The .DATA file is hard to read. So, we also write out the parameters to a text file
        in an easy to read format. This makes it easier to debug.
        """
        
        max_items_per_line = 4

        # Get a list of parameter names
        param_list = list(parameter_dict.keys())

        # Write out parameters to a "easy to read format" file (this just helps for debug) 
        data_file = open(DATA_SWEEP_PATH, 'w')
        data_file.write("param".ljust(40) + "value".ljust(20) + "\n")
        dashes = "-"*60
        data_file.write(dashes+ "\n")
        for param in param_list :
            data_file.write(param.ljust(40, '-'))
            for i in range(len(parameter_dict[param])) :
                data_file.write(str(parameter_dict[param][i]).ljust(20))

            data_file.write("\n")
        data_file.close()

        # Write the .DATA HPSICE file. This first part writes out the header.
        hspice_data_file = open(HSPICE_DATA_SWEEP_PATH, 'w')
        hspice_data_file.write(".DATA sweep_data")
        item_counter = 0
        for param_name in param_list:
            if item_counter >= max_items_per_line:
                hspice_data_file.write("\n" + param_name)
                item_counter = 0
            else:
                hspice_data_file.write(" " + param_name)
            item_counter += 1
        hspice_data_file.write("\n")
    
        # Add data for each elements in the lists.
        num_settings = len(parameter_dict[param_list[0]])
        for i in range(num_settings):
            item_counter = 0
            for param_name in param_list:
                if item_counter >= max_items_per_line:
                    hspice_data_file.write(str(parameter_dict[param_name][i]) + "\n")
                    item_counter = 0
                else:
                    hspice_data_file.write(str(parameter_dict[param_name][i]) + " ")
                item_counter += 1
            hspice_data_file.write ("\n")
    
        # Add the footer
        hspice_data_file.write(".ENDDATA")
    
        hspice_data_file.close()
    
        return

    def run_hspice(self, sp_path: str, parameter_dict: Dict[str, List[str]]):
        """
        This function runs HSPICE on the .sp file at 'sp_path' and returns a dictionary that 
        contains the HSPICE measurements.

        'parameter_dict' is a dictionary that contains the sizes of transistors and wire RC. 
        It has the following format:
        parameter_dict = {param1_name: [val1, val2, etc...],
                          param2_name: [val1, val2, etc...],
                          etc...}

        You need to make sure that 'parameter_dict' has a key-value pair for each parameter
        in your HSPICE netlists. Otherwise, the simulation will fail because of missing 
        parameters. That is, only the parameters found in 'parameter_dict' will be given a
        value. 
        
        This is important when we consider the fact that, the 'value' in the key value 
        pair is a list of different parameter values that you want to run HSPICE on.
        The lists must be of the same length for all params in 'parameter_dict' (param1_name's
        list has the same number of elements as param2_name). Here's what is going to happen:
        We will start by setting all the parameters to their 'val1' and we'll run HSPICE. 
        Then, we'll set all the params to 'val2' and we'll run HSPICE. And so on (that's 
        actually not exactly what happens, but you get the idea). So, you can run HSPICE on 
        different transistor size conbinations by adding elements to these lists. Transistor 
        sizing combination i is ALL the vali in the parameter_dict. So, even if you never 
        want to change param1_name, you still need a list (who's elements will all be the 
        same in this case).
        If you only want to run HSPICE for one transistor sizing combination, your lists will
        only have one element (but it still needs to be a list).

        Ok, so 'parameter_dict' contains a key-value pair for each transistor where the 'value'
        is a list of transistor sizes to use. A transistor sizing combination consists of all 
        the elements at a particular index in these lists. You also need to provide a key-value
        (or key-list we could say) for all your wire RC parameters. The wire RC data in the 
        lists corresponds to each transistor sizing combination. You'll need to calculate what
        the wire RC is for a particular transistor sizing combination outside this function 
        though. Here, we'll only set the paramters to the appropriate values. 

        Finally, what we'll return is a dictionary similar to 'parameter_dict' but containing
        all of the of the SPICE measurements. The return value will have this format: 

        measurements = {meas_name1: [value1, value2, value3, etc...], 
                        meas_name2: [value1, value2, value3, etc...],
                        etc...}
        """

        sp_dir = os.path.dirname(sp_path)
        sp_filename = os.path.basename(sp_path)
  
        # Setup the .DATA sweep file with parameters in 'parameter_dict' 
        self._setup_data_sweep_file(parameter_dict)
 
        # Change working dir so that SPICE output files are created in circuit subdirectory
        saved_cwd = os.getcwd()
        os.chdir(sp_dir)
         
        # Creat an output file having the ending .lis
        # Run the SPICE simulation and capture output
        output_filename = sp_filename.rstrip(".sp") + ".lis"
        output_file = open(output_filename, "w")

        hspice_success = False
        hspice_runs = 0

        # HSPICE simulations might fail for some reasons:
        # 1- The input file is incorrect, which would be a bug within COFFE.
        # 2- HSPICE fails to checheck out the license, assuming the license exists, it is likely due
        #    to many instances checking out the license at the same time or license going down temporarly. 
        #    In this case, we check if the ".mt0" exists, if not, we run hspice again. 
        while (not hspice_success) :
            # last I checked the license is available during the night, so we can try to run hspice uncomment below if this is untrue
            #utils.check_for_time()
            subprocess.call(["hspice", '-mt', '8', '-i', sp_filename], stdout=output_file, stderr=output_file)

            # how come this file is closed here, it should be closed only if there is a success
            # since else the call process will write in a closed file
            ##output_file.close()
             
            # HSPICE should print the measurements in a file having the same
            # name as the output file with .mt0 ending
            mt0_path = output_filename.replace(".lis", ".mt0")

            # check that the ".mt0" file is there
            if os.path.isfile(mt0_path) :
                # store the measurments in a dictionary
                spice_measurements = self.parse_mt0(mt0_path)
                # delete results file to avoid confusion in future runs
                os.remove(mt0_path)
                hspice_success = True
                output_file.close()
            # HSPICE failed to run
            else :
                hspice_runs = hspice_runs + 1
                if hspice_runs > 10 :
                    print("----------------------------------------------------------")
                    print("                  HSPICE failed to run                    ")
                    print("----------------------------------------------------------")
                    print("")
                    exit(2)
  
        # Update simulation counter with the number of simulations done by 
        # adding the length of the list of parameter values inside the dictionary
        self.simulation_counter += len(next(iter(parameter_dict.values())))

        # Return to saved cwd
        os.chdir(saved_cwd)
           
        return spice_measurements
    
    def measure_node_replacement(self, main_file, lib_files):
        class circuit:
            """
            This class represent a subcircuit. 
            A subcircuit in spice would look like this:

            .subckt <type> <io1> .... <io#> <parameter1>=<val1> ... <parameter#>=<val#>
            <element1> <io node/internal node>
            ...
            <element#>
            .ends

            self.type is the type of the subcircuit
            self.io contains all io names
            self.components is in the following form
            {<element1> : [<node1>, ... , <node#>, <element1 type>], ...}
            """
            def __init__(self, s):
                if(s == None):
                    self.type = ""
                    self.io = []
                    self.components = {}
                    return
                # set type
                self.type = re.search(r"\.subckt\s+(\w+)", s, re.I).group(1)
                # set io
                io = re.search(rf"\.subckt\s+{self.type}(.*)", s, re.I).group(1)
                self.io = []
                for word in io.split():
                    if not '=' in word:
                        self.io.append(word)
                # set components
                self.components = {}
                lines = s.split('\n')
                # exclude .subckt and .ends
                lines = lines[1:-1]
                for line in lines:
                    line = line.split()
                    new_line = []
                    # parse all words besides parameter settings
                    for word in line:
                        word = word.lower()
                        if not "=" in word:
                            new_line.append(word)
                    # create one component
                    for i, w in enumerate(new_line):
                        w = w.lower()
                        if i == 0:
                            self.components[w] = []
                        else:
                            self.components[new_line[0]].append(w)

        # holds all subcircuits, key is subcircuit type, value is subcircuit data structure
        circuits = {}
        # holds all node indexing in a spice file that could be potentially wrong when converting from hspice to ngspice
        # it is in the format ["<component1>.<component2>....<component#>.<node>", ...]
        querries = []
        # root file, usually ends with .sp
        main_file = open(main_file, 'r')
        main_file = main_file.read()
        # This can also be "[iv]\((.*)\)" but the following works
        querries = re.findall(r"\w\(([^\s]*?)\)", main_file, re.I)
        main_file = main_file.split("\n")
        # the root file has not ios or types, only components, not using the constructor for circuit
        c = circuit(None)
        c.type = "main"
        for line in main_file:
            line = line.split()
            if len(line) == 0: 
                continue
            if line[0][0] == "+" or line[0][0] == "." or line[0][0] == "*":
                continue
            for i, w in enumerate(line):
                w = w.lower()
                if i == 0:
                    c.components[w] = []
                else:
                    if w == "pulse":
                        break
                    c.components[line[0].lower()].append(w)
        circuits["main"] = c
        
        # parse all subcircuits and create circuit class for them
        for file_path in lib_files:
            file = open(file_path, 'r')
            file = file.read()
            circuit_strs = re.findall(r"(\.subckt.*?\.ends)", file, re.IGNORECASE | re.DOTALL)
            for circuit_str in circuit_strs:
                c = circuit(circuit_str)
                circuits[c.type.lower()] = c
        # result is used to hold the strings to be replaced with
        # querries[i] will be replaced by result[i]
        result = []
        # find replacement string for all querries 
        for q in querries:
            original_string = q
            q = q.split(".")
            current_subcircuit_type = "main"
            # subcircuits holds all subcircuits we traced through
            subcircuits = []
            for i, w in enumerate(q):
                w = w.lower()
                cs = circuits[current_subcircuit_type]
                subcircuits.append(cs)
                # last index is not a subcircuit but a node
                if i != len(q)-1:
                    current_subcircuit_type = cs.components[w][-1]
                else: 
                    break
            # the node of the deepest subcircuit (root is shallow)
            current_io = q[-1]
            for i, sub in enumerate(reversed(subcircuits)):
                # if the node is an io node, then go one subcircuit level above
                if current_io in sub.io:
                    io_index = sub.io.index(current_io)
                    # finding the equivelent node in one subcircuit level above
                    current_io = subcircuits[-2-i].components[q[-2-i]][io_index]
                # if the node is an internal node, keep all subcircuits above the current level, 
                # and append the current node
                else:
                    q = q[0:-1-i]
                    q.append(current_io)
                    break
            result.append((original_string, ".".join(q)))
        return result

    def parse_ngspice_measurements(self, file_path, measurements):
        file = open(file_path, "r")
        file_content = file.read()
        file.close()
        for match in re.finditer(r"^\s*(meas_\w+)\s*=\s*([+-]?(\d*\.\d+|\d+\.\d*)([eE][\+-]?\d+)?|\d+[eE][\+-]?\d)", file_content, flags=re.I|re.M):
            if match.group(1) in measurements:
                measurements[match.group(1)].append((match.group(2)))
            else:
                measurements[match.group(1)] = [(match.group(2))]

    def run_ngspice(self, sp_path, parameter_dict):
        """
        This function runs NGSPICE on the .sp file at 'sp_path' and returns a dictionary that 
        contains the NGSPICE measurements.

        'parameter_dict' is a dictionary that contains the sizes of transistors and wire RC. 
        It has the following format:
        parameter_dict = {param1_name: [val1, val2, etc...],
                          param2_name: [val1, val2, etc...],
                          etc...}

        You need to make sure that 'parameter_dict' has a key-value pair for each parameter
        in your HSPICE netlists. Otherwise, the simulation will fail because of missing 
        parameters. That is, only the parameters found in 'parameter_dict' will be given a
        value. 
        
        This is important when we consider the fact that, the 'value' in the key value 
        pair is a list of different parameter values that you want to run HSPICE on.
        The lists must be of the same length for all params in 'parameter_dict' (param1_name's
        list has the same number of elements as param2_name). Here's what is going to happen:
        We will start by setting all the parameters to their 'val1' and we'll run NGSPICE. 
        Then, we'll set all the params to 'val2' and we'll run NGSPICE. And so on (that's 
        actually not exactly what happens, but you get the idea). So, you can run NGSPICE on 
        different transistor size conbinations by adding elements to these lists. Transistor 
        sizing combination i is ALL the vali in the parameter_dict. So, even if you never 
        want to change param1_name, you still need a list (who's elements will all be the 
        same in this case).
        If you only want to run NGSPICE for one transistor sizing combination, your lists will
        only have one element (but it still needs to be a list).

        Ok, so 'parameter_dict' contains a key-value pair for each transistor where the 'value'
        is a list of transistor sizes to use. A transistor sizing combination consists of all 
        the elements at a particular index in these lists. You also need to provide a key-value
        (or key-list we could say) for all your wire RC parameters. The wire RC data in the 
        lists corresponds to each transistor sizing combination. You'll need to calculate what
        the wire RC is for a particular transistor sizing combination outside this function 
        though. Here, we'll only set the paramters to the appropriate values. 

        Finally, what we'll return is a dictionary similar to 'parameter_dict' but containing
        all of the of the SPICE measurements. The return value will have this format: 

        measurements = {meas_name1: [value1, value2, value3, etc...], 
                        meas_name2: [value1, value2, value3, etc...],
                        etc...}
        """
        sp_dir = os.path.dirname(sp_path)
        sp_filename = os.path.basename(sp_path)

        numOfValues = len(next(iter(parameter_dict.values())))

        # modify the wire subcircuit so the syntax is NGSPICE compatible
        basic_subcircuit_path = "basic_subcircuits.l"
        basic_subcircuit_file = open(basic_subcircuit_path, "r+")
        basic_subcircuit_content = basic_subcircuit_file.read()
        # Rw and Cw become {Rw} and {Cw}
        basic_subcircuit_content_modified = re.sub(r"\b([RC]w)$", r"{\1}", basic_subcircuit_content, flags=re.M|re.I)
        basic_subcircuit_file.seek(0)
        basic_subcircuit_file.write(basic_subcircuit_content_modified)
        basic_subcircuit_file.truncate()
        basic_subcircuit_file.close()

        sp_file = open(os.path.join(sp_dir, sp_filename), "r+")
        sp_content = sp_file.read()
        # functions used by regex subsititution
        def insert_include(match):
            return f"{match.group(0)}\n.INCLUDE \"{os.path.join(os.getcwd(), HSPICE_DATA_SWEEP_PATH)}\"\n"
        def absolute_lib(match):
            return f"{match.group(1)}{os.path.abspath("includes.l")}{match.group(3)}"
        def add_quotation(match):
            s = "pulse ("
            if not match.group(1)[0].isdigit():
                s = s + f"'{match.group(1)}' "
            else:
                s = s + f"{match.group(1)} "
            if not match.group(2)[0].isdigit():
                s = s + f"'{match.group(2)}'"
            else:
                s = s + f"{match.group(2)}"
            return s
        def fix_vgnd(match):
            return f"Vgnd gnd1 gnd 0\n{match.group(1)}v(gnd1){match.group(3)}"
        # parameter file must be included in the circuit.sp file for NGSPICE
        sp_content_modified = re.sub(r".TITLE.*$", insert_include, sp_content, count=1, flags=re.M|re.I)
        # control block in NGSPICE to run and quit the simulation
        sp_content_modified = re.sub(r"$", "\n.CONTROL\nset temp = 25\nrun\nquit\n.ENDC\n", sp_content_modified, count = 1)
        # use absolute path for .LIB section
        sp_content_modified = re.sub(r"(.lib\s+\")(.*)(\")", absolute_lib, sp_content_modified, flags=re.M|re.I)
        # Remove the SWEEP in .tran section, NGSPICE does not have a SWEEP command
        # SWEEP effect is simulated by calling NGSPICE multiple times
        sp_content_modified = re.sub(r"(\.tran(\s+\w+){2}).*$", r"\1", sp_content_modified, flags=re.M|re.I)
        # INTEGRAL keyword has to be INTEG in NGSPICE
        sp_content_modified = re.sub(r"\bintegral\b", "INTEG", sp_content_modified, flags=re.M|re.I)
        # parameter to PULSE function has to have "'" around variables
        sp_content_modified = re.sub(r"pulse\s*\(\s*(\w+)\s+(\w+)", add_quotation, sp_content_modified, flags=re.M|re.I)
        # fix v(gnd): ngspice cannot measure node named gnd
        sp_content_modified = re.sub(r"^(.*)\bv\((gnd)\)(.*)$", fix_vgnd, sp_content_modified, flags=re.M|re.I)
        # replace reference to node with highest level internal node that is equivalent
        measure_replacements = self.measure_node_replacement(os.path.join(sp_dir, sp_filename), ["subcircuits.l", "basic_subcircuits.l"])
        
        for m in measure_replacements:
            sp_content_modified = re.sub(re.escape(m[0]), m[1], sp_content_modified, flags=re.M|re.I)
        sp_file.seek(0)
        sp_file.write(sp_content_modified)
        sp_file.truncate()
        sp_file.close()
        
        # Change working dir so that SPICE output files are created in circuit subdirectory
        saved_cwd = os.getcwd()
        os.chdir(sp_dir)
        measurements = {}
        hspice_data_file = open(os.path.join("..", HSPICE_DATA_SWEEP_PATH), 'r')
        hspice_data_content = hspice_data_file.read()
        hspice_data_file.close()
        for iteration in range(numOfValues): 
            # write all the vali to a parameter file
            hspice_data_file = open(os.path.join("..", HSPICE_DATA_SWEEP_PATH), 'w')
            for param in parameter_dict:
                hspice_data_file.write(".param " + param + "=" + str(parameter_dict[param][iteration])+ "\n")
            hspice_data_file.close()
         
            # Creat an output file having the ending .lis
            # Run the SPICE simulation and capture output
            output_filename = sp_filename.rstrip(".sp") + ".lis"
            output_file = open(output_filename, "w")
            subprocess.call(["ngspice", sp_filename], stdout=output_file, stderr=output_file)
            output_file.close()
            self.parse_ngspice_measurements(output_filename, measurements)

        measurements["temper"] = [25] * numOfValues

        measurements = {
            **measurements,
            **parameter_dict,
        }     

        # Update simulation counter with the number of simulations done by 
        # adding the length of the list of parameter values inside the dictionary
        self.simulation_counter += len(next(iter(parameter_dict.values())))   

        # Return to saved cwd
        os.chdir(saved_cwd)

        basic_subcircuit_file = open(basic_subcircuit_path, "w")
        basic_subcircuit_file.write(basic_subcircuit_content)
        basic_subcircuit_file.close()
        sp_file = open(os.path.join(sp_dir, sp_filename), "w")
        sp_file.write(sp_content)
        sp_file.close()
        hspice_data_file = open(os.path.join("..", HSPICE_DATA_SWEEP_PATH), 'w')
        hspice_data_file.write(hspice_data_content)
        hspice_data_file.close()

        return measurements

    def run(self, sp_path: str, parameter_dict: Dict[str, List[str]]):
        if self.useNgSpice:
            return self.run_ngspice(sp_path, parameter_dict)
        else:
            return self.run_hspice(sp_path, parameter_dict)

       
    def parse_mt0(self, filepath):
        """
        Parse a HSPICE .mt0 file to collect measurements. 
        This function works on .mt0 files generated from single HSPICE runs,
        .sweep runs or .data runs. 
        
        Returns a dictionary that maps measurement names to a list of values.
        If this was a single HSPICE run, the list will only have one element.
        But, if this was a HSPICE sweep, the list will have multiple elements,
        one for each sweep setting. The same goes for .data sweeps.
    
        measurements = {meas_name1: [value1, value2, value3, etc...], 
                        meas_name2: [value1, value2, value3, etc...],
                        etc...}
        """
    
        # The measurements data structure is what we will be building.
        # It's a dictionary that maps measurement names to a list of values. 
        # If this was a simple HSPICE run, the list will only have one element. 
        # But, if this was a HSPICE sweep, the list will have multiple elements,
        # one for each sweep setting.
        # measurements = {meas_name1: [value1, value2, value3, etc...], 
        #                 meas_name2: [value1, value2, value3, etc...],
        #                 etc...}
        measurements = {}
        meas_names = []

        #parse should be changed for ram block
        meaz1_names = []
        meaz2_names = []
        meaz1counter = 0
        meaz2counter = 0

        #I'll need an aittional 4 to test carry chains:
        meaz3_names = []
        meaz4_names = []
        meaz5_names = []
        meaz6_names = []
        meaz3counter = 0
        meaz4counter = 0
        meaz5counter = 0
        meaz6counter = 0
    
        # Open the file for reading
        mt0_file = open(filepath, 'r')
    
        # The first thing we expect to find is the measurement names.
        # We use the 'parsing_names' flag to show that we are parsing the names.
        # Once we find 'alter#' we are done parsing the measurement names. 
        # Then, we start parsing the values themselves.
        parsing_names = True
        for line in mt0_file:
            # Ignore these lines
            if line.startswith("$"):
                continue
            if line.startswith("."):
                continue
    
            if parsing_names:
                words = line.split()
                for meas_name in words:
                    meas_names.append(meas_name)
                    measurements[meas_name] = []
                    if "meaz1" in meas_name:
                        meaz1counter += 1
                        meaz1_names.append(meas_name)
                    if "meaz2" in meas_name:
                        meaz2counter += 1
                        meaz2_names.append(meas_name)
                    if "meaz3" in meas_name:
                        meaz3counter += 1
                        meaz3_names.append(meas_name)
                    if "meaz4" in meas_name:
                        meaz4counter += 1
                        meaz4_names.append(meas_name)
                    if "meaz5" in meas_name:
                        meaz5counter += 1
                        meaz5_names.append(meas_name)
                    if "meaz6" in meas_name:
                        meaz6counter += 1
                        meaz6_names.append(meas_name)
                    # When we find 'alter#' we are done parsing measurement names.
                    if meas_name.startswith("alter#"):
                        num_measurements = len(meas_names)
                        current_meas = 0
                        parsing_names = False
            else:
                line = line.replace("\n", "")
                words = line.split()
                for meas in words:
                    # Append each measurement value to the right list.
                    # We use current_meas and meas_names to keep track of where we 
                    # need to add the measurement value.
                    measurements[meas_names[current_meas]].append(meas)
                    current_meas += 1
                    if current_meas == num_measurements:
                        current_meas = 0


        
        mt0_file.close()

        # This part is added to support having tow different fanins (e.g. ram rowdecoder)
        # If this happens to any other circuit, you should name the delays with mez1 and meaz2
        # the rest is simply the same.
        if meaz3counter != 0:
            for x in range(0,len(meaz1_names)):
                newname = meaz3_names[x].replace("meaz3_", "meas_")
                measurements[newname] = max(measurements[meaz1_names[x]],measurements[meaz2_names[x]],measurements[meaz3_names[x]])
            return measurements             
        if len(meaz1_names) !=0 and len(meaz2_names) != 0:
            if len(meaz1_names) != len(meaz2_names):
                    sys.exit(-1)
            for x in range(0,len(meaz1_names)):
                newname = meaz1_names[x].replace("meaz1_", "meas_")
                measurements[newname] = max(measurements[meaz1_names[x]],measurements[meaz2_names[x]])
        elif len(meaz1_names) !=0:
            for x in range(0,len(meaz1_names)):
                newname = meaz1_names[x].replace("meaz1_", "meas_")
                measurements[newname] = measurements[meaz1_names[x]]
        elif len(meaz2_names) !=0:
            for x in range(0,len(meaz2_names)):
                newname = meaz2_names[x].replace("meaz2_", "meas_")
                measurements[newname] = measurements[meaz2_names[x]]

        return measurements         
