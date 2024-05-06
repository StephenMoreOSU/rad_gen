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
        sp_name: str = subcircuit.sp_name if subcircuit.sp_name else subcircuit.name
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
    
def get_eval_delay(fpga_inst, opt_type, subcircuit, tfall, trise, low_voltage, is_ram_component, is_cc_component):

    # omit measurements that are negative or doesn't reach Vgnd
    if tfall < 0 or trise < 0 or low_voltage > 4.0e-1:
        return 100

    # omit measurements that are too large
    if tfall > 5e-9 or trise > 5e-9 :
        return 100

    # Use average delay for evaluation
    delay = (tfall + trise)/2

    skip_size = 5

    if "hard_block" in subcircuit.name:
        delaywrost = 0.0
        if tfall > trise:
            delayworst = tfall
        else:
            delayworst = trise

        subcircuit.delay = delay
        subcircuit.trise = trise
        subcircuit.tfall = tfall

        if delayworst > subcircuit.lowerbounddelay:
            return subcircuit.delay + 10* (delayworst - subcircuit.lowerbounddelay)
        else:
            return subcircuit.delay

    if is_cc_component:
        subcircuit.delay = delay
        if fpga_inst.specs.carry_chain_type == "ripple":
            path_delay =  (fpga_inst.specs.N * fpga_inst.specs.FAs_per_flut - 2) * fpga_inst.carrychain.delay + fpga_inst.carrychainperf.delay + fpga_inst.carrychaininter.delay
            # The skip is pretty much dependent on size, I'll just assume 4 skip stages for now. However, it should work for any number of bits.
        elif fpga_inst.specs.carry_chain_type == "skip":
            # The critical path is the ripple path and the skip of the first one + the skip path of blocks in between, and the ripple and sum of the last block + the time it takes to load the wire in between
            path_delay = (fpga_inst.carrychain.delay * skip_size  + fpga_inst.carrychainand.delay + fpga_inst.carrychainskipmux.delay) + 2 * fpga_inst.carrychainskipmux.delay + fpga_inst.carrychain.delay * skip_size + fpga_inst.carrychainperf.delay +  (3 - fpga_inst.specs.FAs_per_flut) * fpga_inst.carrychaininter.delay
        return path_delay

        
    if opt_type == "local":
        return delay
    else:
        # We need to get the delay of a representative critical path
        # Let's first set the delay for this subcircuit
        subcircuit.delay = delay
        
        path_delay = 0
        
        # Switch block(s)
        for sb_mux in fpga_inst.sb_muxes:
            sb_mux_ipin_freq_ratio = sb_mux.num_per_tile * sb_mux.required_size / sum([sb_mux.num_per_tile * sb_mux.required_size for sb_mux in fpga_inst.sb_muxes])
            path_delay += sb_mux.delay * sb_mux.delay_weight * sb_mux_ipin_freq_ratio

        # path_delay += fpga_inst.sb_mux.delay*fpga_inst.sb_mux.delay_weight
        # Connection block
        path_delay += fpga_inst.cb_mux.delay*fpga_inst.cb_mux.delay_weight
        # Local mux
        path_delay += fpga_inst.logic_cluster.local_mux.delay*fpga_inst.logic_cluster.local_mux.delay_weight
        # LUT
        path_delay += fpga_inst.logic_cluster.ble.lut.delay*fpga_inst.logic_cluster.ble.lut.delay_weight
        # LUT input drivers

        for lut_input_name, lut_input in fpga_inst.logic_cluster.ble.lut.input_drivers.items():
            path_delay += lut_input.driver.delay*lut_input.driver.delay_weight
            path_delay += lut_input.not_driver.delay*lut_input.not_driver.delay_weight
        # Local BLE output
        path_delay += fpga_inst.logic_cluster.ble.local_output.delay*fpga_inst.logic_cluster.ble.local_output.delay_weight
        # General BLE output
        path_delay += fpga_inst.logic_cluster.ble.general_output.delay*fpga_inst.logic_cluster.ble.general_output.delay_weight
        if fpga_inst.specs.use_fluts:
            path_delay += fpga_inst.logic_cluster.ble.fmux.delay *fpga_inst.logic_cluster.ble.lut.delay_weight

        if fpga_inst.specs.enable_carry_chain == 1:
            path_delay += fpga_inst.carrychainmux.delay *fpga_inst.logic_cluster.ble.lut.delay_weight

        #print path_delay
        #path_delay +=fpga_inst.carrychain.delay *fpga_inst.logic_cluster.ble.lut.delay_weight

        if fpga_inst.specs.enable_bram_block == 0:
            return path_delay
        # Memory block components begin here
        # set RAM individual constant delays here:
        # Memory block local mux
        ram_delay = fpga_inst.RAM.RAM_local_mux.delay

        # Row decoder
        ram_decoder_stage1_delay = 0

        # Obtian the average of NAND2 and NAND3 paths if they are both valid
        count_1 = 0 
        if fpga_inst.RAM.valid_row_dec_size2 == 1:
            ram_decoder_stage1_delay += fpga_inst.RAM.rowdecoder_stage1_size2.delay
            count_1 +=1

        if fpga_inst.RAM.valid_row_dec_size3 == 1:
            ram_decoder_stage1_delay += fpga_inst.RAM.rowdecoder_stage1_size3.delay
            count_1 +=1

        if count_1 !=0:
            fpga_inst.RAM.estimated_rowdecoder_delay = ram_decoder_stage1_delay/count_1
        fpga_inst.RAM.estimated_rowdecoder_delay += fpga_inst.RAM.rowdecoder_stage3.delay
        ram_decoder_stage0_delay = fpga_inst.RAM.rowdecoder_stage0.delay
        fpga_inst.RAM.estimated_rowdecoder_delay += ram_decoder_stage0_delay

        ram_delay = ram_delay + fpga_inst.RAM.estimated_rowdecoder_delay
        # wordline driver
        ram_delay += fpga_inst.RAM.wordlinedriver.delay 
        # column decoder
        ram_delay +=  fpga_inst.RAM.columndecoder.delay

        # add some other components depending on the technology:
        if fpga_inst.RAM.memory_technology == "SRAM":
            ram_delay += fpga_inst.RAM.writedriver.delay + fpga_inst.RAM.samp.delay + fpga_inst.RAM.samp_part2.delay + fpga_inst.RAM.precharge.delay 
        else:
            ram_delay +=fpga_inst.RAM.bldischarging.delay + fpga_inst.RAM.blcharging.delay + fpga_inst.RAM.mtjsamp.delay
        
        # first stage of the configurable deocoder
        ram_delay += fpga_inst.RAM.configurabledecoderi.delay
        # second stage of the configurable decoder
        # if there are two, I'll just add both since it doesn't really matter.
        if fpga_inst.RAM.cvalidobj1 ==1:
            ram_delay += fpga_inst.RAM.configurabledecoder3ii.delay
        if fpga_inst.RAM.cvalidobj2 ==1:
            ram_delay += fpga_inst.RAM.configurabledecoder2ii.delay

        # last stage of the configurable decoder
        ram_delay += fpga_inst.RAM.configurabledecoderiii.delay

        # outputcrossbar
        ram_delay +=fpga_inst.RAM.pgateoutputcrossbar.delay

        if is_ram_component == 0:
            return path_delay
        else:
            return ram_delay
