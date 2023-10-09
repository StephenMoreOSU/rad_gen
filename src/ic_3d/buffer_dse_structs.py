from dataclasses import dataclass, field, fields
import os, sys
import re
import typing
from typing import List

import shapely as sh

import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px

import math
from itertools import combinations


def flatten_mixed_list(input_list):
    """
    Flattens a list with mixed value Ex. ["hello", ["billy","bob"],[["johnson"]]] -> ["hello", "billy","bob","johnson"]
    """
    # Create flatten list lambda function
    flat_list = lambda input_list:[element for item in input_list for element in flat_list(item)] if type(input_list) is list else [input_list]
    # Call lambda function
    flattened_list = flat_list(input_list)
    return flattened_list

@dataclass 
class regexes:
    wspace_re = re.compile(r"\s+",re.MULTILINE)
    int_re = re.compile(r"[0-9]+", re.MULTILINE)
    # sp_del_grab_info_re = re.compile("([^\s=]+)=\s*(-?[\d\.]+)([a-z]+)\s+([^\s=]+)=\s*(-?[\d\.]+)([a-z]+)\s+([^\s=]+)=\s*(-?[\d\.]+)([a-z]+)",re.MULTILINE)
    sp_del_grab_info_re = re.compile(r"^.(?:(?P<var1>[^\s=]+)=\s*(?P<val1>-?[\d.]+)(?P<unit1>[a-z]+))?\s*(?:(?P<var2>[^\s=]+)=\s*(?P<val2>-?[\d.]+)(?P<unit2>[a-z]+))?\s*(?:(?P<var3>[^\s=]+)=\s*(?P<val3>-?[\d.]+)(?P<unit3>[a-z]+))?",re.MULTILINE)
    sp_grab_print_vals_re = re.compile(r"^x.*?^y",re.DOTALL | re.MULTILINE) 
    #
    sp_grab_inv_pn_vals_re : re.Pattern = re.compile(r"\s+\.param\s+(?P<name>inv_w[np]_\d+)\s+=\s+(?P<value>\d+\.\d+)\w*")


@dataclass
class SpProcess:
    """
    This represents a spice run which will be done
    From a title a spice directory will be created
    """
    title: str
    top_sp_dir: str
    sp_dir: str = None # path to directory created
    sp_file: str = None # path to sp file used for simulation
    sp_outfile: str = None # output file
    def __post_init__(self):
        self.sp_dir = os.path.join(self.top_sp_dir,self.title)
        if not os.path.exists(self.sp_dir):
            os.makedirs(self.sp_dir)
        self.sp_file = os.path.join(self.sp_dir,self.title+".sp")
        self.sp_outfile = os.path.join(self.sp_dir,self.title+".lis")
        


@dataclass
class SpInfo:
    """Spice subckt generation info"""
    top_dir: str = os.path.expanduser("~/3D_ICs")
    sp_dir: str = os.path.join(top_dir,"spice_sim")
    sp_sim_title: str = "ubump_ic_driver"
    sp_sim_file: str = os.path.join(top_dir,sp_dir,sp_sim_title,"ubump_ic_driver.sp")
    sp_sim_outfile: str = os.path.join(top_dir,sp_dir,sp_sim_title,"ubump_ic_driver.lis")    
    subckt_lib_dir: str = os.path.join(sp_dir,"subckts")
    basic_subckts_file: str = os.path.join(subckt_lib_dir,"basic_subcircuits.l")
    subckts_file: str = os.path.join(subckt_lib_dir,"subcircuits.l")
    includes_dir: str = os.path.join(sp_dir,"includes")
    include_sp_file: str = os.path.join(includes_dir,"includes.l")
    process_data_file: str = os.path.join(includes_dir,"process_data.l")
    sweep_data_file: str = os.path.join(includes_dir,"sweep_data.l")
    model_dir: str = os.path.join(sp_dir,"models")
    model_file: str = os.path.join(model_dir,"7nm_TT.l")
    # Info for process and package sensitivity analysis
    process_package_dse : SpProcess = None
    def __post_init__(self):
        self.process_package_dse = SpProcess(title="process_package_dse", top_sp_dir=self.sp_dir)


@dataclass
class SpSubCkt:
    """Spice subckt generation info"""

    ports: dict
    params: dict = field(default_factory=lambda: {})
    raw_sp_insts_lines: list = None
    # These params are to allow subcircuits and larger circuits to be created more easily out of them
    # port_defs: dict = None
    name: str = None
    # Element could be one of the following (cap, res, mfet, subckt, etc)
    element: str = "subckt"
    prefix: str = None
    insts: list = None
    direct_conn_insts: bool = False

    def connect_insts(self):
        """
        Connects the instances of the subckt together
        """
        for idx, inst in enumerate(self.insts):
            prev_tmp_int_node = f"n_{idx}"
            cur_tmp_int_node = f"n_{idx+1}"
            if idx == 0:
                # Connect inst input to subckt input
                inst.conns["in"] = self.ports["in"]["name"]
                inst.conns["out"] = cur_tmp_int_node
            elif idx == len(self.insts)-1:
                                # Connect inst input to subckt input
                inst.conns["in"] = prev_tmp_int_node
                inst.conns["out"] = self.ports["out"]["name"]
            else:
                inst.conns["in"] = prev_tmp_int_node
                inst.conns["out"] = cur_tmp_int_node
            
                # Connect las inst output to subckt output
                
    def __post_init__(self):
        prefix_lut = {
            "cap" : "C",
            "res" : "R",
            "ind" : "L",
            "mnfet" : "M",
            "mpfet" : "M",
            "subckt" : "X",
            "v_src" : "V",
        }        
        self.prefix = prefix_lut[self.element]
        if (self.direct_conn_insts == True):
            self.connect_insts()


@dataclass
class SpSubCktInst:
    subckt: SpSubCkt
    name: str
    conns: dict = field(default_factory = lambda: {})
    param_values: dict = None 
    
    # initialize the param_values to those stored in the subckt params, if the user wants to override them they will specify them at creation of SpSubCktInst object
    def __post_init__(self):
        if self.param_values == None:
            self.param_values = self.subckt.params.copy()


@dataclass
class SpVoltageSrcOptions:
    """ Data structure for specifying a voltage source """
    type: str = "PULSE"
    args: dict = field(default_factory = lambda: { 
        "init_val": "0",
        "pulsed_val": "supply_v",
        "delay_time": "0n",
        "rise_time": "0n",
        "fall_time": "0n",
        # below is the 1/2 period, and period for a square wave
        "pulse_width": "2n",
        "period": "4n",
    })


