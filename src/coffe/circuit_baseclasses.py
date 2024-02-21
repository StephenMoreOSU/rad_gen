class _SizableCircuit:
    """ This is a base class used to identify FPGA circuits that can be sized (e.g. transistor sizing on lut)
        and declare attributes common to all SizableCircuits.
        If a class inherits _SizableCircuit, it should override all methods (error is raised otherwise). """
        
    # A list of the names of transistors in this subcircuit. This list should be logically sorted such 
    # that transistor names appear in the order that they should be sized.
    transistor_names = []
    # A list of the names of wires in this subcircuit
    wire_names = []
    # A dictionary of the initial transistor sizes
    initial_transistor_sizes = {}
    # Path to the top level spice file
    top_spice_path = ""    
    # Fall time for this subcircuit
    tfall = 1
    # Rise time for this subcircuit
    trise = 1
    # Delay to be used for this subcircuit
    delay = 1
    # Delay weight used to calculate delay of representative critical path
    delay_weight = 1
    # Dynamic power for this subcircuit
    power = 1

    
    def generate(self):
        """ Generate SPICE subcircuits.
            Generate method for base class must be overridden by child. """
        msg = "Function 'generate' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
       
       
    def generate_top(self):
        """ Generate top-level SPICE circuit.
            Generate method for base class must be overridden by child. """
        msg = "Function 'generate_top' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
     
     
    def update_area(self, area_dict, width_dict):
        """ Calculate area of circuit.
            Update area method for base class must be overridden by child. """
        msg = "Function 'update_area' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
        
        
    def update_wires(self, width_dict, wire_lengths, wire_layers):
        """ Update wire lengths and wire layers based on the width of things, obtained from width_dict. """
        msg = "Function 'update_wires' must be overridden in class _SizableCircuit."
        raise NotImplementedError(msg)
                
  
class _CompoundCircuit:
    """ This is a base class used to identify FPGA circuits that should not be sized. These circuits are
        usually composed of multiple smaller circuits, so we call them 'compound' circuits.
        Examples: circuits representing routing wires and loads. 
        If a class inherits _CompoundCircuit, it should override all methods."""

    def generate(self):
        """ Generate method for base class must be overridden by child. """
        msg = "Function 'generate' must be overridden in class _CompoundCircuit."
        raise NotImplementedError(msg)