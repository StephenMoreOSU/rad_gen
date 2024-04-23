from __future__ import annotations
from dataclasses import dataclass, field, fields, InitVar


from typing import List, Dict, Any, Tuple, Union, Type, Set



import os
import logging
import copy
import math

# Rad Gen data structures
import src.common.data_structs as rg_ds
import src.common.utils as rg_utils
import src.common.spice_parser as sp_parser

# import src.common.rr_parse as rrg_parse



# def common_hash(obj):
#     field_values = []

#     for field in fields(obj):
#         value = getattr(obj, field.name)

#         # Check if the field is mutable
#         if not dataclasses._is_classvar(field) and not dataclasses._is_initvar(field):
#             # If the field is another dataclass, call custom_hash recursively
#             if dataclasses.is_dataclass(value):
#                 field_values.append(custom_hash(value))
#             else:
#                 field_values.append(value)

#     # Combine the values of mutable fields to calculate the hash
#     return hash(tuple(field_values))

@dataclass
class LoadCircuit():
    id: int                                       = None                                   # Unique identifier for this sizeable circuit
    name: str = None
    sp_name: str = None
    wire_names: List[str]                          = field(default_factory= lambda: []) 
    # SizeableCircuits that are dependancies to create this loading circuit
    dep_ckts: List[Type[SizeableCircuit]]           = field(default_factory= lambda: [])

    def __post_init__(self):
        self.sp_name = self.get_sp_name()    

    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        msg = "Function 'update_wires' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)

    def generate(self):
        """ Generate SPICE subcircuits.
            Generate method for base class must be overridden by child. """
        msg = "Function 'generate' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)

    def get_sp_name(self) -> str:
        """ 
            Get the string used in spice for this subckt name
        """
        return f"{self.name}_id_{self.id}"

    def get_param_str(self) -> str:
        """ 
            Get the spice string for this subckt parameter
            Ex. "gen_routing_wire_L4" | "intra_tile_ble_2_sb"
        """
        return f"id_{self.id}"


@dataclass
class SizeableCircuit():
    # Hopefully replacable to '_SizableCircuit' and '_CompoundCircuit' classes
    # List of spice parameters for each tx size in component circuit TODO change to SpParam rather than str
    transistor_names: List[str]                        = field(default_factory= lambda: [])     
                                                                #    Because COFFE has so many parameters that may require sweeping, this list would be all parameters
                                                                #    Used in the component circuit AND any child subckts until we get to transistor sizes. 
                                                                #    This is why the Component class should be a relatively small circuit and not have more than around 10 transistor sizes in it
    # List of spice parameters for each wire length in component circuit TODO change to SpParam rather than str
    wire_names: List[str]                              = field(default_factory= lambda: [])     
    # Initial transistor sizes for each transistor in the component circuit
    initial_transistor_sizes: Dict[str, int | float]   = field(default_factory= lambda: {})     
    tfall: int | float                                 = 1      # Fall time for this subcircuit
    trise: int | float                                 = 1      # Rise time for this subcircuit
    delay: int | float                                 = 1      # Delay for this subcircuit
    delay_weight: int | float                          = 1      # Delay weight in a representative critical path
    power: int | float                                 = 1      # Dynamic power for this subcircuit

    name: str                                          = None
    sp_name: str                                       = None
    id: int                                            = None   # Unique identifier for this sizeable circuit

    num_per_tile: int                                  = None   # Number of this circuit in a tile
    circuit: rg_ds.SpSubCkt                            = None   # SpCircuit for this particular sizeable circuit
    # circuit: SwitchBlockMux(_SizeableCircuit) <
    #     child of _SizableCircuit or _CompoundCircuit or whatever class we use to represent
    #     a circuit having a .subckt, top_level, update_area/wires, (generate_top?) and works with transistor sizing function
    # >

    def __post_init__(self):
        self.sp_name = self.get_sp_name()

    def get_param_str(self) -> str:
        """ 
            Get the spice string for this subckt parameter
            Ex. "gen_routing_wire_L4" | "intra_tile_ble_2_sb"
        """
        return f"id_{self.id}"

    def get_sp_name(self) -> str:
        """ 
            Get the string used in spice for this subckt name
        """
        return f"{self.name}_id_{self.id}"

    def generate(self):
        """ Generate SPICE subcircuits.
            Generate method for base class must be overridden by child. """
        msg = "Function 'generate' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
       
    # def generate_top(self):
    #     """ Generate top-level SPICE circuit.
    #         Generate method for base class must be overridden by child. """
    #     msg = "Function 'generate_top' must be overridden in class _SizableCircuit."
    #     raise NotImplementedError(msg)
     
    def update_area(self, area_dict: Dict[str, float], width_dict: Dict[str, float]):
        """ Calculate area of circuit.
            Update area method for base class must be overridden by child. """
        msg = "Function 'update_area' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
        
        
    def update_wires(self, width_dict: Dict[str, float], wire_lengths: Dict[str, float], wire_layers: Dict[str, float]):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        msg = "Function 'update_wires' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
    

@dataclass
class CompoundCircuit():
    """
        Non sizable circuit containing sizeable circuits, has update_area + update_wire functions, however, they simlply call those functions for each sizeable circuit
    """
    
    name: str = None
    sp_name: str = None
    id: int                                       = None                                   # Unique identifier for this sizeable circuit
    
    def __post_init__(self):
        self.sp_name = self.get_sp_name() 

    def get_sp_name(self) -> str:
        """ 
            Get the string used in spice for this subckt name
        """
        return f"{self.name}_id_{self.id}"
    
    def get_param_str(self) -> str:
        """ 
            Get the spice string for this subckt parameter
            Ex. "gen_routing_wire_L4" | "intra_tile_ble_2_sb"
        """
        return f"id_{self.id}"

    def generate(self):
        """ Generate SPICE subcircuits.
            Generate method for base class must be overridden by child. """
        msg = "Function 'generate' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)