@dataclass
class TechInfo:
    # beol info
    mlayer_ic_res_list : list = None
    mlayer_ic_cap_list : list = None
    via_res_list : list = None
    via_cap_list : list = None
    # not really a tech info but TODO move to a better data structure
    ubump_res: str = None
    ubump_cap: str = None

    num_mlayers = 9
    Mx_range = [0,4]
    My_range = [4,9]
    # rough estimate for single trans area in um^2
    min_width_trans_area = 0.0946
    # def __post_init__(self):
    #     for 
        # self.beol_info["via_info"]

@dataclass
class SpProcessData:
    global_nodes : dict
    voltage_info : dict
    geometry_info : dict
    driver_info : dict
    tech_info: dict

@dataclass
class DriverSpModel:
    global_in_node: str = "n_in"
    global_out_node: str = "n_out"
    v_supply_param: str = "supply_v" 
    gnd_node: str = "gnd"
    global_vdd_node : str = "vdd"
    dut_in_node : str = "n_dut_in"
    dut_vdd_node: str = "vdd_dut"
    dut_out_node : str = "n_dut_out"



@dataclass
class SpLocalSimSettings:
    top_die_inv_stages: int
    # How many inverters on the base die?
    bottom_die_inv_stages: int
    total_inv_stages: int

    def __post_init__(self):
        self.total_inv_stages = self.top_die_inv_stages + self.bottom_die_inv_stages

@dataclass 
class SpGlobalSimSettings:
    # These unit lookups will set the default unit value of returned hspice sim plots
    # For below example 1ps will be the default time unit and 1mV will be the default voltage unit
    unit_lookups: dict = field(default_factory = lambda: {
        "time" : {
            "n" : 1e3,
            "p" : 1,
            "f" : 1e-3,
        },
        "voltage" : {
            "m": 1,
            "u": 1e-3,
            "n": 1e-6,
        }
    })
    bottom_die_inv_stages: int = 1 


########################## GENERAL PROCESS INFORMATION ###########################
@dataclass
class SpParam:
    # param name
    name: str
    # param unit (ex. f, p, etc)
    suffix: str
    # unit type (meters, farads, etc)
    # param val
    value: float = None
    unit: str = None
    # sweep_vals: List[float] = None
        

@dataclass
class MlayerInfo:
    idx: int # LOWEST -> TOP
    wire_res_per_um: float # Ohm / um
    wire_cap_per_um: float # fF / um
    via_res: float # Ohm
    via_cap: float # fF
    via_pitch: float # nm
    pitch: float # nm
    t_barrier: float # nm
    height: float # nm
    width: float # nm
    # Spice Info for MLayer / Vias
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        # for each member of mlayer
        for sp_param in ["wire_res_per_um","wire_cap_per_um","via_res","via_cap"]:
            attr_val = getattr(self, sp_param)
            if "res" in sp_param:
                suffix = "" # Ohm no unit
            elif "cap" in sp_param:
                suffix = "f"
            self.sp_params[sp_param] = SpParam(
                name = f"mlayer_{self.idx}_{sp_param}",
                value = attr_val,
                suffix = suffix,
            ) 
        # print(f"mlayer {self.idx} sp params:")
        # for k,v in self.self.sp_params.items():
        #     print(f"{k}: {v}")


@dataclass
class ViaStackInfo:
    mlayer_range: List[int]
    res: float # Ohm
    height: float # nm
    avg_mlayer_cap_per_um: float # fF / um
    # Spice Info for Via Stack
    cap: float = None # fF
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        # This is a rough (conservative estimation for via capacitance, probably much lower than this)
        self.cap = (self.height * 1e-3) * (self.avg_mlayer_cap_per_um)
        for sp_param in ["res", "cap"]:
            attr_val = getattr(self, sp_param)
            if "res" in sp_param:
                suffix = ""
            elif "cap" in sp_param:
                suffix = "f"
            self.sp_params[sp_param] = SpParam(
                name = f"via_stack_{sp_param}_m{self.mlayer_range[0]}_to_{self.mlayer_range[1]}_to",
                value = attr_val,
                suffix = suffix,
            )


@dataclass
class TxGeometryInfo:
    """ Geometry information for a single transistor of process """
    # hfin: float # nm
    min_tx_contact_width: float # nm
    tx_diffusion_length: float # nm
    gate_length: float # nm
    min_width_tx_area: float # nm^2
    sp_params: dict = field(default_factory = lambda: {})
    def __post_init__(self):
        sp_params = [field.name for field in fields(self) if field.name != "sp_params"]
        #sp_params = [ "min_tx_contact_width", "tx_diffusion_length", "gate_length", "hfin"]
        for sp_param in sp_params:
            attr_val = getattr(self, sp_param)
            suffix = "n"
            self.sp_params[sp_param] = SpParam(
                name = f"{sp_param}",
                value = attr_val,
                suffix = suffix,
            )

@dataclass
class ProcessInfo:
    name: str
    num_mlayers: int
    mlayers: List[MlayerInfo]
    contact_poly_pitch: float # nm
    # min_width_tx_area: float # nm^2
    # tx_dims: List[float] #nm
    via_stack_infos: List[ViaStackInfo]
    tx_geom_info: TxGeometryInfo


########################## GENERAL PROCESS INFORMATION ###########################


########################## PDN MODELING ###########################
@dataclass
class GridCoord:
    x: float
    y: float

@dataclass
class RectBB:
    p1 : GridCoord
    p2 : GridCoord
    # label for what this BB represents
    bb : sh.box
    # tsv_grid -> "TSV" "KoZ"
    # C4_grid -> "PWR" "GND" "IO"
    label : str

