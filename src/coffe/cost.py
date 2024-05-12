def cost_function(area, delay, area_opt_weight, delay_opt_weight):

    return pow(area,area_opt_weight) * pow(delay,delay_opt_weight)


def get_eval_area(
    fpga_inst, 
    opt_type: str, 
    subcircuit = None, 
    is_ram_component: bool = False, 
    is_cc_component: bool = False,
):
    """
        Get area cost for current FPGA state
    """
    if subcircuit:
        sp_name: str = subcircuit.sp_name if (hasattr(subcircuit, "sp_name") and subcircuit.sp_name) else subcircuit.name
        # Get area based on optimization type (subcircuit if local optimization, tile if global)
        if opt_type == "local":
            return fpga_inst.area_dict[sp_name]
        # If the block being sized is part of the memory component, return ram size
        # Otherwise, the block size is returned
        elif "hard_block" in sp_name:
            return subcircuit.area
    
    if is_cc_component:
        return fpga_inst.area_dict["total_carry_chain"]
    # If this is a regular block
    elif not is_ram_component or not fpga_inst.specs.enable_bram_block:
        return fpga_inst.area_dict["tile"] 
    else:
        return fpga_inst.area_dict["ram_core"]
    