@dataclass
class Units:
    # Represents a unit of a particular type
    type: str                       = None # Name of the type of units being represented Ex. "time" | "voltage" | "current"   
    type_suffix: str                = None # Ex. "S" = seconds, "V" = volts, "A" = amps, "NFINS" | "NWIRE" | "NSHEET" = Discrete Tx Size  
    factor: int | float             = None # Factor to multiply the value by to get it into the base unit Ex. for nano = 1e-12
    factor_suffix: str              = None # For stdout or value conversion Ex. "n" = 1e-12, "p" = 1e-15, "m" = 1e-3, "u" = 1e-6
    # Dict of unit lookups for this unit type
    type_2_suff_lookup: dict      = field(default_factory = lambda: {
        # type -> suffix lookups
        'time': 's',
        'voltage': 'V',
        'current': 'A',
    }) 
    suff_2_type_lookup: dict      = field(default_factory = lambda: {
        # suffix -> type lookups
        's': 'time',
        'V': 'voltage',
        'A': 'current',
    })
    # These factor lookups are for spice write out
    # TODO verif write out functionality for each tool being used for
    suff_2_fac_lookup: dict           = field(default_factory = lambda: {
        '' : 1,
        'm': 1e-3,
        'u': 1e-6,
        'n': 1e-9,
        'p': 1e-12,
        'f': 1e-15,
        'a': 1e-18,
    })
    fac_2_suff_lookup: dict    = field(default_factory = lambda: {
        # suffix -> factor lookups
        1: '',
        1e-3: 'm',
        1e-6: 'u',
        1e-9: 'n',
        1e-12: 'p',
        1e-15: 'f',
        1e-18: 'a',
    })

    def __post_init__(self):
        ## Struct verif checks
        # assert self.factor != None or self.factor_suffix != None, "factor or factor_suffix must be set"
        # assert self.type != None or self.type_suffix != None, "type or type_suffix must be set"
        # Setting unit type
        if self.type:
            self.type_suffix = self.type_2_suff_lookup[self.type]
        elif self.type_suffix:
            self.type = self.suff_2_type_lookup[self.type_suffix]
        # Setting factor 
        if self.factor:
            self.factor_suffix = self.fac_2_suff_lookup[self.factor]
        elif self.factor_suffix:
            self.factor = self.suff_2_fac_lookup[self.factor_suffix]

    def update_factor(self, new_factor: int | float = None, new_suffix = None):
        if new_factor:
            # Update the factor and factor_suffix based on the new factor
            self.factor = new_factor
            self.factor_suffix = self.fac_2_suff_lookup[self.factor]
        elif new_suffix:
            # Update the factor and factor_suffix based on the new factor
            self.factor = self.suff_2_fac_lookup[new_suffix]
            self.factor_suffix = new_suffix
        else:
            raise ValueError("Either new_factor or new_suffix must be set")

@dataclass
class Value:
    # Params used to affect generation of a subckt or netlist. Ex. for a mux params could be "mux_type" : "on" | "off" | "partial"
    # Key used to hash this struct and find it in other data structs & write out the "parameter" name to various tools
    value: int | float              = None # Base value, if units are set this value is multiplied by the unit.factor to get the true value
    name: str                       = None # Name of the parameter Ex. "mux_type"
    units: Units                    = None # Units of the value Ex. "time" | "voltage" | "current"

    abs_val_flag: InitVar[bool]      = None

    def __post_init__(self, abs_val_flag: bool):
        # if we get the abs_val_flag, we assume the value is absolute and we decode it into the factors that exist in units
        if abs_val_flag:
            self.set_value(abs_val = self.value)
    
    def set_value(self, abs_val: float):
        """ 
            Set the value of this value struct to an absolute value
            Ex. abs_val = 0.1 -> self.value = 0.1, self.units = "n"
        """
        # Find the closest factor to our inputted self.value 
        suffix, _ = self.find_closest_factor()
        # Set Units to match this factor
        self.units.update_factor(new_suffix = suffix)
        # Set the value scaled 
        self.value = abs_val * self.units.factor if self.units.factor > 1 else abs_val / self.units.factor

    def find_closest_factor(self) -> Tuple[str, float]:
        min_difference = float('inf')

        ret_fac_combo: Tuple[str, float] = None
        for suffix, factor in self.units.suff_2_fac_lookup.items():
            cur_diff: float = abs(self.value - factor)
            if cur_diff < min_difference:
                min_difference = cur_diff
                ret_fac_combo = (suffix, factor)
        return ret_fac_combo


    def get_sp_val(self) -> str:
        # Get the value for use in spice
        if self.name:
            sp_str: str = self.name
        elif isinstance(self.value, (float, int)) and self.units:
            sp_str: str = self.get_sp_val_w_suffix()
        else:
            raise ValueError("Either name or value and units must be set")
        return sp_str

    def get_sp_val_w_suffix(self) -> str:
        """ 
            Get the spice string for this value with suffix
            Ex. "0.1n" | "1.0u" | "0.5m"
        """
        return f"{self.value}{self.units.factor_suffix}"
    
    def get_abs_val(self) -> float:
        """ 
            Get the absolute value of this value
            Ex. returns 0.1 | 1.0 | 0.5
        """
        return self.value * self.units.factor



@dataclass
class SpNodeProbe:
    # Information to create an evaluation of a spice node used in .MEAS, .PRINT, etc statements
    node: str  = None # Name of node being evaluated Ex. "n_1_1" or "x_top_inst.x_sub_inst.n_1_1"
    type: str  = None # 'voltage' | 'current'

    # Lookup to convert "unit type" to something spiec can understand Ex. "voltage" -> "V"
    type_2_sp_lookup: Dict[str, str] = field(
        default_factory = lambda: {
            "voltage": "V",
            "current": "I",
    })

    def get_sp_str(self) -> str:
        """ 
            Get the spice string for this node evaluation
            Ex. "v(node_name)" | "i(node_name)"
        """
        return f"{self.type_2_sp_lookup[self.type]}({self.node})"