@dataclass
class GridPlacement:
    start_coord: GridCoord
    # vertical and horizontal distance in um for each TSV
    h: float 
    v: float
    # vertical and horizontal distance bw tsvs in um 
    s_h: float
    s_v: float
    dims: List[int]
    # grid start and end in um
    grid: List[List[RectBB]] = None
    # fig: go.Figure = go.Figure()
    tag: str = None # used to identify what this grid is for
    area: float = None # area of the grid in um^2
    bb_poly: sh.Polygon = None # Polygon containing a bounding box for the grid (xmin, ymin, xmax, ymax)
    # def update_grid()
    def __post_init__(self) -> None:
        self.grid = [[None]*self.dims[1] for _ in range(self.dims[0])]
        for col in range(self.dims[0]):
            for row in range(self.dims[1]):
                self.grid[col][row] = RectBB(
                    p1 = GridCoord(
                        x = self.start_coord.x + col*(self.s_h),
                        y = self.start_coord.y + row*(self.s_v),
                    ),
                    p2 = GridCoord(
                        x = self.start_coord.x + col*(self.s_h) + self.h,
                        y = self.start_coord.y + row*(self.s_v) + self.v,
                    ),
                    bb = sh.box(
                        xmin = self.start_coord.x + col*(self.s_h),
                        ymin = self.start_coord.y + row*(self.s_v),
                        xmax = self.start_coord.x + col*(self.s_h) + self.h,
                        ymax = self.start_coord.y + row*(self.s_v) + self.v,
                    ),
                    label = None,
                )
        poly_bbs = [ rect.bb for rows in self.grid for rect in rows ]
        self.bb_poly = sh.Polygon(
            [
                (min(x for x,_,_,_ in [poly.bounds for poly in poly_bbs]), min(y for _,y,_,_ in [poly.bounds for poly in poly_bbs])), # BL pos (xmin, ymin)
                (min(x for x,_,_,_ in [poly.bounds for poly in poly_bbs]), max(y for _,_,_,y in [poly.bounds for poly in poly_bbs])), # TL pos (xmin, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in poly_bbs]), max(y for _,_,_,y in [poly.bounds for poly in poly_bbs])), # TR pos (xmax, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in poly_bbs]), max(y for _,y,_,_ in [poly.bounds for poly in poly_bbs])) # BR pos (xmax, ymin)
            ]
        )
    def gen_fig(self, fig: go.Figure, fill_color: str, opacity: str, label_filt: str = None, layer: str = "above", line_color: str = "black") -> None:
        for col in range(self.dims[0]):
            for row in range(self.dims[1]):
                if label_filt is None or self.grid[col][row].label == label_filt:
                    fig.add_shape(
                        type="rect",
                        x0 = self.grid[col][row].bb.bounds[0],
                        y0 = self.grid[col][row].bb.bounds[1],
                        x1 = self.grid[col][row].bb.bounds[2],
                        y1 = self.grid[col][row].bb.bounds[3],
                        line = dict(
                            color = line_color,
                            width = 1,
                        ),
                        opacity = opacity,
                        fillcolor = fill_color,
                        layer = layer,
                    )



@dataclass
class SingleTSVInfo:
    height: int #um
    diameter: int #um
    pitch: int #um
    resistivity: float # Ohm * um
    keepout_zone: int #um (adds to diameter)
    area: float = None # um^2
    resistance: float = None # Ohm
    def __post_init__(self):
        self.area = (self.diameter**2)
        # self.resistance = self.resistivity * self.height / (self.diameter**2)


@dataclass
class PolyPlacements:
    # grid start and end in um
    rects: List[RectBB] = None
    tag: str = None # used to identify what this grid is for
    area: float = None # area of the grid in um^2
    bb_poly: sh.Polygon = None # Polygon containing a bounding box for the grid (xmin, ymin, xmax, ymax)

    def gen_fig(self, fig: go.Figure, fill_color: str, opacity: str, label_filt: str = None, layer: str = "above", line_color: str = "black") -> None:
        for rect in self.rects:
            if label_filt is None or rect.label == label_filt:
                fig.add_shape(
                    type="rect",
                    x0 = rect.bb.bounds[0],
                    y0 = rect.bb.bounds[1],
                    x1 = rect.bb.bounds[2],
                    y1 = rect.bb.bounds[3],
                    line = dict(
                        color = line_color,
                        width = 1,
                    ),
                    opacity = opacity,
                    fillcolor = fill_color,
                    layer = layer,
                )

@dataclass
# per C4 bump TSV info
class TSVInfo:
    single_tsv: SingleTSVInfo
    placement_setting: str # "dense" or "checkerboard"
    koz_grid: GridPlacement
    # koz_area: float # um^2
    # koz_bb_poly: sh.Polygon # polygon containing KoZ bounding box surrounding grid
    tsv_grid: GridPlacement
    # list of tsv relevant polygons (this is a way to more easily access the polygons rather than being forced to conform to grid)
    tsv_rect_placements: PolyPlacements = None
    koz_rect_placements: PolyPlacements = None
    # 
    dims: List[int] = None # [x, y] dimensions of grid
    area_bounds: List[float] = None # [xmax, ymax]
    # tsv_area: float # um^2
    # tsv_bb_poly: sh.Polygon # polygon containing TSV bounding box surrounding grid
    # for grid of TSVs
    resistance: float = None # Ohm
    
    def calc_resistance(self) -> float:
        return self.single_tsv.resistance / len(self.tsv_rect_placements.rects)
        # return self.single_tsv.resistivity * self.single_tsv.height / self.tsv_rect_placements.area



@dataclass
class SingleC4Info:
    height: int #um
    diameter: int #um
    pitch: int #um 
    area : float # um^2
    resistance: float = None
    def __post_init__(self):
        self.area = (self.diameter**2)

@dataclass
class C4Info:
    single_c4: SingleC4Info
    placement_setting: str # "dense" or "checkerboard"
    # margin between edge of device and start of C4 grid
    margin : int #um
    grid: GridPlacement # grid of C4s
    max_c4_placements: PolyPlacements = None # list of PolyPlacements containing max C4s for each device size
    max_c4_dims: List[int] = None # dimensions of C4 bumps based on device size
    # Used for calculating the FPGA floorplan
    pdn_dims: List[int] = None 


################## REPEAT OF C4 INFO FOR UBUMPS ##################
################## TODO update to use a single metal bump class ##################

@dataclass
class SolderBumpInfo:
    height: float
    diameter: float
    pitch: float
    res : float
    cap : float
    area : float = None
    bump_per_sq_um : float = None
    # for ubump "ubump" for c4 "c4", etc
    tag : str = None
    sp_params : dict = field(default_factory = lambda: {})
    def __post_init__(self): 
        # square area
        self.area = (self.diameter**2)
        # initialze sp params
        for sp_param in ["res","cap"]:
            attr_val = getattr(self, sp_param)
            if "res" in sp_param:
                suffix = "" # Ohm no unit
            elif "cap" in sp_param:
                suffix = "f"
            self.sp_params[sp_param] = SpParam(
                name = f"{self.tag}_{sp_param}",
                value = attr_val,
                suffix = suffix,
            )


@dataclass
class SingleUbumpInfo:
    height: float
    diameter: float
    pitch: float
    # resistivity: float 
    resistance: float = None
    area: float = None
    def __post_init__(self): 
        self.area = (self.diameter**2)
        # self.resistance = self.resistivity * self.height / (self.diameter**2)
@dataclass
class UbumpInfo:
    single_ubump: SingleUbumpInfo
    margin : float #um
    grid: GridPlacement #
    max_dims: List[int] = None #
################## REPEAT OF C4 INFO FOR UBUMPS ##################