@dataclass
class SpEvalFn:
    # Represents a function to be evaluted in spice. TODO implement assertions and checks to make sure they are valid
    fn: str  = None # Ex. "max(abs(rising_prop_delay_0),abs(falling_prop_delay_0))"

@dataclass
class SpDelayBound:
    # Information to create a "TRIG" or "TARG" portion of delay measure statement
    probe: SpNodeProbe  = None        # Node probe measured, compared to eval_cond to trigger bound
    eval_cond: SpEvalFn = None       # Evaluation condition to trigger bound                         Ex. "0.2*supply_v"
    td: str = None              # Optional Time delay delay bound can be triggered
    rise: bool = None           # If true, we are measuring a rising edge, if false, falling edge
    fall: bool = None                # If true, we are measuring a falling edge, if false, rising edge
    num_trans: int = 1         # Number of transitions to measure
    def __post_init__(self):
        if not self.rise:
            self.fall = True
        if not self.fall:
            self.rise = True
    #     # Struct verif checks
    #     assert self.rise != self.fall and (self.rise or self.fall), "Both rise and fall cannot be true or false at the same time"

    def get_sp_str(self) -> str:
        """ 
            Get the spice string for this delay bound
            Ex. "v(n_1) VAL="supply_v/2" RISE=1"
        """
        # Get the type of edge we are measuring
        edge_type: str = "RISE" if self.rise else "FALL"
        # Get the string for this delay bound
        sp_str: str = f"{self.probe.get_sp_str()} VAL='{self.eval_cond.fn}' {edge_type}={self.num_trans}"
        # If using time delay
        if self.td:
            sp_str += f" TD={self.td}"
        return sp_str 

@dataclass
class SpMeasure:
    # name : str # The string which is assigned to this measure statement
    # Contains information to generate a measure statement in a SPICE simulation
    type: str               = "TRAN"             # "DC" / "AC" / "TRAN"
    # TODO verify this spice expr exists
    # expr: SpNodeProbe               = None               # Ex. "FIND" | "INTEGRAL" | "PARAM" (None if using targ / trig)
    # probe: str              = None               # Node probe measured, in place to delay bound  
    value: Value            = None               # Variable to store the value of the measure statement
    trig: SpDelayBound      = None               # On what evaluation condition do we start trig
    targ: SpDelayBound      = None               # On what evaluation condition do we stop trig
    eval_fn: SpEvalFn       = None               # Raw spice which is evaluated to get meas statement value Ex. "max(abs(rising_prop_delay_0),abs(falling_prop_delay_0))"

    def __post_init__(self):
        # Struct verif checks
        # Make sure type is upper case
        self.type = self.type.upper()
        assert self.type in ["DC", "AC", "TRAN"], "type must be one of 'DC', 'AC', 'TRAN'"
        # Eval function should only be set if no trig / targ statements 
        if not ( self.trig or self.targ ):
            assert self.eval_fn != None, "Either trig or targ must be set if eval_fn is not set"
        else: 
            assert self.eval_fn == None, "If trig or targ is set, eval_fn must not be set"

    def get_sp_lines(self) -> List[str]:
        """ 
            Get the spice lines for this measure statement
            Ex. returns [".MEAS TRAN delay_0 TRIG v(n_1_1) VAL=0.2*supply_v TARG v(n_1_1) VAL=0.8*supply_v"]
        """
        # head_line += f" {self.eval_fn.fn}"
        
        meas_lines: List[str] = [
            f".MEAS {self.type} {self.value.name}",
        ]
        # Prefix to lines in body of measure statement
        body_prefix: str = f"+{' ' * 4}" 
        # Check if not using trig / targ
        if self.eval_fn:
            meas_lines += [
                f"{body_prefix}param='{self.eval_fn.fn}'"
            ]
        # If using trig / targ
        else:
            trig_line: str = f"{body_prefix}TRIG {self.trig.get_sp_str()}"
            targ_line: str = f"{body_prefix}TARG {self.targ.get_sp_str()}"
            # Add lines to meas_lines
            meas_lines += [trig_line, targ_line]
        return meas_lines


@dataclass
class SpLib:
    # Contains information to generate an include statement in a SPICE simulation
    path: str     = None                       # Path to the library file
    inc_libs: List[str] = None                       # Name of library to include from the file
    def get_sp_str(self) -> str:
        """ 
            Get the spice line for this include statement
            Ex. returns .LIB \"/path/to/file\" LIB_NAME
        """
        return f".LIB \"{self.path}\" {' '.join(self.inc_libs)}"
@dataclass
class SpSimMode:
    # TODO support DC | AC
    analysis: str = None # TRAN | AC | DC
    sim_prec: Value = None # Precision of simulation
    sim_time: Value = None # Duration of simulation
    # TODO define legal options for each analysis type
    args: Dict[str, str] = None # Additional Options following analysis directive
    def __post_init__(self):
        if not self.sim_prec.units:
            self.sim_prec.units = Units(type="time", factor_suffix='p')
        if not self.sim_time.units:
            self.sim_time.units = Units(type="time", factor_suffix='n')
    def get_sp_str(self) -> str:
        """ 
            Get the spice line for this analysis statement
            Ex. returns [".TRAN 0.1ns 10ns"]
        """
        opt_str: str = ' '.join([f"{k}={v}" if v else f"{k}" for k, v in self.args.items()])
        return f".{self.analysis} {self.sim_prec.get_sp_val()} {self.sim_time.get_sp_val()} {opt_str}"


# @dataclass
# class SpVoltageSrcFactory:
#     # Contains information to generate a voltage source in a SPICE simulation
#     def get_pulse(self, nam)