@dataclass
class PwrRailInfo:
    # contains the percentage of each metal layer which pdn occupies
    # pitch_fac: float # pitch factor for power gnd rails
    mlayer_dist: List[float] # should be of length num_mlayers
    num_mlayers: int


@dataclass
class PDNSimSettings:
    plot_settings: dict = field(default_factory = lambda: {
        "tsv_grid" : False,
        "c4_grid" : False,
        "power_region": False,
        "pdn_sens_study": False,
    })


######################## GENERATING FPGA SECTOR FLOORPLAN ########################
@dataclass
class Coord:
    x: int
    y: int

@dataclass
class BlockRegion:
    resource_tag: str # "dsp", "bram", "lb", "io", "gnd", "pwr"
    pwr_region_coord: Coord # coord in grid of power regions
    sector_coord: Coord 

# @dataclass
# class PwrRegion:
#     # abs_dims: List[float] # [width, height]
#     # Grid of LB sized regions occupied by various types of blocks
#     blocks: List[List[BlockRegion]] = None


@dataclass 
class SectorInfo:
    # All below are calculated from floorplan and TSVs
    width: int = None # in LB tiles
    height: int = None # in LB tiles
    bram_cols: int = None
    dsp_cols: int = None
    abs_area: float = None # um^2
    sector_grid: List[List[BlockRegion]] = None
    # pwr_regions: List[List[PwrRegion]] = None

@dataclass
class FPGAResource:
    total_num: int
    abs_area: float # um^2
    rel_area: int # area in LBs (assume aspect ratio of W / L = Area / 1)
    abs_width: float = None # um
    abs_height: float = None # um 



@dataclass
class FPGAInfo:
    sector_info: SectorInfo
    sector_dims: List[int] # [x, y] number of sectors
    lbs: FPGAResource 
    dsps: FPGAResource
    brams: FPGAResource
    # calculated below
    grid_height: int = None
    grid_width: int = None

######################## GENERATING FPGA SECTOR FLOORPLAN ########################


pdn_sim_settings = PDNSimSettings()


def get_total_poly_area(boxes: List[sh.Polygon]) -> float:
    """ 
        Get total area of polygons, subtracts overlap area bw two bboxes (if any)
    """
    # Create polygons for each rectangle
    polygons = [sh.Polygon(box.exterior.coords) for box in boxes]
    # Compute the total area of all polygons
    total_area = sum(poly.area for poly in polygons)
    # Compute the area of intersection between each pair of rectangles,
    # skipping pairs that have already been checked
    intersection_area = 0
    checked_pairs = set()
    for box1, box2 in combinations(range(len(boxes)), 2):
        if (box1, box2) in checked_pairs or (box2, box1) in checked_pairs:
            continue
        if polygons[box1].intersects(polygons[box2]):
            intersection_area += polygons[box1].intersection(polygons[box2]).area
        checked_pairs.add((box1, box2))
    # Subtract the area of intersection to get the total area covered by boxes
    total_coverage_area = total_area - intersection_area
    # print(f"total area: {total_area}, intersection area: {intersection_area}, total coverage area: {total_coverage_area}")
    return total_coverage_area





@dataclass
class DesignPDN:
    ################ USER INPUTTED VALUES ################
    # Polygon containing the floorplan of the design (top and bottom die assumed to be the same)
    floorplan: sh.Polygon
    # Design Power Load (How many W power is the design taking in)
    power_budget: float # W
    #### COULD GO UNDER PROCESS PARAMS ####
    # Design Power Supply Voltage 
    process_info: ProcessInfo
    supply_voltage: float # V
    ir_drop_budget: float # mV
    fpga_info: FPGAInfo
    ################ GENERATED VALUES ################
    tsv_info: TSVInfo
    c4_info: C4Info
    ubump_info: UbumpInfo
    pwr_rail_info: PwrRailInfo
    pwr_region_dims: List[float] = None # [x, y] number of pwr regions
    resistance_target: float = None # mOhm 
    current_per_tx: float = None # A
    num_txs: int = None


    def init_placement(grid_pls: List[GridPlacement], area_inter: bool) -> PolyPlacements:
        rects = [ rect for grid_pl in grid_pls for rows in grid_pl.grid for rect in rows ]
        polys = [ rect.bb for grid_pl in grid_pls for rows in grid_pl.grid for rect in rows ]
        if area_inter:
            area = get_total_poly_area(polys)
        else:
            area = sum(poly.area for poly in polys)
        bb_poly = sh.Polygon(
            [
                (min(x for x,_,_,_ in [poly.bounds for poly in polys]), min(y for _,y,_,_ in [poly.bounds for poly in polys])), # BL pos (xmin, ymin)
                (min(x for x,_,_,_ in [poly.bounds for poly in polys]), max(y for _,_,_,y in [poly.bounds for poly in polys])), # TL pos (xmin, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in polys]), max(y for _,_,_,y in [poly.bounds for poly in polys])), # TR pos (xmax, ymax)
                (max(x for _,_,x,_ in [poly.bounds for poly in polys]), max(y for _,y,_,_ in [poly.bounds for poly in polys])) # BR pos (xmax, ymin)
            ]
        )
        # make sure the inputted placement is all of the same tag
        assert all(grid_pl.tag == grid_pls[0].tag for grid_pl in grid_pls)
        
        pps = PolyPlacements(
            rects = rects,
            bb_poly = bb_poly,
            area = area,
            # assumi
            tag = grid_pls[0].tag,
        )
        return pps

    def design_pdn_post_init(self) -> None:
        if self.c4_info.placement_setting == "dense":
            ######################################### MAX C4 GRID PLACEMENT INIT #########################################
            self.c4_info.max_c4_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch) 
            ] 
            self.ubump_info.max_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch) 
            ]
            c4_grid_placement = GridPlacement(
                start_coord=GridCoord(self.c4_info.margin,self.c4_info.margin),
                h=self.c4_info.single_c4.diameter,
                v=self.c4_info.single_c4.diameter,
                s_h=self.c4_info.single_c4.pitch,
                s_v=self.c4_info.single_c4.pitch,
                dims=self.c4_info.max_c4_dims,
                tag="C4"
            )
            self.c4_info.max_c4_placements = self.init_placement([c4_grid_placement], area_inter=False)
        elif self.c4_info.placement_setting == "checkerboard":
            ######################################### MAX C4 GRID PLACEMENT INIT #########################################
            self.c4_info.max_c4_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2) 
            ] 
            self.ubump_info.max_dims = [
                math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2),
                math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2) 
            ] 
            # Setting MAX C4 Grid
            c4_outer_grid = GridPlacement(
                start_coord=GridCoord(self.c4_info.margin,self.c4_info.margin),
                h=self.c4_info.single_c4.diameter,
                v=self.c4_info.single_c4.diameter,
                s_h=self.c4_info.single_c4.pitch*2,
                s_v=self.c4_info.single_c4.pitch*2,
                dims=self.c4_info.max_c4_dims,
                tag="C4"
            )
            c4_inner_grid = GridPlacement(
                start_coord=GridCoord(self.c4_info.margin + self.c4_info.single_c4.pitch, self.c4_info.margin + self.c4_info.single_c4.pitch),
                h=self.c4_info.single_c4.diameter,
                v=self.c4_info.single_c4.diameter,
                s_h=self.c4_info.single_c4.pitch*2,
                s_v=self.c4_info.single_c4.pitch*2,
                dims=self.c4_info.max_c4_dims-1,
                tag="C4"
            )
            self.c4_info.max_c4_placements = self.init_placement([c4_outer_grid, c4_inner_grid], area_inter=False)
        
        # get resistance target
        self.resistance_target = (self.power_budget / self.supply_voltage) / self.ir_drop_budget
        # get num txs in design
        self.num_txs = math.floor(self.floorplan.area / (self.process_info.tx_geom_info.min_width_tx_area*1e-6))
        self.current_per_tx = (self.power_budget / self.supply_voltage) / self.num_txs

    def update(self) -> None:
        self.design_pdn_post_init()
        # if self.tsv_info.placement_setting == "dense":
        #     self.c4_info.max_c4_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch) 
        #     ] 
        #     self.ubump_info.max_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch) 
        #     ] 
        # elif self.tsv_info.placement_setting == "checkerboard":
        #     self.c4_info.max_c4_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2) 
        #     ] 
        #     self.ubump_info.max_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2) 
        #     ] 
        # # get resistance target
        # self.resistance_target = (self.power_budget / self.supply_voltage) / self.ir_drop_budget

    def __post_init__(self):
        self.design_pdn_post_init()
        # if self.tsv_info.placement_setting == "dense":
        #     ######################################### MAX C4 GRID PLACEMENT INIT #########################################
        #     self.c4_info.max_c4_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch) 
        #     ] 
        #     self.ubump_info.max_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch) 
        #     ]
        #     c4_grid_placement = GridPlacement(
        #         start_coord=GridCoord(self.c4_info.margin,self.c4_info.margin),
        #         h=self.c4_info.single_c4.diameter,
        #         v=self.c4_info.single_c4.diameter,
        #         s_h=self.c4_info.single_c4.pitch,
        #         s_v=self.c4_info.single_c4.pitch,
        #         dims=self.c4_info.max_c4_dims,
        #         tag="C4"
        #     )
        #     self.c4_info.max_c4_placements = init_placement([c4_grid_placement])
        # elif self.tsv_info.placement_setting == "checkerboard":
        #     ######################################### MAX C4 GRID PLACEMENT INIT #########################################
        #     self.c4_info.max_c4_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.c4_info.margin*2 + self.c4_info.single_c4.diameter) / self.c4_info.single_c4.pitch * 2) 
        #     ] 
        #     self.ubump_info.max_dims = [
        #         math.floor(((self.floorplan.bounds[2] - self.floorplan.bounds[0]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2),
        #         math.floor(((self.floorplan.bounds[3] - self.floorplan.bounds[1]) - self.ubump_info.margin*2 + self.ubump_info.single_ubump.diameter) / self.ubump_info.single_ubump.pitch * 2) 
        #     ] 
        #     # Setting MAX C4 Grid
        #     c4_outer_grid = GridPlacement(
        #         start_coord=GridCoord(self.c4_info.margin,self.c4_info.margin),
        #         h=self.c4_info.single_c4.diameter,
        #         v=self.c4_info.single_c4.diameter,
        #         s_h=self.c4_info.single_c4.pitch*2,
        #         s_v=self.c4_info.single_c4.pitch*2,
        #         dims=self.c4_info.max_c4_dims,
        #         tag="C4"
        #     )
        #     c4_inner_grid = GridPlacement(
        #         start_coord=GridCoord(self.c4_info.margin + self.c4_info.single_c4.pitch, self.c4_info.margin + self.c4_info.single_c4.pitch),
        #         h=self.c4_info.single_c4.diameter,
        #         v=self.c4_info.single_c4.diameter,
        #         s_h=self.c4_info.single_c4.pitch*2,
        #         s_v=self.c4_info.single_c4.pitch*2,
        #         dims=self.c4_info.max_c4_dims-1,
        #         tag="C4"
        #     )
        #     self.c4_info.max_c4_placements = init_placement([c4_outer_grid, c4_inner_grid])
        
        # # get resistance target
        # self.resistance_target = (self.power_budget / self.supply_voltage) / self.ir_drop_budget
        # # get num txs in design
        # self.num_txs = math.floor(self.floorplan.area / (self.process_info.tx_geom_info.min_width_tx_area*1e-6))
        # self.current_per_tx = (self.power_budget / self.supply_voltage) / self.num_txs


@dataclass
class TSVGridPlacement:
    start_coord: GridCoord
    # vertical and horizontal distance in um for each TSV
    tsv_h: float 
    tsv_v: float
    # vertical and horizontal distance bw tsvs in um 
    tsv_s_h: float
    tsv_s_v: float
    dim: int
    # grid start and end in um
    tsv_grid : List[RectBB] = None
    def __post_init__(self):
        self.tsv_grid = [[None]*self.dim for _ in range(self.dim)]
        for col in range(self.dim):
            for row in range(self.dim):
                # bb of tsv coords 
                self.tsv_grid[col][row] = RectBB(
                    p1 = GridCoord(
                        x = self.start_coord.x + col*(self.tsv_s_h),
                        y = self.start_coord.y + row*(self.tsv_s_v),
                    ),
                    p2 = GridCoord(
                        x = self.start_coord.x + col*(self.tsv_s_h) + self.tsv_h,
                        y = self.start_coord.y + row*(self.tsv_s_v) + self.tsv_v,
                    ),
                )

@dataclass
class PDNModelingInfo:
    r_script_path: str = os.path.expanduser("~/3D_ICs/fpga21-scaled-tech/rc_calculations/custom_calc_resistance.py")
    c_script_path: str = os.path.expanduser("~/3D_ICs/fpga21-scaled-tech/rc_calculations/custom_calc_capacitance.py")

pdn_modeling_info = PDNModelingInfo()

########################## PDN MODELING ###########################




    