@dataclass
class SpVoltageSrc:
    """
        Data structure for specifying a voltage source 
        Only supportive of a pulse voltage source
    """
    name: str = None # name of voltage source, ex. if name = "IN" -> will be written as "VIN"
    sp_name: str = None # name of voltage source written to spice file
    out_node: str = None # node connecting to output of voltage source
    gnd_node: str = None # node connected to gnd, set to global defined gnd in __post_init__
    type: str = None # Type of voltage source Ex. PULSE, SINE, PWL, etc
    # All relevant params for pulse voltage src
    init_volt: Value = field(
        default_factory = lambda: Value(
            units = Units(type="voltage", factor=1),
        )
    ) # Initial voltage OR constant voltage for DC voltage src
    peak_volt: Value = field(
        default_factory = lambda: Value(
            units = Units(type="voltage", factor=1),
        )
    )
    # These times in ps
    delay_time: Value = field(
        default_factory = lambda: Value(
            value = 0,
            units = Units(type="time", factor_suffix='p'),
        )
    )
    rise_time: Value = field(
        default_factory = lambda: Value(
            value = 0,
            units = Units(type="time", factor_suffix='p'),
        )
    )
    fall_time: Value = field(
        default_factory = lambda: Value(
            value = 0,
            units = Units(type="time", factor_suffix='p'),
        )
    )
    # These times in ns
    pulse_width: Value = field(
        default_factory = lambda: Value(
            units = Units(type="time", factor_suffix='n'),
        )
    )
    period: Value = field(
        default_factory = lambda: Value(
            units = Units(type="time", factor_suffix='n'),
        )
    )
    def __post_init__(self):
        # Struct verif checks
        # assert self.type in ["PULSE", "SINE", "PWL", "DC"], "type must be one of 'PULSE', 'SINE', 'PWL', 'DC'"
        self.sp_name = self.get_sp_name()
        # Set gnd_node to global gnd if not set
        if not self.gnd_node:
            # TODO get this from some defined location
            self.gnd_node = "gnd"
        # Set default units
        for volt_val in [self.init_volt, self.peak_volt]:
            if not volt_val.units:
                volt_val.units = Units(type="voltage", factor=1)
        for pico_time_val in [self.rise_time, self.fall_time]:
            if not pico_time_val.units:
                pico_time_val.units = Units(type="time", factor_suffix='p')
        for nano_time_val in [self.pulse_width, self.period, self.delay_time]:
            if not nano_time_val.units:
                nano_time_val.units = Units(type="time", factor_suffix='n')


    def get_sp_str(self) -> str:
        """ 
            Get the spice line for this voltage source
            Ex. returns "VIN n_1_1 0 PULSE(0 1 0 0 0 0.1 0.2)"
        """
        if self.type:
            # This is literal string concat (just another way to concat strings)
            sp_str: str = " ".join([
                f"V{self.name}", f"{self.out_node}", f"{self.gnd_node}",
                f"{self.type}({self.init_volt.get_sp_val()}",f"{self.peak_volt.get_sp_val()}",
                f"{self.delay_time.get_sp_val()}",f"{self.rise_time.get_sp_val()}",
                f"{self.fall_time.get_sp_val()}",f"{self.pulse_width.get_sp_val()}",
                f"{self.period.get_sp_val()})",
            ])
        else:
            # Assumes we're using a DC voltage source
            sp_str: str = f"V{self.name} {self.out_node} {self.gnd_node} {self.init_volt.get_sp_val()}"

        return sp_str

    def get_sp_name(self) -> str:
        """ 
            Get the spice string for this voltage source name
            Ex. "VIN" | "VDD" | "VSS"
        """
        return f"V{self.name}"


@dataclass
class SimTB():
    # SubcktLib, used to initialize SpSubCkts from sp_names
    subckt_lib: Dict[str, Type[SizeableCircuit]] = None

    # Unique TB identifier, required because sometimes we simulate the same CB in a different TB environment
    id: int = None
    # Data required to perform a top level simulation of a particular component
    inc_libs: List[SpLib]                               = None
    mode: SpSimMode                                         = None 
    options: Dict[str, str]                                 = None 
    # Voltage sources used in the top level simulation
    voltage_srcs: List[SpVoltageSrc]                         = None
    stim_vsrc: SpVoltageSrc                                 = None
    dut_dc_vsrc: SpVoltageSrc                             = None
    # Structs to generate .MEAS statements
    meas_points: List[SpMeasure]                                = None 
    node_prints: List[SpNodeProbe]                              = None

    # sizing_ckt: Type[SizeableCircuit]                                # The Sizeable Circuit which we are simulating
    # SpInsts used in the top_level sim
    dut_ckt: Type[SizeableCircuit]                              = None
    top_insts: List[rg_ds.SpSubCktInst]                         = None
    # Could possibly get these from SpSubCkts themselves
    tb_fname: str = None 
    sp_fpath: str = None
    # List of sizable circuits require definitions to be used in this simulation
    # ckt_def_deps: List[Type[SizeableCircuit]]                   = field(default_factory= lambda: [])
    # Header lines for the spice simulation which are common to all simulations
    # sp_sim_setup_lines: List[str]                               = None

    # Instead of a list of ckt dependancies I'd rather just have pure definitions of the circuit objects in child clases
    # dep_wire_names: List[str] = []
    # dep_tx_names: List[str] = []
    # dep_ckt_basenames: List[str] = []           # basename of subckt definitions that 

    pwr_meas_clk_period: Value = field(
        default_factory = lambda: Value(
            value = 4,
            units = Units(type="time", factor_suffix='n'),
        )
    )

    # Sim global param / node variables
    # TODO get these global nodes from defined location
    vdd_node: str = "vdd"
    gnd_node: str = "gnd"
    sram_vdd_node: str = "vsram"
    sram_vss_node: str = "vsram_n"
    supply_v_param: str = "supply_v"

    # Prefix that is prepended to each measure statement variable
    meas_val_prefix: str = "meas"

    inc_hdr_lines: List[str] = field(
        default_factory = lambda: [
            "********************************************************************************",
            "** Include libraries, parameters and other",
            "********************************************************************************",
    ])
    setup_hdr_lines: List[str] = field(
        default_factory = lambda: [
            "********************************************************************************",
            "** Setup and input",
            "********************************************************************************",
    ])
    meas_hdr_lines: List[str] = field(
        default_factory = lambda: [
            "********************************************************************************",
            "** Measurement",
            "********************************************************************************",
    ])
    ckt_hdr_lines: List[str] = field(
        default_factory = lambda: [
            "********************************************************************************",
            "** Circuit",
            "********************************************************************************",
    ])

    # initialized __post_init__
    stim_vsrc: SpVoltageSrc = None
    delay_eval_cond: SpEvalFn = None # The condition to trigger trise / tfall eval on delay

    def __post_init__(self):
        self.delay_eval_cond: SpEvalFn = SpEvalFn(
            fn = f"{self.supply_v_param}/2"
        )
        # Define the standard voltage sources for the simulation
        # STIM PULSE Voltage SRC
        self.stim_vsrc = SpVoltageSrc(
            name = "IN",
            out_node = "n_in",
            type = "PULSE",
            init_volt = Value(0),
            peak_volt = Value(name = self.supply_v_param),
            pulse_width = Value(2), # ns
            period = Value(4), # ns
        )
    
    def __hash__(self):
        return id(self)
    
    def get_node_prints_line(self) -> str:
        """ 
            Get the spice line for this node probe
            Ex. returns ".PRINT V(n_1_1)"
        """
        return ".PRINT " + " ".join([node_probe.get_sp_str() for node_probe in self.node_prints])

    # def __post_init__(self):
    #     dep_wire_names: List[str] = []                      # List of wire names (SpParams) Which are dependancies for this simulation
    #     dep_tx_names: List[str] = []                        # List of transistor names (SpParams) Which are dependancies for this simulation
    #     dep_ckt_basenames: List[str] = []

    # def __post_init__(self):
    def generate_top(self, 
            delay_names: List[str], targ_nodes: List[str],
            low_v_node: str, trig_node: str,
            # These two args used for edge cases (lut driver w lut load)
            tb_fname: str = None,
            pwr_meas_lines: List[str] = None,
            ) -> str:
        """
            Common functionality for child generation of SPICE Testbenches
        """
        assert len(delay_names) == len(targ_nodes) 
        if not tb_fname:
            self.tb_fname: str = f"{self.dut_ckt.sp_name}_tb_{self.id}"
        else:
            self.tb_fname = tb_fname
        os.makedirs(f"{self.tb_fname}", exist_ok=True)
        # self.sim_dpath = os.path.join(os.getcwd(), self.tb_fname)
        dut_sp_name: str = self.dut_ckt.sp_name
        
        # Probe nodes
        meas_probes: Set[str] = set()
        meas_probes.add(trig_node)
        for node in targ_nodes:
            meas_probes.add(node)
        self.node_prints = []
        for probe in meas_probes:
            self.node_prints.append(
                SpNodeProbe(
                    node = probe,
                    type = "voltage",
                )
            )
        # Compressed format for generating measurement statements for each inverter and tfall / trise combo
        # total trise / tfall is same as the last inverter
        for i, meas_name in enumerate(delay_names):
            for trans_state in ["rise", "fall"]:
                # Define variables to determine which nodes to use for trig / targ in the case of rising / falling
                trig_trans: bool = trans_state == "rise"
                # Create delay index to deal with repeat of last inverter for total
                delay_idx: int = i #if meas_name != "total" else len(delay_names) - 2
                targ_node: str = targ_nodes[delay_idx]
                # If we measure total delay we just use the index of the last inverter
                inv_idx: int = i + 1 if meas_name != "total" else i
                # Rise and fall combo, based on how many inverters in the chain
                # If its even we set both to rise or both to fall
                if inv_idx % 2 == 0:
                    rise_fall_combo: Tuple[bool] = (trig_trans, trig_trans)
                else:
                    rise_fall_combo: Tuple[bool] = (not trig_trans, trig_trans)

                delay_bounds: Dict[str, SpDelayBound] = {
                    del_str: SpDelayBound(
                        probe = SpNodeProbe(
                            node = node,
                            type = "voltage",
                        ),
                        eval_cond = self.delay_eval_cond,
                        rise = rise_fall_combo[i],
                    ) for (i, node), del_str in zip(enumerate([trig_node, targ_node]), ["trig", "targ"])
                }

                # Create measurement object
                measurement: SpMeasure = SpMeasure(
                    value = Value(
                        name = f"{self.meas_val_prefix}_{meas_name}_t{trans_state}",
                    ),
                    trig = delay_bounds["trig"],
                    targ = delay_bounds["targ"],
                )
                self.meas_points.append(measurement)
        low_volt_time: Value = copy.deepcopy(self.stim_vsrc.period)
        # Seems like the low voltage measure is always 1n less than period
        low_volt_time.value = low_volt_time.value - 1
        # Kinda hacky but we need to get the unit lookups
        # low_volt_time = Value(
        #     value = low_volt_abs_time,
        #     units = Units(),
        #     abs_val_flag = True
        # )

        # For every node in measure points create a probe
        if not pwr_meas_lines:
            pwr_meas_lines: List[str] = [
                f".MEASURE TRAN meas_logic_low_voltage FIND V({low_v_node}) AT={low_volt_time.get_sp_val()}",
                f"",
                f"* Measure the power required to propagate a rise and a fall transition through the subcircuit at 250MHz",
                f".MEASURE TRAN meas_current INTEGRAL I({self.dut_dc_vsrc.get_sp_name()}) FROM=0ns TO={self.pwr_meas_clk_period.get_sp_val()}",
                f".MEASURE TRAN meas_avg_power PARAM = '-(meas_current/{self.pwr_meas_clk_period.get_sp_val()})*{self.supply_v_param}'",
            ]

        # if voltage src list not defined
        if not self.voltage_srcs:
            self.voltage_srcs = [
                self.stim_vsrc, 
                self.dut_dc_vsrc
            ]
        # Create the spice file
        top_sp_lines: List[str] = [
            f".TITLE {dut_sp_name} Test Bench #{self.id}",
            # Library includes
            *self.inc_hdr_lines,
            *[ lib.get_sp_str() for lib in self.inc_libs],
            # Stimulus, Simulation Settings, and Voltage Sources
            *self.setup_hdr_lines,
            self.mode.get_sp_str(), # Analysis + Simulation Mode
            # Options for the simulation
            self.get_option_str(),
            "*** Input Signal & Power Supply ***",
            "* Power rail for the circuit under test.",
            "* This allows us to measure power of a circuit under test without measuring the power of wave shaping and load circuitry.",
            *[ vsrc.get_sp_str() for vsrc in self.voltage_srcs],
            # Measurements
            *self.meas_hdr_lines,
            *rg_utils.flatten_mixed_list(
                [ meas.get_sp_lines() for meas in self.meas_points] + ["\n"]
            ),
            # Raw Measure statements
            *pwr_meas_lines,
            # Circuit Inst Definitions
            *self.ckt_hdr_lines,
            *[ inst.get_sp_str() for inst in self.top_insts],
            self.get_node_prints_line(),
            ".END",
        ]
        # Write the SPICE file
        self.sp_fpath: str = os.path.join(self.tb_fname, f"{self.tb_fname}.sp")
        with open(self.sp_fpath, "w") as f:
            f.write("\n".join(top_sp_lines))

        return self.sp_fpath


    def get_option_str(self) -> str:
        """ 
            Get the spice string for this option statement
            Ex. ".OPTION BRIEF=1"
        """
        opt_str: str = ' '.join([f"{k}={v}" if v else f"{k}" for k, v in self.options.items()])
        return f".OPTIONS {opt_str}"