@dataclass
class SpTestingModel:
    insts : list
    testing_in_node: str = "n_in"
    testing_out_node: str = "n_out"
    target_freq: int = 1000 # freq in MHz
    # sim_prec: int # samples in ps
    # Params swept in sp simulation
    # sweep_mlayer_trav_dist: SpParam = None # um
    # sweep_ubump_factor: SpParam = None # unitless
    # sweep_via_factor: int = None # unitless
    # sweep_mlayer_cap_per_um: SpParam = None # f/um
    # sweep_mlayer_res_per_um: SpParam = None # Ohm/um

    # sp_params : dict = field(default_factory = lambda: {})
    # def __post_init__(self): 
    #     # initialze sp params
    #     for sp_param in ["sweep_mlayer_trav_dist","sweep_ubump_factor"]:
    #         attr_val = getattr(self, sp_param)
    #         suffix = ""
    #         self.sp_params[sp_param] = SpParam(
    #             name = f"{sp_param}",
    #             value = attr_val,
    #             suffix = suffix,
    #         )

@dataclass
class SpPNOptModel:
    wn_param : str = "inv_Wn"
    wp_param : str = "inv_Wp"

pn_opt_model = SpPNOptModel()


io_ports = {
    "in" : { 
        "name" : "n_in",
        "idx" : 0
    },
    "out" : { 
        "name" : "n_out",
        "idx" : 1
    }
}

io_vdd_gnd_ports = {
    "in" : { 
        "name" : "n_in",
        "idx" : 0
    },
    "out" : { 
        "name" : "n_out",
        "idx" : 1
    },
    "gnd" : { 
        "name" : "n_gnd",
        "idx" : 2
    },
    "vdd" : { 
        "name" : "n_vdd",
        "idx" : 3
    }
}


mfet_ports = {
    "base" : {
        "name" : "n_b",
        "idx": 3,
    },
    "drain" : {
        "name" : "n_d",
        "idx": 0,
    },
    "gate" : {
        "name" : "n_g",
        "idx": 1,
    },
    "source" : {
        "name" : "n_s",
        "idx": 2,
    },
}

nfet_width_param = "Wn"
pfet_width_param = "Wp"


tech_info = TechInfo()

"""
    Atomic subckts are from spice syntax and are not defined anywhere
    This means that the parameters used are always assigned during an instantiation of atomic subckts
"""
sp_subckt_atomic_lib = {
    "cap" : SpSubCkt(
        element = "cap",
        ports = io_ports,
        params = {
            "C" : "1f"
        }
    ),
    "res" : SpSubCkt(
        element = "res",
        ports = io_ports,
        params = {
            "R" : "1m"
        }
    ),
    "ind" : SpSubCkt(
        element = "ind",
        ports = io_ports,
        params = {
            "L" : "1p"
        }
    ),
    "mnfet" : SpSubCkt(
        name = "nmos",
        element = "mnfet",
        ports = mfet_ports,
        params = {
            "hfin" : "hfin",
            "lfin" : "lfin",
            "L" : "gate_length",
            "M" : "1",
            "nfin" : f"{nfet_width_param}",
            "ASEO" : f"{nfet_width_param}*min_tran_width*trans_diffusion_length",
            "ADEO" : f"{nfet_width_param}*min_tran_width*trans_diffusion_length",
            "PSEO" : f"{nfet_width_param}*min_tran_width+2*trans_diffusion_length",
            "PDEO" : f"{nfet_width_param}*min_tran_width+2*trans_diffusion_length",
        }
    ),
    "mpfet" : SpSubCkt(
        name = "pmos",
        element = "mpfet",
        ports = mfet_ports,
        params = {
            "hfin" : "hfin",
            "lfin" : "lfin",
            "L" : "gate_length",
            "M" : "1",
            "nfin" : f"{pfet_width_param}",
            "ASEO" : f"{pfet_width_param}*min_tran_width*trans_diffusion_length",
            "ADEO" : f"{pfet_width_param}*min_tran_width*trans_diffusion_length",
            "PSEO" : f"{pfet_width_param}*min_tran_width+2*trans_diffusion_length",
            "PDEO" : f"{pfet_width_param}*min_tran_width+2*trans_diffusion_length",
        }
    )
    
}


"""
How to describe connections to ports in a subckt?
conns should be a list of port key names which define the 

"""

""" 
    Basic subckts are made up from atomics and used to build more complex subckts
"""

#TODO make sure that the number of conn keys are equal to the number of ports in inst 
basic_subckts = {
    "inv" : SpSubCkt(
        name = "inv",
        element = "subckt",
        ports = io_vdd_gnd_ports,
        params = {
            "hfin": "3.5e-008",
            "lfin": "6.5e-009",
            "Wn" : "1",
            "Wp" : "2",
            "fanout" : "1",
        },
        insts = [
            SpSubCktInst(
                subckt = sp_subckt_atomic_lib["mnfet"],
                name = "N_DOWN",
                # Connecting the io_gnd_vdd_ports to the mnfet ports
                # Key will be mnfet port and value will be io_gnd_vdd_ports OR internal node
                conns = {
                    "gate" : io_vdd_gnd_ports["in"]["name"],
                    "base" : io_vdd_gnd_ports["gnd"]["name"],
                    "drain" : io_vdd_gnd_ports["out"]["name"],
                    "source" : io_vdd_gnd_ports["gnd"]["name"],
                },
                param_values = {
                    "hfin" : "hfin",
                    "lfin" : "lfin",
                    "L" : "gate_length",
                    "M" : "fanout",
                    "nfin" : f"{nfet_width_param}",
                    "ASEO" : f"{nfet_width_param}*min_tran_width*trans_diffusion_length",
                    "ADEO" : f"{nfet_width_param}*min_tran_width*trans_diffusion_length",
                    "PSEO" : f"{nfet_width_param}*min_tran_width+2*trans_diffusion_length",
                    "PDEO" : f"{nfet_width_param}*min_tran_width+2*trans_diffusion_length",
                }
                # if param values are not defined they are set to default
            ),
            SpSubCktInst(
                subckt = sp_subckt_atomic_lib["mpfet"],
                name = "P_UP",
                # Connecting the io_gnd_vdd_ports to the mnfet ports
                # Key will be mnfet port and value will be io_gnd_vdd_ports OR internal node
                conns = {
                    "drain" : io_vdd_gnd_ports["out"]["name"],
                    "gate" : io_vdd_gnd_ports["in"]["name"],
                    "source" : io_vdd_gnd_ports["vdd"]["name"],
                    "base" : io_vdd_gnd_ports["vdd"]["name"],
                },
                param_values = {
                    "hfin" : "hfin",
                    "lfin" : "lfin",
                    "L" : "gate_length",
                    "M" : "fanout",
                    "nfin" : f"{pfet_width_param}",
                    "ASEO" : f"{pfet_width_param}*min_tran_width*trans_diffusion_length",
                    "ADEO" : f"{pfet_width_param}*min_tran_width*trans_diffusion_length",
                    "PSEO" : f"{pfet_width_param}*min_tran_width+2*trans_diffusion_length",
                    "PDEO" : f"{pfet_width_param}*min_tran_width+2*trans_diffusion_length",
                }
                # if param values are not defined they are set to default
            ),
        ]
    ),
    "wire" : SpSubCkt(
        name = "wire",
        element = "subckt",
        ports = io_ports,
        params = {
            "Rw" : "1m",
            "Cw" : "1f",
        },
        insts = [
            SpSubCktInst(
                subckt = sp_subckt_atomic_lib["cap"],
                name = "PAR_IN",
                conns = { 
                    "in" : io_ports["in"]["name"],
                    "out" : "gnd", # TODO globally defined gnd, use data structure to access instead of hardcoding                    
                },
                param_values = {
                    "C" : "Cw",
                }
            ),
            SpSubCktInst(
                subckt = sp_subckt_atomic_lib["res"],
                name = "SER",
                conns = { 
                    "in" : io_ports["in"]["name"],
                    "out" : io_ports["out"]["name"],          
                },
                param_values = {
                    "R" : "Rw",
                }
            ),
            SpSubCktInst(
                subckt = sp_subckt_atomic_lib["cap"],
                name = "PAR_OUT",
                conns = { 
                    "in" : io_ports["out"]["name"],
                    "out" : "gnd", # TODO globally defined gnd, use data structure to access instead of hardcoding                    
                },
                param_values = {
                    "C" : "Cw",
                }
            ),
        ],
    ),
}