# @dataclass
# class Tile:

@dataclass
class Block:
    """
        Block refers to a type of subcircuit in the FPGA which is parameterized
        Contains information relevant to all subcircuits used in the FPGA of this 'block_type' 
        Examples of blocks are switch blocks, connection blocks, local interconnect
        Should only be created for non load circuits with multiple instantiations in a tile, load circuits don't need this information
    """

    total_num_per_tile: int = None # The total number of all instances of this circuit in a tile
    ckt_defs: List[Type[SizeableCircuit]] = None

    # Initalized in __post_init__
    # Percentage of each circuit type in a block
    perc_dist: Dict[Type[SizeableCircuit], float] = field(
        default_factory = lambda: {}
    ) 
    # What is the frequency of each of these circuit types in a block
    freq_dist: Dict[Type[SizeableCircuit], int] = field(
        default_factory = lambda: {}
    ) 
    block_area: float = 0 # Area of the block in nm^2 TODO implement in flexible units
    block_area_sram: float = 0 # Area of the block with SRAM in nm^2 TODO implement in flexible units
    block_area_no_sram: float = 0 # Area of the block without SRAM in nm^2 TODO implement in flexible units
    block_avg_area: float = 0
    block_avg_area_no_sram: float = 0 # Avg Area of the block without SRAM in nm^2 TODO implement in flexible units

    # Block Stripe Widths
    num_stripes: int = None 
    stripe_widths: Dict[Type[SizeableCircuit], float] = field(
        default_factory = lambda: {}
    )
    stripe_sram_widths: Dict[Type[SizeableCircuit], float] = field(
        default_factory = lambda: {}
    )
    stripe_avg_width: float = 0
    stripe_avg_sram_width: float = 0

    def __post_init__(self):
        # self.freq_dist = {ckt: 0 for ckt in self.ckt_defs}

        for ckt in self.ckt_defs:
            self.freq_dist[ckt] = ckt.num_per_tile

        self.perc_dist = {
            ckt: freq / self.total_num_per_tile 
                for ckt, freq in self.freq_dist.items()
        }
        # Struct verif checks
        assert sum(self.freq_dist.values()) == self.total_num_per_tile, f"Sum of freq_dist values must equal total_num_per_tile, got {sum(self.freq_dist.values())} != {self.total_num_per_tile}"
        assert all([set(self.ckt_defs) == set(list(ckt_info.keys())) for ckt_info in [self.perc_dist, self.freq_dist]]), f"perc_dist and freq_dist keys must be == ckt_defs"
        assert len(set([ckt.name for ckt in self.ckt_defs])) == 1, "All ckt_defs must have the same name"

    def set_block_tile_area(self, area_dict: Dict[str, float | int], width_dict: Dict[str, float | int]):
        # calculates the area with and without SRAM and average of this block type
        for ckt in self.ckt_defs:
            self.block_avg_area += self.perc_dist[ckt] * area_dict[ckt.sp_name]
            self.block_area += ckt.num_per_tile * area_dict[ckt.sp_name + "_sram"]
            self.block_area_no_sram += ckt.num_per_tile * area_dict[ckt.sp_name]
            self.block_area_sram += ckt.num_per_tile * (area_dict[ckt.sp_name + "_sram"] - area_dict[ckt.sp_name])
            self.block_avg_area_no_sram += self.perc_dist[ckt] * (area_dict[ckt.sp_name + "_sram"] - area_dict[ckt.sp_name])
        assert self.block_area != 0 and self.block_area_no_sram != 0 and self.block_avg_area != 0
        # Set the fields in the area dict
        # Specific to an SB mux
        area_dict[f"{self.ckt_defs[0].sp_name}_sram"] = self.block_area_sram
        area_dict[f"{self.ckt_defs[0].sp_name}_no_sram"] = self.block_area_no_sram
        
        # Across all Sb muxes (name rather than sp_name)
        area_dict[f"{self.ckt_defs[0].name}_avg"] = self.block_avg_area
        area_dict[f"{self.ckt_defs[0].name}_total"] = self.block_area
        width_dict[f"{self.ckt_defs[0].name}_total"] = math.sqrt(self.block_area)

    def set_block_widths(self, area_dict: Dict[str, float | int], num_stripes: int, lb_height: float):
        # Just set in this struct in case we need later
        self.num_stripes = num_stripes
        for ckt, freq  in self.freq_dist.items():
            self.stripe_widths[ckt] = freq * area_dict[f"{ckt.sp_name}_no_sram"] / ( num_stripes * lb_height)
            self.stripe_sram_widths[ckt] = freq * (area_dict[f"{ckt.sp_name}_sram"] - area_dict[f"{ckt.sp_name}"]) / ( num_stripes * lb_height)
            # Weighted avg across all instantiations 
            self.stripe_avg_width += self.stripe_widths[ckt] * self.perc_dist[ckt]
            self.stripe_avg_sram_width += self.stripe_sram_widths[ckt] * self.perc_dist[ckt]



        



@dataclass
class Model:

    # Models wrap around a list of SizeableCircuit objects which can exist on the FPGA
    #   and contain an update_XXX methods to condense the area of different parameterized instances of a circuit
    #   into a single value which can be used for cost functions or esitimation of area / delay / etc when considering many types for this circuit value is inconvient
    # name: str                                   # Name of the model, will be used to generate the "base" subckt names of insts, the inst name will be the model name + the inst uid
                                                #       Ex. "sb"
    # num_per_tile: int                           # Number of subckt instances per tile in the FPGA
    
    sim_tb: Type[SimTB]                  = None   # Test Bench to be created to simulate this model with a set of parameters
    ckt_def: Type[SizeableCircuit] = None   # The Sizeable Circuit which we are modeling
    # Fields that should apply to all circuits globally on a device for a particular run
    # use_tgate: bool # Use tgate or pass transistor
    
    
    def __post_init__(self):
        # Struct verif checks
        # Assert that the ckt_def is in the isnts of SimTB.top_insts
        pass



# RRG data structures are taken from csvs generated via the rr_parse script
@dataclass
class SegmentRRG():
    """ 
        This class describes a segment in the routing resource graph (RRG). 
    """
    # Required fields
    name: str            # Name of the segment
    id: int               
    length: int          # Length of the segment in number of tiles
    C_per_meter: float  # Capacitance per meter of the segment (FROM VTR)
    R_per_meter: float  # Resistance per meter of the segment (FROM VTR)

@dataclass
class SwitchRRG():
    name: str
    id: int
    type: str
    R: float        = None 
    Cin: float      = None 
    Cout: float     = None 
    Tdel: float     = None 


@dataclass
class MuxLoadRRG():
    wire_type: str  # What is the wire type being driven by this mux load?
    mux_type: str   # What loading mux are we referring to?
    freq: int       # How many of these muxes are attached?

@dataclass
class MuxIPIN():
    wire_type: str      # What is the wire type going into this mux IPIN?
    drv_type: str       # What is the driver type of the wire going into this mux IPIN?
    freq: int          # How many of these muxes are attached?

@dataclass
class MuxWireStatRRG():
    wire_type: str                # What wire are we referring to?
    drv_type: str                 # What mux is driving this wire?
    mux_ipins: List[MuxIPIN]      # What are the mux types / frequency attached to this wire?
    mux_loads: List[MuxLoadRRG]   # What are mux types / frequency attached to this wire?
    total_mux_inputs: int         = None  # How many mux inputs for mux driving this wire?
    total_wire_loads: int         = None  # How many wires are loading this mux in total of all types?
    num_mux_per_tile: int         = None # How many of these muxes are in a tile?
    num_mux_per_device: int       = None # How many of these muxes are in a device?
    def __post_init__(self):
        self.total_mux_inputs = sum([mux_ipin.freq for mux_ipin in self.mux_ipins])
        self.total_wire_loads = sum([mux_load.freq for mux_load in self.mux_loads])

@dataclass
class Wire:
    # Describes a wire type in the FPGA
    name: str           = None            # Name of the wire type, used for the SpParameter globally across circuits Ex. "gen_routing_wire_L4", "intra_tile_ble_2_sb"    
    layer: int          = None            # What RC index do we use for this wire (what metal layer does this corresond to?)
    id: int             = None            # Unique identifier for this wire type, used to generate the wire name Ex. "gen_routing_wire_L4_0", "intra_tile_ble_2_sb_0"
    def __post_init__(self):
        # Struct verif checks
        assert self.id >= 0, "uid must be a non-negative integer"

    def get_sp_param_str(self) -> str:
        """ 
            Get the spice string for this wire type
            Ex. "gen_routing_wire_L4" | "intra_tile_ble_2_sb"
        """
        return f"{self.name}_id_{self.id}"
    
    def __hash__(self):
        # Returns a unique id for this class, easier to think of like a pointer or reference
        return id(self)


@dataclass
class GenRoutingWire(Wire):
    """ 
        This class describes a general routing wire in an FPGA. 
    """
    name: str                = "wire_gen_routing"
    type: str                = None # The string associated with "WIRE_TYPE" column in rr_parse.py output rr_wire_stats.csv
    num_starting_per_tile: int  = None # Avg number of these wires starting in a tile, from RRG
    freq: int                = None # How many of these wires are in a channel?
    # Required fields
    length: int              = None # Length of the general routing wire in number of tiles

    def __hash__(self):
        return id(self)