subckts = {
    ##### This works for only a specific metal stack, TODO fix this for all processes #####
    f"bottom_to_top_mlayers_via_stack": SpSubCkt( 
        name = f"bottom_to_top_mlayers_via_stack",
        element = "subckt",
        ports = io_ports,
        direct_conn_insts = True,
        insts = flatten_mixed_list([
            [
                [SpSubCktInst(
                    subckt = basic_subckts["wire"],
                    name = f"m1_to_m3_wire_load",
                    param_values={
                        "Rw" : f"m1_to_m3_via_stack_res",
                        "Cw" : f"{0.22}f",
                    }
                )] + [
                SpSubCktInst(
                    subckt = basic_subckts["wire"],
                    name = f"m{mlayer_idx}_to_m{mlayer_idx+1}_wire_load",
                    param_values={
                        "Rw" : f"m{mlayer_idx}_to_m{mlayer_idx+1}_via_stack_res",
                        # The capacitance of the via stack is estimated that 0.11 fF per via stack
                        "Cw" : f"0.11f",
                    # This indexing comes from the fact we want to start at metal 4 in the loop
                    # and only create a via stack (spice wire) for each odd metal layer
                    # 1 -> 3 ->
                    # 4 -> 5 ->
                    # 6 -> 7 ->
                    # And make sure to leave the last 2 metal layers (8,9) s.t the wire can be routed in X,Y
                }) for mlayer_idx in range(4, tech_info.num_mlayers-1, 2) ]
            ]
        ])
    ),
    f"m1_to_{tech_info.num_mlayers}_w_vias_load": SpSubCkt(
        name = f"m1_to_{tech_info.num_mlayers}_w_vias_load",
        element = "subckt",
        ports = io_ports,
        direct_conn_insts = True,
        # If the subckt contains a direct connection between insts
        # Then the insts are connected directly in the following order
        # [ "in" -> insts[0] -> ... -> insts[n] -> "out" ]
        insts = flatten_mixed_list([
            [SpSubCktInst(
                subckt = basic_subckts["wire"],
                name = f"m{mlayer_idx}_wire_load",
                param_values = {
                    "Rw": f"m{mlayer_idx}_ic_res",
                    "Cw": f"m{mlayer_idx}_ic_cap",
                },
            ),
            SpSubCktInst(
                subckt = basic_subckts["wire"],
                name = f"m{mlayer_idx}_m{mlayer_idx+1}_via_load",
                param_values = {
                    "Rw": f"m{mlayer_idx}_m{mlayer_idx+1}_via_res",
                    "Cw": f"m{mlayer_idx}_m{mlayer_idx+1}_via_cap",
                },
            )] for mlayer_idx in range(1, tech_info.num_mlayers )
        ]) + [
            # LAST m layer
            SpSubCktInst(
                subckt = basic_subckts["wire"],
                name = f"m{tech_info.num_mlayers}_wire_load",
                param_values = {
                    "Rw": f"m{tech_info.num_mlayers}_ic_res",
                    "Cw": f"m{tech_info.num_mlayers}_ic_cap",
                },
            ),
        ],
    ),
    f"m{tech_info.num_mlayers}_to_m1_w_vias_load": SpSubCkt(
        name = f"m{tech_info.num_mlayers}_to_m1_w_vias_load",
        element = "subckt",
        ports = io_ports,
        direct_conn_insts = True,
        # If the subckt contains a direct connection between insts
        # Then the insts are connected directly in the following order
        # [ "in" -> insts[0] -> ... -> insts[n] -> "out" ]
        insts = flatten_mixed_list([
            [SpSubCktInst(
                subckt = basic_subckts["wire"],
                name = f"m{mlayer_idx}_wire_load",
                param_values = {
                    "Rw": f"m{mlayer_idx}_ic_res",
                    "Cw": f"m{mlayer_idx}_ic_cap",
                },
            ),
            SpSubCktInst(
                subckt = basic_subckts["wire"],
                name = f"m{mlayer_idx}_m{mlayer_idx-1}_via_load",
                param_values = {
                    "Rw": f"m{mlayer_idx-1}_m{mlayer_idx}_via_res",
                    "Cw": f"m{mlayer_idx-1}_m{mlayer_idx}_via_cap",
                },
            )] for mlayer_idx in range(tech_info.num_mlayers, 1, -1)
        ]) + [
            # LAST m layer
            SpSubCktInst(
                subckt = basic_subckts["wire"],
                name = f"m1_wire_load",
                param_values = {
                    "Rw": f"m1_ic_res",
                    "Cw": f"m1_ic_cap",
                },
            ),
        ],
    ),
}



@dataclass
class SpSubCktLibs:
    atomic_subckts: dict = field(default_factory = lambda: sp_subckt_atomic_lib)
    basic_subckts: dict = field(default_factory = lambda: basic_subckts)
    subckts: dict = field(default_factory = lambda: subckts)

""" Here defines the top class used for buffer exploration """
@dataclass
class SRAMInfo:
    width: float # um
    height: float # um
    area: float = None # um^2
    def __post_init__(self):
        self.area = self.width * self.height

"""
    height: float
    diameter: float
    pitch: float
    res : float
    cap : float
"""

@dataclass
class PackageInfo:
    """
    Contains information about the package
    Ubumps / C4s / TSVs Etc ... 
    """
    ubump_info: SolderBumpInfo
    esd_rc_params: dict 
    # c4_info: SolderBumpInfo
    # tsv_info: TSVInfo




@dataclass
class HwModuleInfo:
    """
    Contains information about the HW Module
    """
    name: str
    area: float
    width: float
    height: float

@dataclass
class NoCInfo:
    area: float # um^2
    rtl_params: dict # RTL parameters

    lbs_per_router: float = None
    noc_lb_grid_sz: int = None
    noc_ubump_area: float = None

    max_num_ubumps: int = None
    needed_num_ubumps: int = None

    needed_lb_grid_sz: int = None
    add_wire_len: float = None

    def __post_init__(self):
        # Check if the RTL parameters are valid
        assert "flit_width" in self.rtl_params.keys()

    def calc_noc_info(self, lb_info: HwModuleInfo, ubump_pitch: float) -> None:
        self.lbs_per_router = math.ceil(self.area / lb_info.area)
        self.noc_lb_grid_sz = math.ceil(math.sqrt(self.lbs_per_router))
        self.noc_ubump_area = (math.ceil(math.sqrt(self.lbs_per_router))**2) * lb_info.area

        self.max_num_ubumps = math.floor((1/ubump_pitch**2) * self.noc_ubump_area)
        self.needed_num_ubumps = 2 * self.rtl_params["flit_width"]
        self.needed_lb_grid_sz = math.ceil(math.sqrt(self.needed_num_ubumps*(ubump_pitch**2)/lb_info.area))

        self.add_wire_len = max(math.ceil((math.ceil(math.sqrt(self.needed_num_ubumps * (ubump_pitch**2) / lb_info.area)) \
            - math.ceil(math.sqrt(self.lbs_per_router)) ) / 2) * (lb_info.width + lb_info.height), 0) 
        



@dataclass
class DesignInfo:
    """ Contains information about the Whole Design """
    # Process information
    process_info: ProcessInfo
    srams: List[SRAMInfo]
    logic_block: HwModuleInfo
    
    # Buffer DSE information
    subckt_libs: SpSubCktLibs
    bot_die_nstages: int
    package_info: PackageInfo = None

    nocs: List[NoCInfo] = None

    # Additional Wire Length Calculation
    # lbs_per_router: float = None
    # noc_lb_grid: float = None
    # noc_ubump_area: float = None
    buffer_routing_mlayer_idx: int = None
    # add_wire_len: float = None
    def calc_add_wlen(self):
        for noc in self.nocs:
            noc.calc_noc_info(self.logic_block, self.package_info.ubump_info.pitch)
    






""" Instantiation of Spice Circuits """
res = regexes()

spice_info = SpInfo()
driver_model_info = DriverSpModel()

# subckt_libs = SpSubCktLibs()

# global_sp_sim_settings = SpGlobalSimSettings()
sp_sim_settings = SpGlobalSimSettings()


process_data = SpProcessData(
    global_nodes = {
        "gnd": "gnd",
        "vdd": "vdd"
    },
    voltage_info = {
        "supply_v": "0.7"
    },
    geometry_info = {
        # "fin_height": "3.5e-008",
        # "fin_length": "6.5e-009",
        "gate_length" : "20n",
        "trans_diffusion_length" : "27.0n",
        "min_tran_width" : "27n",
        # "rest_length_factor" : "2",
    },
    driver_info = {
        **{
            key : val
            for stage_idx in range(10)
            for key, val in {
                f"init_Wn_{stage_idx}" : "1",
                f"init_Wp_{stage_idx}" : "2"
            }.items()
        },
        "dvr_ic_in_res" : "1m",
        "dvr_ic_in_cap" : "0.001f",
    },
    tech_info={
        # **{ f"m{mlayer+1}_ic_res": f"{res}" for mlayer, res in enumerate(tech_info.mlayer_ic_res_list) },
        # **{ f"m{mlayer+1}_ic_cap": f"{cap}" for mlayer, cap in enumerate(tech_info.mlayer_ic_cap_list) },
        # **{
        #     # Taken from [1] https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=5658180
        #     "ubump_cap": tech_info.ubump_cap,
        #     "ubump_res": tech_info.ubump_res,
        #     "m9_ubump_via_res": tech_info.via_res_list[-1],
        #     "m9_ubump_via_cap": tech_info.via_cap_list[-1],
        # },
        **{
            # Each of the following via stacks include a via to the next metal layer in name
            "m1_to_m3_via_stack_res": "33.95",
            "m4_to_m5_via_stack_res": "14.56",
            "m6_to_m7_via_stack_res": "9.59",
            "m8_to_m9_via_stack_res": "5.4",
        },
        **{
            # Taken from [1] https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=5658180
            "ubump_cap": "25.7f",
            "ubump_res": "3.9m",
            "m9_ubump_via_res": "10.32",
            "m9_ubump_via_cap": "0.12f",
        },
        # Values from [2] https://dl.acm.org/doi/pdf/10.1145/3431920.3439300
        # Mx resitance and capacitance, assuming 1um of metal
        **{ f"m{mlayer+1}_ic_res": f"128.7" for mlayer in range(tech_info.Mx_range[0],tech_info.Mx_range[1],1)},
        **{ f"m{mlayer+1}_ic_cap": f"0.22f" for mlayer in range(tech_info.Mx_range[0],tech_info.Mx_range[1],1)},
        # My resitance and capacitance
        **{ f"m{mlayer+1}_ic_res": f"21.6" for mlayer in range(tech_info.My_range[0],tech_info.My_range[1],1)},
        **{ f"m{mlayer+1}_ic_cap": f"0.24f" for mlayer in range(tech_info.My_range[0],tech_info.My_range[1],1)},
        # Mx-Mx via resistance and capacitance, 
        **{ f"m{mlayer+1}_m{mlayer+2}_via_res": f"34.8" for mlayer in range(tech_info.Mx_range[0],tech_info.Mx_range[1],1)},
        **{ f"m{mlayer+1}_m{mlayer+2}_via_cap": f"0.11f" for mlayer in range(tech_info.Mx_range[0],tech_info.Mx_range[1],1)},
        # My-My via resistance and capacitance, 
        **{ f"m{mlayer+1}_m{mlayer+2}_via_res": f"10.32" for mlayer in range(tech_info.My_range[0],tech_info.My_range[1],1)},
        **{ f"m{mlayer+1}_m{mlayer+2}_via_cap": f"0.12f" for mlayer in range(tech_info.My_range[0],tech_info.My_range[1],1)},

    }
)