@dataclass
class COFFETelemetry():
    # Telemetry info for coffe
    logger: logging.Logger
    update_area_cnt: int = 0
    update_wires_cnt: int = 0
    update_delays_cnt: int = 0
    out_catagories: List[str] = field(
        default_factory = lambda: [
            "wire_length",
            "area",
            "tx_size",
            "delay",
        ]
    )


class Specs:
    """ General FPGA specs. """
 
    def __init__(self, arch_params_dict, quick_mode_threshold):
        
        # FPGA architecture specs
        self.N                       = arch_params_dict['N']
        self.K                       = arch_params_dict['K']
        self.W                       = arch_params_dict['W']
        # self.rrg_fpath:             str                                 = arch_params_dict['rrg_fpath']
        self.wire_types:            List[Dict[str, Any]]                = arch_params_dict['wire_types']
        self.Fs_mtx:                List[Dict[str, Any]]                = arch_params_dict['Fs_mtx']
        self.sb_muxes:              List[Dict[str, Any]]                = arch_params_dict['sb_muxes']
        self.I                       = arch_params_dict['I']
        self.Fs                      = arch_params_dict['Fs']
        self.Fcin                    = arch_params_dict['Fcin']
        self.Fcout                   = arch_params_dict['Fcout']
        self.Fclocal                 = arch_params_dict['Fclocal']
        self.num_ble_general_outputs = arch_params_dict['Or']
        self.num_ble_local_outputs   = arch_params_dict['Ofb']
        self.num_cluster_outputs     = self.N * self.num_ble_general_outputs
        self.Rsel                    = arch_params_dict['Rsel']
        self.Rfb                     = arch_params_dict['Rfb']
        self.use_fluts               = arch_params_dict['use_fluts']
        self.independent_inputs      = arch_params_dict['independent_inputs']
        self.enable_carry_chain      = arch_params_dict['enable_carry_chain']
        self.carry_chain_type        = arch_params_dict['carry_chain_type']
        self.FAs_per_flut            = arch_params_dict['FAs_per_flut']

        # BRAM specs
        self.row_decoder_bits     = arch_params_dict['row_decoder_bits']
        self.col_decoder_bits     = arch_params_dict['col_decoder_bits']
        self.conf_decoder_bits    = arch_params_dict['conf_decoder_bits']
        self.sense_dv             = arch_params_dict['sense_dv']
        self.worst_read_current   = arch_params_dict['worst_read_current']
        self.quick_mode_threshold = quick_mode_threshold
        self.vdd_low_power        = arch_params_dict['vdd_low_power']
        self.vref                 = arch_params_dict['vref']
        self.number_of_banks      = arch_params_dict['number_of_banks']
        self.memory_technology    = arch_params_dict['memory_technology']
        self.SRAM_nominal_current = arch_params_dict['SRAM_nominal_current']
        self.MTJ_Rlow_nominal     = arch_params_dict['MTJ_Rlow_nominal']
        self.MTJ_Rlow_worstcase   = arch_params_dict['MTJ_Rlow_worstcase']
        self.MTJ_Rhigh_worstcase  = arch_params_dict['MTJ_Rhigh_worstcase']
        self.MTJ_Rhigh_nominal    = arch_params_dict['MTJ_Rhigh_nominal']
        self.vclmp                = arch_params_dict['vclmp']
        self.read_to_write_ratio  = arch_params_dict['read_to_write_ratio']
        self.enable_bram_block    = arch_params_dict['enable_bram_module']
        self.ram_local_mux_size   = arch_params_dict['ram_local_mux_size']


        # Technology specs
        self.vdd                      = arch_params_dict['vdd']
        self.vsram                    = arch_params_dict['vsram']
        self.vsram_n                  = arch_params_dict['vsram_n']
        self.gate_length              = arch_params_dict['gate_length']
        self.min_tran_width           = arch_params_dict['min_tran_width']
        self.min_width_tran_area      = arch_params_dict['min_width_tran_area']
        self.sram_cell_area           = arch_params_dict['sram_cell_area']
        self.trans_diffusion_length   = arch_params_dict['trans_diffusion_length']
        self.metal_stack              = arch_params_dict['metal']
        self.model_path               = arch_params_dict['model_path']
        self.model_library            = arch_params_dict['model_library']
        self.rest_length_factor       = arch_params_dict['rest_length_factor']
        self.use_tgate                = arch_params_dict['use_tgate']
        self.use_finfet               = arch_params_dict['use_finfet']
        self.gen_routing_metal_pitch  = arch_params_dict['gen_routing_metal_pitch']
        self.gen_routing_metal_layers = arch_params_dict['gen_routing_metal_layers']

        # Specs post init

        # If the user directly provides the freq of each wire type, then don't manually calculate the num_tracks
        if all(wire.get("freq") is not None for wire in self.wire_types):
            for i, wire in enumerate(self.wire_types):
                wire["num_tracks"] = wire["freq"]
                wire["id"] = i
        else:
            tracks = []
            for id, wire in enumerate(self.wire_types):
                tracks.append( int(self.W * wire["perc"]) )

            remaining_wires = self.W - sum(tracks)
            # Adjust tracks to distribute remaining wires proportionally
            while remaining_wires != 0:
                for idx, wire in enumerate(self.wire_types):
                    # Calculate the adjustment based on the remaining wires & freq of wire types
                    adjustment = round((self.W * wire["perc"] - tracks[idx]) * remaining_wires / sum(tracks))
                    # if we are reducing wires flip the sign of adjustment
                    if remaining_wires < 0:
                        adjustment = -adjustment
                    tracks[idx] += adjustment
                    remaining_wires -= adjustment
                    if remaining_wires == 0:
                        break
            # set it back in wire types
            for i, (wire, num_tracks) in enumerate(zip(self.wire_types, tracks)):
                wire["num_tracks"] = num_tracks
                wire["id"] = i

