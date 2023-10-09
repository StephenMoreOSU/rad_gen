# General imports
from typing import List, Dict, Tuple, Set, Union, Any, Type
import os, sys
from dataclasses import dataclass, asdict
import datetime
import yaml
import re
import subprocess as sp
from pathlib import Path
import json
import copy
import math
import pandas as pd
import io
from functools import reduce

import plotly.graph_objects as go
import shapely as sh

import numpy as np
from itertools import combinations, tee
from shapely.ops import nearest_points
from plotly.subplots import make_subplots
from collections import deque

import src.utils as rg_utils
import src.data_structs as rg_ds

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def map_smaller_grid_to_larger_grid(N: List[int], M: List[int]):
    N_columns = N[0]
    N_rows = N[1]
    M_columns = M[0]
    M_rows = M[1]

    # Generate coordinates for the smaller grid
    smaller_grid_rows, smaller_grid_columns = np.indices((N_rows, N_columns))
    smaller_grid = np.stack((smaller_grid_rows.flatten(), smaller_grid_columns.flatten()), axis=1)

    # Calculate the scaling factors for each dimension
    scale_factor_rows = M_rows / N_rows
    scale_factor_columns = M_columns / N_columns

    # Generate coordinates for the larger grid by scaling the smaller grid
    larger_grid_rows = smaller_grid[:, 0] * scale_factor_rows
    larger_grid_columns = smaller_grid[:, 1] * scale_factor_columns
    larger_grid = np.stack((larger_grid_rows, larger_grid_columns), axis=1)

    return larger_grid.astype(int)


def check_pair_in_array(array, pair):
    return np.any((array == pair).all(axis=1))


def plot_c4_placements(c4_info: dict, design_info: dict):
    c4_grid_placement = rg_ds.GridPlacement(
        start_coord=rg_ds.GridCoord(c4_info["grid_margin"],c4_info["grid_margin"]),
        h=c4_info["diameter"],
        v=c4_info["diameter"],
        s_h=c4_info["pitch"],
        s_v=c4_info["pitch"],
        dim=int(math.sqrt(design_info["num_c4"])),
    )
    fig = go.Figure()
    c4_polys = []
    pwr_rail_polys = []
    mapped_coords = map_smaller_grid_to_larger_grid(int(math.sqrt(design_info["num_pdn_c4"])),int(math.sqrt(design_info["num_c4"])))
    scale_factor = int(math.sqrt(design_info["num_c4"])) // int(math.sqrt(design_info["num_pdn_c4"]))
    pwr_rail_distance = ((scale_factor-1)*c4_info["diameter"] + (c4_info["pitch"] - c4_info["diameter"])*scale_factor)/2
    # print(pwr_rail_distance)
    # we need to know how far apart c4 bumps are to know distance required for upper metal layer routing
    for row in range(len(c4_grid_placement.grid)):
        for col in range(len(c4_grid_placement.grid[0])):
            c4_poly = {}
            c4_poly_bb = sh.box(
                xmin=c4_grid_placement.grid[row][col].p1.x,
                ymin=c4_grid_placement.grid[row][col].p1.y,
                xmax=c4_grid_placement.grid[row][col].p2.x,
                ymax=c4_grid_placement.grid[row][col].p2.y,
            )
            c4_poly["grid_idx"] = [col, row]
            if check_pair_in_array(mapped_coords,np.array([col,row])):
                c4_poly["pdn_active"] = True
                box_color = "Red"
                # pwr rails
                fig.add_shape(
                    type="rect",
                    x0=c4_grid_placement.grid[row][col].p1.x - pwr_rail_distance,
                    y0=c4_grid_placement.grid[row][col].p1.y - pwr_rail_distance,
                    x1=c4_grid_placement.grid[row][col].p2.x + pwr_rail_distance,
                    y1=c4_grid_placement.grid[row][col].p2.y + pwr_rail_distance,
                    opacity=0.1,
                    line=dict(
                        color="Black",
                        width=1,
                    ),
                    fillcolor="Yellow",
                )
                pwr_rail_poly = sh.box(
                    xmin=c4_grid_placement.grid[row][col].p1.x - pwr_rail_distance,
                    ymin=c4_grid_placement.grid[row][col].p1.y - pwr_rail_distance,
                    xmax=c4_grid_placement.grid[row][col].p2.x + pwr_rail_distance,
                    ymax=c4_grid_placement.grid[row][col].p2.y + pwr_rail_distance,
                )
                pwr_rail_polys.append(pwr_rail_poly)
            else:
                box_color = "Blue"
                c4_poly["pdn_active"] = False

            fig.add_shape(
                type="rect",
                x0=c4_grid_placement.grid[row][col].p1.x,
                y0=c4_grid_placement.grid[row][col].p1.y,
                x1=c4_grid_placement.grid[row][col].p2.x,
                y1=c4_grid_placement.grid[row][col].p2.y,
                line=dict(
                    color="RoyalBlue",
                    width=1,
                ),
                fillcolor=box_color,
            )


            c4_poly["bb"] = c4_poly_bb
            c4_polys.append(c4_poly)

    return fig, c4_polys, pwr_rail_distance


# def get_tx_placements(design_pdn: DesignPDN, pwr_region: RectBB) -> GridPlacement:
#     tx_x_pitch = (design_pdn.process_info.min_width_tx_area
#     tx_grid_placement = GridPlacement(
#         start_coord = GridCoord(pwr_region.bb.bounds[0], pwr_region.bb.bounds[1]),
#         h=design_pdn.process_info.tx_dims[0],
#         v=design_pdn.process_info.tx_dims[1],
#         s_h=(design_pdn.process_info.min_width_tx_area/design_pdn.process_info.tx_dims[1]),

#     )


def get_c4_placements_new(design_pdn: rg_ds.DesignPDN, pdn_dims: List[int]) -> dict:
    # Max c4 dimensions already initialized so we now map the smaller grid to the larger grid
    # Divide the max c4 dims into equal sized chunks
    r_width = (design_pdn.floorplan.bounds[2] - design_pdn.floorplan.bounds[0]) / pdn_dims[0]
    r_height = (design_pdn.floorplan.bounds[3] - design_pdn.floorplan.bounds[1]) / pdn_dims[1]

    # Region boxes splits up floorplan into even areas
    region_boxes = [
        sh.box(
            xmin = r_width*i,
            ymin = r_height*j,
            xmax = r_width*(i+1),
            ymax = r_height*(j+1),
        ) 
        for i in range(pdn_dims[0])
        for j in range(pdn_dims[1])
    ]
    # for each region find the C4 bump which is closest to the center of the region
    # region_center_to_c4_center_dists = []
    # for region in region_boxes:
    #     center_point = region.centroid
    #     for c4 in design_pdn.c4_info.placement_setting.rects:
    #         c4_center = c4.bb.centroid

    closest_region_to_c4_center = [
            min(
                [
                    [
                        region.centroid.distance(c4.bb.centroid),
                        idx,  
                    ] for idx, c4 in enumerate(design_pdn.c4_info.max_c4_placements.rects)
                ],
                key = lambda x: x[0]
            ) for region in region_boxes
        ] 

    for region_vals in closest_region_to_c4_center:
        idx = region_vals[1]
        design_pdn.c4_info.max_c4_placements.rects[idx].label = "PWR/GND"

    # max region dim would be the region dimension subtracted by half the diameter of C4 bump
    max_dist = (max([r_width,r_height]) - design_pdn.c4_info.single_c4.diameter)/2

    region_out_dict = {
        "max_dist": max_dist,
        "dims": [r_width, r_height],
        "boxes": region_boxes,
    }
    return region_out_dict
    # pwr_c4_coords



def get_c4_placements(design_pdn: rg_ds.DesignPDN, pdn_dims: List[int]) -> Tuple[rg_ds.GridPlacement]:
    c4_grid_placement = rg_ds.GridPlacement(
        start_coord=rg_ds.GridCoord(design_pdn.c4_info.margin,design_pdn.c4_info.margin),
        h=design_pdn.c4_info.single_c4.diameter,
        v=design_pdn.c4_info.single_c4.diameter,
        s_h=design_pdn.c4_info.single_c4.pitch,
        s_v=design_pdn.c4_info.single_c4.pitch,
        dims=design_pdn.c4_info.max_c4_dims,
        tag="C4"
    )
    mapped_coords = map_smaller_grid_to_larger_grid(pdn_dims, design_pdn.c4_info.max_c4_dims)
        
    mapped_grid = np.array(mapped_coords)
    unique_x = np.unique(mapped_grid[:,0])
    unique_y = np.unique(mapped_grid[:,1])
    max_x = max(unique_x)
    max_y = max(unique_y)
    if math.prod(pdn_dims) > 1:
        min_dx = np.amin(np.diff(unique_x))
        min_dy = np.amin(np.diff(unique_y))
    else:
        min_dx = 0
        min_dy = 0
    mapped_coords = [[col*min_dx, row*min_dy] for row in range(len(unique_y)) for col in range(len(unique_x))]

    # Offset the grid such that its not on the edge of the chip
    dims_diff = [design_pdn.c4_info.max_c4_dims[0] - max_x, design_pdn.c4_info.max_c4_dims[1] - max_y]
    mapped_coords = [[coord[0] + dims_diff[0]//2, coord[1] + dims_diff[1]//2] for coord in mapped_coords]
    pwr_rail_xy_diameters = [(((diff-1)*(design_pdn.c4_info.single_c4.diameter) + diff*(design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter))/2 + design_pdn.c4_info.single_c4.diameter/2) for diff in [min_dx,min_dy]] 
    # What are the dimensions of power rails, the following calculation is for the distance between two c4 bumps perspective power reigons (ie the x,y diameter of a power rail reigon)
    # scale_factors = [ max_c4_dim / pdn_dim for max_c4_dim, pdn_dim in zip(design_pdn.c4_info.max_c4_dims, pdn_dims) ]
    # pwr_rail_xy_diameters = [ ((fac-1)*(design_pdn.c4_info.single_c4.diameter*2) + fac*(design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter*2))/2 + design_pdn.c4_info.single_c4.diameter for fac in scale_factors ]
    # print(pwr_rail_xy_diameters)

    pwr_rail_regions_grid_placement = rg_ds.GridPlacement(
        #start_coord=GridCoord(design_pdn.c4_info.margin - (pwr_rail_xy_diameters[0] - design_pdn.c4_info.single_c4.diameter/2), design_pdn.c4_info.margin - (pwr_rail_xy_diameters[1] - design_pdn.c4_info.single_c4.diameter/2)),
        start_coord=rg_ds.GridCoord(design_pdn.c4_info.margin - (pwr_rail_xy_diameters[0] - design_pdn.c4_info.single_c4.diameter/2) + (design_pdn.c4_info.single_c4.diameter + (design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter))*mapped_coords[0][0], design_pdn.c4_info.margin - (pwr_rail_xy_diameters[0] - design_pdn.c4_info.single_c4.diameter/2) + (design_pdn.c4_info.single_c4.diameter + (design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter))*mapped_coords[0][1]),
        h=pwr_rail_xy_diameters[0]*2,
        v=pwr_rail_xy_diameters[1]*2,
        s_h=pwr_rail_xy_diameters[0]*2,
        s_v=pwr_rail_xy_diameters[1]*2,
        dims=pdn_dims,
        tag="PWR_RAIL_REGION"
    )
    for col in range(pwr_rail_regions_grid_placement.dims[0]):
        for row in range(pwr_rail_regions_grid_placement.dims[1]):
            # If on the edge of grid
            xmin = pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[0]
            ymin = pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[1]
            xmax = pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[2]
            ymax = pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[3]
            if col == 0:
                xmin = design_pdn.floorplan.bounds[0]
            if row == 0:
                ymin = design_pdn.floorplan.bounds[1]
            if col == (pwr_rail_regions_grid_placement.dims[0]-1):
                xmax = design_pdn.floorplan.bounds[2]
            if row == (pwr_rail_regions_grid_placement.dims[1]-1):
                ymax = design_pdn.floorplan.bounds[3]
            bb = sh.box(
                xmin = xmin,
                ymin = ymin,
                xmax = xmax,
                ymax = ymax
            )
            pwr_rail_regions_grid_placement.grid[col][row].bb = bb
            # if (row == 0 or col == 0 or col == pwr_rail_regions_grid_placement.dims[0]-1 or row == pwr_rail_regions_grid_placement.dims[1]-1): 
                # This depends on the Floorplan being intialized at 0,0
                # index 0 is -x, 1 is -y, 2 is +x, 3 is +y
                # bound_diffs = [ abs(fp-pwr) for fp, pwr in zip(design_pdn.floorplan.bounds, pwr_rail_regions_grid_placement.grid[col][row].bb.bounds)]
                # min_diff_idxs = [ idx for idx, diff in enumerate(bound_diffs) if diff == min(bound_diffs)]
                # moves = [ -1, -1, 1, 1]
                # bound_moves = [diff * moves[idx] if idx in min_diff_idxs else 0 for idx, diff in enumerate(bound_diffs)]
                # bb = sh.box(
                #     xmin=pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[0] + bound_moves[0],
                #     ymin=pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[1] + bound_moves[1],
                #     xmax=pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[2] + bound_moves[2],
                #     ymax=pwr_rail_regions_grid_placement.grid[col][row].bb.bounds[3] + bound_moves[3]
                # )
                # pwr_rail_regions_grid_placement.grid[col][row].bb = bb

                # print(f"col: {col}, row {row}: bound_diffs")
                # print(bound_moves)
                # print(bb.bounds)
                # print(bound_diffs)

    # sys.exit()
                # minx, miny, maxx, maxy
                # if abs(bounds[0] - design_pdn.floorplan.)
                

    # for x_idx, cols in enumerate(pwr_rail_regions_grid_placement.grid):
        # for y_idx, row in enumerate(cols):
            # print(row[]

    # sys.exit()
                



    pwr_rects = []
    # Update Rect BB tags to reflect which C4 bumps are used in PDN
    for x_idx, cols in enumerate(c4_grid_placement.grid):
        for y_idx, rect in enumerate(cols):
            if check_pair_in_array(mapped_coords, np.array([x_idx, y_idx])):
                rect.label = "PWR/GND"
                pwr_rects.append(rect)
            else:
                rect.label = "SIGNAL"

    
    # Find nearest points between pwr rail region and c4 bumps
    closest_points = [
        (
            nearest_points(pwr_rect.bb, design_pdn.floorplan),
            pwr_rect 
        ) for pwr_rect in pwr_rects 
    ]
    # closest_points = [ nearest_points(pwr_rect.bb, design_pdn.floorplan) for pwr_rect in pwr_rects ]
    # closest_points = [ item for sublist in closest_points for item in sublist]
    # for p in closest_points:
    #     print(p)
    # sys.exit(1)
    # from the closest points which one is the closest to the floorplan boundaries
    max_dist = max(
        [
            min(
                [
                    (p.distance(sh.Point(vertex)),(abs(p.x - vertex[0]),abs( p.y - vertex[1])), pair[1])
                    for pair in closest_points 
                    for p_tuple in pair 
                    for p in (p_tuple if isinstance(p_tuple,tuple) else [])
                ],
                key= lambda x: x[0]
            ) for vertex in design_pdn.floorplan.exterior.coords
        ],
        key = lambda x: x[0]
    )

    scale_factors = [ max_c4_dim / pdn_dim for max_c4_dim, pdn_dim in zip(design_pdn.c4_info.max_c4_dims, pdn_dims) ]
    pwr_rail_xy_diameters = [ ((fac-1)*(design_pdn.c4_info.single_c4.diameter*2) + fac*(design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter*2))/2 + design_pdn.c4_info.single_c4.diameter for fac in scale_factors ]


    xy_diam_bb = sh.box(
        xmin = 0,
        ymin = 0,
        xmax = pwr_rail_xy_diameters[0]*2,
        ymax = pwr_rail_xy_diameters[1]*2 
    )
    # print(pwr_rail_xy_diameters)
    # print(xy_diam_bb.bounds)

    # reformat to information
    critical_res_path_info = {
        "total_dist": max_dist[0],
        #"x_y_dist": max_dist[1],
        "x_y_dist": pwr_rail_xy_diameters,
        "c4_poly": max_dist[2],
        "pwr_rail_poly": xy_diam_bb,
    }

    # break_var = 0
    # for col in pwr_rail_regions_grid_placement.grid:
    #     for rect in col:
    #         if any(rect.bb.contains(sh.Point(p)) for p in critical_res_path_info["c4_poly"].bb.exterior.coords):
    #             break_var = 1
    #             critical_res_path_info["pwr_rail_poly"] = rect.bb
    #             break
    #     if break_var:
    #         break
        
    # print(design_pdn.floorplan)
    # print(closest_points)
    # print(closest_dists)
    # sys.exit(1)
    # print(f"scale_factors: {scale_factors}")
    # print(f"pwr_rail_xy_diameters: {pwr_rail_xy_diameters}")

    
    return c4_grid_placement, pwr_rail_regions_grid_placement, critical_res_path_info



def get_tsv_placements(design_pdn: rg_ds.DesignPDN, dims: List[int]) -> Tuple[rg_ds.GridPlacement]:
    # # res = (tsv_info["height"]*tsv_info["resistivity"])/((np.pi)*(dim**2)*(tsv_info["diameter"]/2)**2)
    
    # tsv_bb_area = ((tsv_info["diameter"]/2)**2)
    ## area for a single 
    # koz_bb_area = (((tsv_info["KoZ"] + tsv_info["diameter"]/2))*2)**2
    # koz_bb_2_bb_overlap_area = 2*(tsv_info["diameter"]/2 + tsv_info["KoZ"] - tsv_info["pitch"]/2)*((tsv_info["diameter"]/2 + tsv_info["KoZ"])*2)
    # inn_sq_area = ((tsv_info["diameter"]/2 + tsv_info["KoZ"] - tsv_info["pitch"]/2)*2)**2
    # total_area = koz_bb_area*(dim**2) - (((dim)*(dim-1)*2)*koz_bb_2_bb_overlap_area + inn_sq_area*((dim-1)**2) )
    # tsv_area_ratio = (tsv_bb_area*dim**2)/total_area
    # print(f"TSV Vals: R: {res} Dim: {dim}, Area: {total_area}, KoZ Area: {koz_bb_area}, % TSV Area: {tsv_area_ratio}")
    # init tsv grid (outer grid)
    if design_pdn.tsv_info.placement_setting == "dense":
        # TSV PLACEMENTS
        tsv_grid = rg_ds.GridPlacement(
            start_coord = rg_ds.GridCoord(0,0),
            h=design_pdn.tsv_info.single_tsv.diameter,
            v=design_pdn.tsv_info.single_tsv.diameter,
            s_h=design_pdn.tsv_info.single_tsv.pitch,
            s_v=design_pdn.tsv_info.single_tsv.pitch,
            dims=dims,
            tag="TSV",
        )
        # KOZ PLACEMENTS
        koz_grid = rg_ds.GridPlacement(
            start_coord = rg_ds.GridCoord(-design_pdn.tsv_info.single_tsv.keepout_zone, -design_pdn.tsv_info.single_tsv.keepout_zone),
            h = design_pdn.tsv_info.single_tsv.diameter + design_pdn.tsv_info.single_tsv.keepout_zone*2,
            v = design_pdn.tsv_info.single_tsv.diameter + design_pdn.tsv_info.single_tsv.keepout_zone*2,
            s_h = design_pdn.tsv_info.single_tsv.pitch,
            s_v = design_pdn.tsv_info.single_tsv.pitch,
            dims = dims,
            tag = "KOZ",
        )
        tsv_grids = {
            "TSV": [tsv_grid],
            "KOZ": [koz_grid],
        }
    elif design_pdn.tsv_info.placement_setting == "checkerboard":  
        tsv_grids = {
            "TSV": [],
            "KOZ": [],
        }      
        # OUTER GRID PLACEMENTS
        tsv_outer_grid = rg_ds.GridPlacement(
                start_coord=rg_ds.GridCoord(0,0),
                h=design_pdn.tsv_info.single_tsv.diameter,
                v=design_pdn.tsv_info.single_tsv.diameter,
                s_h=design_pdn.tsv_info.single_tsv.pitch*2,
                s_v=design_pdn.tsv_info.single_tsv.pitch*2,
                dims=dims,
                tag="TSV",
            )
        tsv_koz_outer_grid = rg_ds.GridPlacement(
            start_coord = rg_ds.GridCoord(-design_pdn.tsv_info.single_tsv.keepout_zone, -design_pdn.tsv_info.single_tsv.keepout_zone),
            h = design_pdn.tsv_info.single_tsv.diameter + design_pdn.tsv_info.single_tsv.keepout_zone*2,
            v = design_pdn.tsv_info.single_tsv.diameter + design_pdn.tsv_info.single_tsv.keepout_zone*2,
            s_h = design_pdn.tsv_info.single_tsv.pitch*2,
            s_v = design_pdn.tsv_info.single_tsv.pitch*2,
            dims = dims,
            tag = "KOZ",
        )    
        if math.prod(dims) > 1:
            tsv_inner_grid = rg_ds.GridPlacement(
                start_coord=rg_ds.GridCoord((design_pdn.tsv_info.single_tsv.pitch),(design_pdn.tsv_info.single_tsv.pitch)),
                h=design_pdn.tsv_info.single_tsv.diameter,
                v=design_pdn.tsv_info.single_tsv.diameter,
                s_h=design_pdn.tsv_info.single_tsv.pitch*2,
                s_v=design_pdn.tsv_info.single_tsv.pitch*2,
                dims=dims,
                tag="TSV",
            )
            tsv_koz_inner_grid = rg_ds.GridPlacement(
                start_coord = rg_ds.GridCoord(design_pdn.tsv_info.single_tsv.pitch-design_pdn.tsv_info.single_tsv.keepout_zone, design_pdn.tsv_info.single_tsv.pitch-design_pdn.tsv_info.single_tsv.keepout_zone),
                h = design_pdn.tsv_info.single_tsv.diameter + design_pdn.tsv_info.single_tsv.keepout_zone*2,
                v = design_pdn.tsv_info.single_tsv.diameter + design_pdn.tsv_info.single_tsv.keepout_zone*2,
                s_h = design_pdn.tsv_info.single_tsv.pitch*2,
                s_v = design_pdn.tsv_info.single_tsv.pitch*2,
                dims = dims,
                tag = "KOZ",
            )
            tsv_grids["TSV"] = [tsv_outer_grid, tsv_inner_grid]
            tsv_grids["KOZ"] = [tsv_koz_outer_grid, tsv_koz_inner_grid]
        else:
            tsv_grids["TSV"] = [tsv_outer_grid]
            tsv_grids["KOZ"] = [tsv_koz_outer_grid]
    
    return tsv_grids  

# def get_total_poly_area(boxes: List[sh.Polygon]) -> float:
#     """ 
#         Get total area of polygons, subtracts overlap area bw two bboxes (if any)
#     """

#     # Create polygons for each rectangle
#     polygons = [sh.Polygon(box.exterior.coords) for box in boxes]

#     # Compute the total area of all polygons
#     total_area = sum(poly.area for poly in polygons)

#     # Compute the area of intersection between each pair of rectangles,
#     # skipping pairs that have already been checked
#     intersection_area = 0
#     checked_pairs = set()
#     for box1, box2 in combinations(range(len(boxes)), 2):
#         if (box1, box2) in checked_pairs or (box2, box1) in checked_pairs:
#             continue
#         if polygons[box1].intersects(polygons[box2]):
#             intersection_area += polygons[box1].intersection(polygons[box2]).area
#         checked_pairs.add((box1, box2))

#     # Subtract the area of intersection to get the total area covered by boxes
#     total_coverage_area = total_area - intersection_area
#     # print(f"total area: {total_area}, intersection area: {intersection_area}, total coverage area: {total_coverage_area}")
#     return total_coverage_area



# def tsv_calc(tsv_grid: GridPlacement, koz_grid: GridPlacement) -> dict:
    
def tsv_calc(tsv_grids: dict) -> dict:
    return_dict = {
        "TSV":
        {
            "area": None,
            "bb": None,
        },
        "KOZ":
        {
            "area": None,
            "bb": None,
        },
    }
    # Get total area of all TSVs and KOZs
    KoZ_poly_bbs = [ rect.bb for koz_grid in tsv_grids["KOZ"] for rows in koz_grid.grid for rect in rows ]
    tsv_poly_bbs = [ rect.bb for tsv_grid in tsv_grids["TSV"] for rows in tsv_grid.grid for rect in rows ]
    ############ THESE TAKE WAY TOO LONG ############
    # TODO take this function out of data structs, just don't want to rn cus of import loop 
    koz_area = rg_ds.get_total_poly_area(KoZ_poly_bbs)
    #tsv_area = get_total_poly_area(tsv_poly_bbs)
    tsv_area = sum(rect.area for rect in tsv_poly_bbs)
    # koz_area = sum(rect.area for rect in KoZ_poly_bbs)

    # bounding box of all Polygons for KoZs and TSVs 
    koz_bb_poly = sh.Polygon(
        [
            (min(x for x,_,_,_ in [koz_poly.bounds for koz_poly in KoZ_poly_bbs]), min(y for _,y,_,_ in [koz_poly.bounds for koz_poly in KoZ_poly_bbs])), # BL pos (xmin, ymin)
            (min(x for x,_,_,_ in [koz_poly.bounds for koz_poly in KoZ_poly_bbs]), max(y for _,_,_,y in [koz_poly.bounds for koz_poly in KoZ_poly_bbs])), # TL pos (xmin, ymax)
            (max(x for _,_,x,_ in [koz_poly.bounds for koz_poly in KoZ_poly_bbs]), max(y for _,_,_,y in [koz_poly.bounds for koz_poly in KoZ_poly_bbs])), # TR pos (xmax, ymax)
            (max(x for _,_,x,_ in [koz_poly.bounds for koz_poly in KoZ_poly_bbs]), max(y for _,y,_,_ in [koz_poly.bounds for koz_poly in KoZ_poly_bbs])) # BR pos (xmax, ymin)
        ]
    )
    tsv_bb_poly = sh.Polygon(
        [
            (min(x for x,_,_,_ in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs]), min(y for _,y,_,_ in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs])), # BL pos (xmin, ymin)
            (min(x for x,_,_,_ in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs]), max(y for _,_,_,y in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs])), # TL pos (xmin, ymax)
            (max(x for _,_,x,_ in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs]), max(y for _,_,_,y in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs])), # TR pos (xmax, ymax)
            (max(x for _,_,x,_ in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs]), max(y for _,y,_,_ in [tsv_poly.bounds for tsv_poly in tsv_poly_bbs])) # BR pos (xmax, ymin)
        ]
    )
    
    return_dict["TSV"]["area"] = tsv_area
    return_dict["TSV"]["bb"] = tsv_bb_poly
    return_dict["KOZ"]["area"] = koz_area
    return_dict["KOZ"]["bb"] = koz_bb_poly

    return return_dict


def get_res_info_from_dims(design_pdn: rg_ds.DesignPDN, dims: List[int], metal_rail_res_per_um: float, single_via_stack_res: float, pwr_rails_per_um: float, current_per_sq_um: float, region_info: dict, source: str):
    
    # Assuming checkerboard pattern of power rails
    # if design_pdn.c4_info.placement_setting == "checkerboard":
    pwr_rail_xy_radius = [math.sqrt(design_pdn.floorplan.area / (math.prod(dims)))/2]*2
        # gnd_rail_xy_radius = []
    """
    if source == "ubump":
        scale_factors = [ int(max_dim) // int(pdn_dim) for max_dim, pdn_dim in zip(design_pdn.ubump_info.max_dims, dims) ]
        pwr_rail_xy_radius = [ ((fac-1)*design_pdn.ubump_info.single_ubump.diameter + fac*(design_pdn.ubump_info.single_ubump.pitch - design_pdn.ubump_info.single_ubump.diameter))/2 for fac in scale_factors ]
        pwr_rail_region_bump_dims = [max_dim // var_dim for max_dim, var_dim in zip(design_pdn.ubump_info.max_dims, dims)]
        pwr_rail_radius = [ ((fac-1)*(design_pdn.ubump_info.single_ubump.diameter*2) + fac*(design_pdn.ubump_info.single_ubump.pitch - design_pdn.ubump_info.single_ubump.diameter*2))/2 + design_pdn.ubump_info.single_ubump.diameter for fac in pwr_rail_region_bump_dims ]
    elif source == "c4":
        scale_factors = [ max_c4_dim / pdn_dim for max_c4_dim, pdn_dim in zip(design_pdn.c4_info.max_c4_dims, dims) ]
        pwr_rail_xy_radius = [ ((fac-1)*(design_pdn.c4_info.single_c4.diameter*2) + fac*(design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter*2))/2 + design_pdn.c4_info.single_c4.diameter for fac in scale_factors ]
        pwr_rail_region_bump_dims = [max_dim // var_dim for max_dim, var_dim in zip(design_pdn.ubump_info.max_dims, dims)]
        pwr_rail_radius = [ ((fac-1)*(design_pdn.c4_info.single_c4.diameter*2) + fac*(design_pdn.c4_info.single_c4.pitch - design_pdn.c4_info.single_c4.diameter*2))/2 + design_pdn.c4_info.single_c4.diameter for fac in pwr_rail_region_bump_dims ]
    """

    pwr_rail_box = sh.box(
        xmin = 0,
        ymin = 0,
        xmax = pwr_rail_xy_radius[0]*2,
        ymax = pwr_rail_xy_radius[1]*2 
    )
    region_dims = [ abs(pwr_rail_box.bounds[2] - pwr_rail_box.bounds[0]), abs(pwr_rail_box.bounds[3] - pwr_rail_box.bounds[1])]

    ######## PRECISE FINDING THE MIDDLE MOST POINT OF THE REGION ########
    # region_dims = region_info["dims"]
    # pwr_rail_box = region_info["boxes"][0]
    # max_dist = region_info["max_dist"]

    tsv_grid_bounds = [abs(design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[2] - design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[0]),abs(design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[3] - design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[1])]
    if source == "ubump":
        # Crit patch distance
        # Subtract distance from the edge of TSV region to the edge of power region
        crit_path_distance = (max(region_dims) - (min(tsv_grid_bounds)))/2
        #crit_path_distance = (max(region_dims) - (min(tsv_grid_bounds)))/2
        
        #crit_path_distance = (region_dims[0] - design_pdn.single_ubump.diameter) + (region_dims[1] - design_pdn.single_ubump.diameter)
    elif source == "c4":
        crit_path_distance = (max(region_dims) - (min(tsv_grid_bounds))) / 2
        # crit_path_distance = (max(region_dims) - design_pdn.c4_info.single_c4.diameter)/2

    assert crit_path_distance >= 0, "Crit path distance is negative"

    ####################### IR DROP USING DISCRETE INTEGRALS AND HOLISTIC APPROACH #######################
    current_per_region = current_per_sq_um * math.prod(region_dims)
    # X dimension critical path, only horizontal traversal, we use the y axis of the tsv grid to determine number of pwr rails
    pwr_rails_per_x_dim = pwr_rails_per_um * tsv_grid_bounds[1] / 2
    crit_x_distance = (region_dims[0] - tsv_grid_bounds[0]) / 2

    current_per_x_pwr_rail = (current_per_region / 4) / (pwr_rails_per_x_dim * 2) 
    pwr_rails_per_quarter_x_dim = pwr_rails_per_um * crit_x_distance

    # Y dimension critical path, only horizontal traversal, we use the y axis of the tsv grid to determine number of pwr rails
    pwr_rails_per_y_dim = pwr_rails_per_um * tsv_grid_bounds[0] / 2
    crit_y_distance = (region_dims[1] - tsv_grid_bounds[1]) / 2

    current_per_y_pwr_rail = (current_per_region / 4) / (pwr_rails_per_y_dim * 2)
 
    pwr_rails_per_quarter_y_dim = pwr_rails_per_um * crit_y_distance
    

    current_per_quarter_region = (current_per_region / 4) - (current_per_sq_um * crit_x_distance * tsv_grid_bounds[1]) / 2 - (current_per_sq_um * crit_y_distance * tsv_grid_bounds[0]) / 2

    vias_per_x_crit_path = crit_x_distance * pwr_rails_per_um #/ (design_pdn.process_info.mlayers[-1].via_pitch*1e-3)
    vias_per_y_crit_path = crit_y_distance / (design_pdn.process_info.mlayers[-1].via_pitch*1e-3)


    # traversing across the wire measuring each voltage value
    # current per via will be the amount of current that needs to be distributed in that region divided by # of rails and # of vias on that path
    current_x_per_via_stack = (current_per_sq_um * crit_x_distance * tsv_grid_bounds[1] / 2) / (pwr_rails_per_x_dim * vias_per_x_crit_path)

    current_x_per_metal_rail = (current_per_quarter_region * 0.5) / pwr_rails_per_quarter_x_dim

    wire_res_bw_vias = ((1/pwr_rails_per_um) * design_pdn.process_info.mlayers[-1].wire_res_per_um)

    #vias_per_pwr_rail = (design_pdn.process_info.mlayers[-1].via_pitch * 1e-3) / pwr_rails_per_um 
    
    x_ir_drops = []
    x_rail_currents = []
    # GETS IR DROP FOR HORIZONTAL/VERTICAL DISTANCE FROM TSV TO EDGE OF UMBRELLA
    # Assmes a single via also traverses metal pitch
    for via_idx in range(math.floor(vias_per_x_crit_path)):
        # Lost current due to via stack
        via_lost_current = (current_x_per_via_stack * via_idx)
        # Perpindicular metal lost current
        rail_lost_current = ( (current_per_quarter_region / pwr_rails_per_x_dim) * via_idx / pwr_rails_per_quarter_x_dim )
        # Current is reduced in discrete amounts as we traverse in the x direction
        x_ir_metal = (current_per_x_pwr_rail - via_lost_current - rail_lost_current) * wire_res_bw_vias
        x_ir_drops.append(x_ir_metal)
        x_rail_currents.append(current_per_x_pwr_rail - via_lost_current - rail_lost_current)
    

    # # GETS IR DROP FOR HORIZONTAL/VERTICAL DISTANCE FROM TSV TO EDGE OF UMBRELLA
    #for m_idx, current in enumerate(x_rail_currents):




    total_ir_drop = sum(x_ir_drops)


    ####################### IR DROP USING DISCRETE INTEGRALS AND HOLISTIC APPROACH #######################

    ####################### IR DROP MODELING USING POWER DENSITY AND 1D INTEGRAL OF LINEARLY DECREASING PWR #######################
    current_per_half_region = (current_per_sq_um * region_dims[0] * region_dims[1]) / 2
    # single via res / number of vias per half region
    via_res_per_half_region = single_via_stack_res / (single_via_stack_res * math.prod(region_dims) / 2)
    # J(r) = current_per_sq_um * (1 - r/R)
    # If we integrate 0 -> R (1 - r/R) dr we get R / 2 where R is the radius of the power rail or distance traveled
    # V = current_per_sq_um * (R / 2)
    # V = half_region_current * (length (R) * metal_rail_res_per_um) / (pwr_rails_per_um * 2 * R ) )
    dist_mstack_ir_drop = current_per_half_region * (1 / 2 * metal_rail_res_per_um + via_res_per_half_region ) / ( pwr_rails_per_um )
    
    # print(f"Voltage Drop Integral Calc: {dist_mstack_ir_drop}")
    ####################### IR DROP MODELING USING POWER DENSITY AND 1D INTEGRAL OF LINEARLY DECREASING PWR #######################
    ####################### IR DROP MODELING USING POWER DENSITY AND DISCRETE VIA / RESISTANCES #######################
    current_per_region = current_per_sq_um * math.prod(region_dims)
    pwr_rails_per_region_dim = pwr_rails_per_um * min(region_dims)
    # Divided by two as current is flowing through half of the region
    current_per_pwr_rail = (current_per_region / 2) / pwr_rails_per_region_dim
    # modeling half a region as a 1D line of resistances and currents
    # Floored to make sure vias dont go outside of floorplan bounds
    vias_per_crit_path = crit_path_distance / (design_pdn.process_info.mlayers[-1].via_pitch*1e-3)
    # single rail resistance between vias of wire
    wire_res_bw_vias = (design_pdn.process_info.mlayers[-1].via_pitch * 1e-3 * design_pdn.process_info.mlayers[-1].wire_res_per_um) # / (pwr_rails_per_um * min(region_dims))
    # traversing across the wire measuring each voltage value
    current_per_via_stack = current_per_pwr_rail / vias_per_crit_path
    ir_drops = []
    for ir_idx in range(math.floor(vias_per_crit_path)):
        # distance_traversed += design_pdn.process_info.mlayers[-1].via_pitch
        ir_metal = (current_per_pwr_rail - current_per_via_stack * ir_idx) * wire_res_bw_vias # + single_via_stack_res * current_per_via_stack
        ir_drops.append(ir_metal)

    # sum all ir drops measured discretely and add an additional ir drop from via stack resistance
    #total_ir_drop = sum(ir_drops) + (single_via_stack_res) * current_per_via_stack
    # 
    single_rail_res = crit_path_distance * design_pdn.process_info.mlayers[-1].wire_res_per_um
    single_rail_path_res = single_rail_res + single_via_stack_res
    
    single_rail_voltage = total_ir_drop
    ####################### IR DROP MODELING USING POWER DENSITY AND DISCRETE VIA / RESISTANCES #######################
    ####################### IR DROP MODELING USING CRITICAL PATH AND NUMBER OF TX PER RAIL #######################
    """
        txs_per_crit_region = pwr_rail_box.area / (design_pdn.process_info.tx_geom_info.min_width_tx_area * 1e-6)
        # Need the amount of current drawn for a power region, add this to current drawn for a C4 Power Region 
        current_per_crit_region = txs_per_crit_region * design_pdn.current_per_tx
        region_pwr_rail_dims = [dim*pwr_rails_per_um for dim in region_dims]
        # Number of Tx per power rail are equal to the number of txs per region divided by the dimension of the power rail, multiply by 2 because there are two metal layers for power
        tx_per_pwr_rail = txs_per_crit_region / (max(region_pwr_rail_dims)*2) #math.prod(region_pwr_rail_dims)


        # Calc resistance of single rail with critical path , single rail + via_stack / num_vias to txs
        single_rail_res = metal_rail_res_per_um * crit_path_distance #  + (single_via_stack_res / tx_per_pwr_rail)
        single_rail_path_res = single_rail_res + (single_via_stack_res / (tx_per_pwr_rail * via_stacks_per_sq_um * (design_pdn.process_info.tx_geom_info.min_width_tx_area*1e-6) )) # THIS NEEDS TO BE MULTIPLIED BY VIAS PER TX
        # total number of vias to deliver power
        # vias_per_pwr_rail_region = tx_per_pwr_rail * (max(region_pwr_rail_dims)*2) #math.prod(region_pwr_rail_dims)
        # assuming each tx takes some amount of current lets see how much voltage goes through each rail
        # (single_rail_path_res scales linearly with single_path_dist) (tx_per_pwr_rail scales quadratically w area of region)
        
        #single_rail_voltage = max([single_rail_path_res * tx_per_pwr_rail * design_pdn.current_per_tx, dist_mstack_ir_drop])
        ####################### IR DROP MODELING USING CRITICAL PATH AND NUMBER OF TX PER RAIL #######################
        # print(f"Voltage Drop Single Rail: {single_rail_voltage}")
    """
    out_dict = {
        "region_dims": region_dims,
        # "txs_per_crit_region": txs_per_crit_region,
        # "region_pwr_rail_dims": region_pwr_rail_dims, 
        # "tx_per_pwr_rail": tx_per_pwr_rail,
        "single_rail_res": single_rail_res,
        "single_rail_path_res": single_rail_path_res,
        "single_rail_voltage": single_rail_voltage,
        # "single_rail_v_calc_tx": single_rail_path_res * tx_per_pwr_rail * design_pdn.current_per_tx,
        "single_rail_v_calc_iavg": dist_mstack_ir_drop,
        "crit_path_distance": crit_path_distance,
        "current_per_crit_region": current_per_region,
        "current_per_pwr_rail": current_per_pwr_rail,
    }
    return out_dict




def find_tsv_info(design_pdn: rg_ds.DesignPDN, in_dims: List[int], axis: int):
    """
    axis = 0 rows 
    """
    tsv_out_infos = []
    ncols = in_dims[0]
    nrows = in_dims[1]
    out_dims = []
    while True:
        tsv_out_info = {}
        test_dims = [ncols, nrows]
        #This clears the plots for the next round of plotting don't ask me why I can access the tsv_grid object outside the loop (smh python)
        tsv_grids = get_tsv_placements(design_pdn, test_dims)
        calc_info = tsv_calc(tsv_grids)

        koz_bounds = [(calc_info["KOZ"]["bb"].bounds[2] - calc_info["KOZ"]["bb"].bounds[0]), (calc_info["KOZ"]["bb"].bounds[3] - calc_info["KOZ"]["bb"].bounds[1])] # x, y bb dimensions

        if koz_bounds[axis] > design_pdn.tsv_info.area_bounds[axis] or koz_bounds[axis] > design_pdn.c4_info.single_c4.diameter:
            break
        out_dims = test_dims
        tsv_rects = [ rect for t_grid in tsv_grids["TSV"] for rows in t_grid.grid for rect in rows ]
        koz_rects = [ rect for k_grid in tsv_grids["KOZ"] for rows in k_grid.grid for rect in rows ]

        tsv_rect_placements = rg_ds.PolyPlacements(
            rects = tsv_rects,
            area = calc_info["TSV"]["area"],
            bb_poly = calc_info["TSV"]["bb"],
            tag = "TSV"
        )

        koz_rect_placements = rg_ds.PolyPlacements(
            rects = koz_rects,
            area = calc_info["KOZ"]["area"],
            bb_poly = calc_info["KOZ"]["bb"],
            tag = "KOZ"
        )

        design_pdn.tsv_info.tsv_rect_placements = tsv_rect_placements
        design_pdn.tsv_info.koz_rect_placements = koz_rect_placements

        # uncomment below to calculate res using resistivity and tsv dimensions
        design_pdn.tsv_info.resistance = design_pdn.tsv_info.calc_resistance()
        
        # print(f"TSV Grid resistance {design_pdn.tsv_info.resistance*1e3} mOhms")
        # save output to tsv_output_dataframe
        # tsv_output_df = pd.concat([tsv_output_df, {"dims": ["x".join([f"{dim}" for dim in dims])], "tsv_grid_area": calc_info["TSV"]["area"], "koz_grid_area": calc_info["KOZ"]["area"], "grid_resistance": design_pdn.tsv_info.resistance}], ignore_index=True)
        tsv_out_info["dims"] = "x".join([f"{dim}" for dim in out_dims])
        if design_pdn.tsv_info.placement_setting == "dense":
            tsv_out_info["total_tsvs"] = math.prod(out_dims)
        elif design_pdn.tsv_info.placement_setting == "checkerboard":
            tsv_out_info["total_tsvs"] = math.prod(out_dims) + math.prod([dim-1 for dim in out_dims])
        else:
            raise Exception("Invalid TSV placement setting")

        tsv_out_info["tsv_grid_area (um^2)"] = calc_info["TSV"]["area"]
        tsv_out_info["koz_grid_area (um^2)"] = calc_info["KOZ"]["area"]
        tsv_out_info["grid_resistance (mOhm)"] = round(design_pdn.tsv_info.resistance*1e3,4)
        tsv_out_infos.append(tsv_out_info)
        if axis == 0:
            ncols += 1
        elif axis == 1:
            nrows += 1
        else:
            raise Exception("Invalid axis") 

    return tsv_out_infos, out_dims


def get_via_stack_info(design_pdn: rg_ds.DesignPDN, via_stack_idx: int):
    via_stack = design_pdn.process_info.via_stack_infos[via_stack_idx]
    via_pitch = design_pdn.process_info.mlayers[via_stack.mlayer_range[-1]].via_pitch
    via_stacks_per_sq_um = 1 / ((via_pitch*1e-3)**2)
    via_stacks_per_tsv = math.ceil(via_stacks_per_sq_um * design_pdn.tsv_info.single_tsv.area)
    vias_per_tsv_grid = via_stacks_per_tsv * len(design_pdn.tsv_info.tsv_rect_placements.rects)


# def gen_candidate_sector(sector_area: float, )

# def modify_pdn_dims(design_pdn: DesignPDN):
#     """
#         Modifies the dimensions of the pdn to add both PWR/GND lines
#     """


def gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height,  tsv_lb_grid_bounds: List[int], i, j, l, m, corner):
    ret_val = 0
    if "br" in corner:
        # BOTTOM RIGHT
        if i > pwr_region_lb_width - 1 - math.ceil(tsv_lb_grid_bounds[0] / 2) and j < math.ceil(tsv_lb_grid_bounds[1] / 2):
            sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "gnd"
            ret_val = 1
    if "tr" in corner:
        # TOP RIGHT
        if i > pwr_region_lb_width - 1 - math.floor(tsv_lb_grid_bounds[0] / 2) and j > pwr_region_lb_height - 1 - math.floor(tsv_lb_grid_bounds[1] / 2):
            sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "gnd"
            ret_val = 1
    if "tl" in corner:
        # TOP LEFT
        if i < math.floor(tsv_lb_grid_bounds[0] / 2) and j > pwr_region_lb_height - 1 - math.floor(tsv_lb_grid_bounds[1] / 2):
            sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "gnd"
            ret_val = 1
    if "bl" in corner:
        # BOTTOM LEFT
        if i < math.ceil(tsv_lb_grid_bounds[0] / 2) and j < math.ceil(tsv_lb_grid_bounds[1] / 2):
            sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "gnd"
            ret_val = 1

    return ret_val
    



# def expand_fan_out(grid, start_x, start_y, )


def shift_fpga_resouce(sector_pwr_region_grid: List[List[rg_ds.BlockRegion]], x_idx: int, y_idx: int, shift_dir: List[int], shift_amt: int):
    """
        - Takes in the sector_pwr_region_grid and an index of a resource to shift, as well as a specification in which direction in x or y to shift the resource
        - A resource is defined as a contiguous block of resources of the same type
        - An error will be returned if the resource collides with a non logic block resource
    """

    grid_idx_queue = deque([[x_idx, y_idx]])

    resource_idx_results = []

    x_dirs = [-1, 0, 1]
    y_dirs = [-1, 0, 1]
    x_max = len(sector_pwr_region_grid)
    y_max = len(sector_pwr_region_grid[0])
    resource_tag = sector_pwr_region_grid[x_idx][y_idx].resource_tag
    # cur_grid_idx_queue.append()
    resource_idx_results.append([x_idx, y_idx])
    if resource_tag == "lb":
        raise Exception("LB is an invalid resource to shift")
    # check adjacent resources to see if they are of the same type
    while grid_idx_queue:
        idxs = grid_idx_queue.popleft()
        cur_x = idxs[0]
        cur_y = idxs[1]
        for dx in x_dirs:
            for dy in y_dirs:
                # Dont check the current index
                if dx == 0 and dy == 0:
                    continue
                new_x = cur_x + dx
                new_y = cur_y + dy
                # make sure its not out of bounds of the grid
                if new_x < 0 or new_x >= x_max or new_y < 0 or new_y >= y_max:
                    continue      
                # if the resource is the same type as the current resource add to resource_idxs and add to expansion queue
                if sector_pwr_region_grid[new_x][new_y].resource_tag == resource_tag:
                    grid_idx_queue.append([new_x, new_y])
                    resource_idx_results.append([new_x, new_y])

    y_idxs = [idx[1] for idx in resource_idx_results]
    min_x_idx = min(resource_idx_results, key=lambda x: x[0])[0]
    max_x_idx = max(resource_idx_results, key=lambda x: x[0])[0]
    x_idxs = [idx[0] for idx in resource_idx_results]
    min_y_idx = min(resource_idx_results, key=lambda x: x[1])[1]
    max_y_idx = max(resource_idx_results, key=lambda x: x[1])[1]

    # Left Shift
    if shift_dir[0] == -1 and shift_dir[1] == 0:
        # For left shift we add a column of resources to the left of the resource and remove a column to the right, replace with LBs
        # Check if the left shift is valid
        if min_x_idx - shift_amt < 0:
            raise Exception("Invalid left shift goes below 0 in grid")
        for y in y_idxs:
            if sector_pwr_region_grid[min_x_idx - shift_amt][y].resource_tag != "lb":
                raise Exception("Invalid left shift collides with non LB resource")
        # Now that we know shift is valid we can perform shift
        for x in range(1, shift_amt+1):
            for y in y_idxs:
                # Adding columns on the left
                sector_pwr_region_grid[min_x_idx - x][y].resource_tag = resource_tag
                # Removing columns on the right
                sector_pwr_region_grid[max_x_idx - x - 1][y].resource_tag = "lb"
    # Right Shift
    if shift_dir[0] == 1 and shift_dir[1] == 0:
        # For left shift we add a column of resources to the left of the resource and remove a column to the right, replace with LBs
        # Check if the left shift is valid
        if max_x_idx + shift_amt > len(sector_pwr_region_grid):
            raise Exception("Invalid right shift goes above max in grid")
        for y in y_idxs:
            if sector_pwr_region_grid[max_x_idx + shift_amt][y].resource_tag != "lb":
                raise Exception("Invalid right shift collides with non LB resource")
        # Now that we know shift is valid we can perform shift
        for x in range(1, shift_amt+1):
            for y in y_idxs:
                # Adding columns on the right
                sector_pwr_region_grid[max_x_idx + x][y].resource_tag = resource_tag
                # Removing columns on the left
                sector_pwr_region_grid[min_x_idx + x - 1][y].resource_tag = "lb"

    return sector_pwr_region_grid
                









def generate_fpga_sectors(design_pdn: rg_ds.DesignPDN):
    """
    1. Create a possibly sloppy floorplan which does not 
    Requirements:
     - Each row of power regions inside of a sector must be repeatable 
     - regularity should be maximized 
    Notes:
     - It is good intially to try and only remove LB regions as its the most granular resource
    Assumptions:
     - The TSV blockages will be arranged in a checkerboard pattern w.r.t PWR and GND regions
    """
    # TODO make the keys of this dict come from the FPGA info class instead of hardcoding
    target_sector_resources = {
        "lbs": design_pdn.fpga_info.lbs.total_num / math.prod(design_pdn.fpga_info.sector_dims),
        "dsps": design_pdn.fpga_info.dsps.total_num / math.prod(design_pdn.fpga_info.sector_dims),
        "brams": design_pdn.fpga_info.brams.total_num / math.prod(design_pdn.fpga_info.sector_dims),
    }


    # Divide the chip into sectors, initial sector area is derived from the floorplan
    init_sector_area = design_pdn.floorplan.area / math.prod(design_pdn.fpga_info.sector_dims) # um^2
    
    # ceil to put as many LBs as possible (could be floored I think its a choice)
    init_sector_lb_width = math.ceil(math.sqrt(init_sector_area) / design_pdn.fpga_info.lbs.abs_width)
    init_sector_lb_height = math.ceil(math.sqrt(init_sector_area) / design_pdn.fpga_info.lbs.abs_height)
    
    # Find number of power regions that fit in total sector
    pwr_regions_per_sector = math.prod(design_pdn.c4_info.pdn_dims) / math.prod(design_pdn.fpga_info.sector_dims)
    
    # get power regions bounds in terms of logic blocks
    pwr_region_lb_width = math.ceil(design_pdn.pwr_region_dims[0] / design_pdn.fpga_info.lbs.abs_width)
    pwr_region_lb_height = math.ceil(design_pdn.pwr_region_dims[1] / design_pdn.fpga_info.lbs.abs_height)


    # Get tsv grid bounds in terms of logic blocks
    tsv_grid_bounds = [abs(design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[2] - design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[0]),abs(design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[3] - design_pdn.tsv_info.tsv_rect_placements.bb_poly.bounds[1])]
    tsv_lb_grid_bounds = [math.ceil(tsv_grid_bounds[0] / design_pdn.fpga_info.lbs.abs_width), math.ceil(tsv_grid_bounds[1] / design_pdn.fpga_info.lbs.abs_height)]

    # To make the tsv grid centered we will make sure that the power region dimensions are even or odd depending on if the TSV grid is even or odd
    # After this assuming all sectors are comprised of power grids the final dimensions of a sector will change, we will have to adjust for that
    if tsv_lb_grid_bounds[0] % 2 == 0 and pwr_region_lb_width % 2 != 0 or tsv_lb_grid_bounds[0] % 2 != 0 and pwr_region_lb_width % 2 == 0:
        # If theres a mismatch we can reduce dimension of the pwr region as this should only reduce IR drop
        pwr_region_lb_width -= 1
    if tsv_lb_grid_bounds[1] % 2 == 0 and pwr_region_lb_height % 2 != 0 or tsv_lb_grid_bounds[1] % 2 != 0 and pwr_region_lb_height % 2 == 0:
        # If theres a mismatch we can reduce dimension of the pwr region as this should only reduce IR drop
        pwr_region_lb_height -= 1


    ############################## DETERMINE RESOURCE COLUMNS AND DIMENSIONS TO MATCH TARGET RESOURCES ##############################
    # ceil as we want the sector to be a factor of power regions
    pwr_region_grid_width = math.ceil(init_sector_lb_width / pwr_region_lb_width)
    pwr_region_grid_height = math.ceil(init_sector_lb_height / pwr_region_lb_height)
    sector_lb_width = pwr_region_grid_width * pwr_region_lb_width 
    sector_lb_height = pwr_region_grid_height * pwr_region_lb_height

    # determine appropriate number of columns for non lb resources which lets us meet our targets
    # ceil to get as many as possible as we will possibly lose some due to tsv placement
    num_dsp_cols = math.ceil(target_sector_resources["dsps"] / init_sector_lb_height)
    num_bram_cols = math.ceil(target_sector_resources["brams"] / init_sector_lb_height)

    dsps_per_pwr_region_grid_row = pwr_region_lb_height * num_dsp_cols
    brams_per_pwr_region_grid_row = pwr_region_lb_height * num_bram_cols

    percent_diff_dsps = (dsps_per_pwr_region_grid_row * pwr_region_grid_height - target_sector_resources["dsps"]) / target_sector_resources["dsps"]
    percent_diff_brams = (brams_per_pwr_region_grid_row * pwr_region_grid_height - target_sector_resources["brams"]) / target_sector_resources["brams"]
    percent_diff_lbs = (sector_lb_width * sector_lb_height - target_sector_resources["lbs"]) / target_sector_resources["lbs"]
    # if per differences are larger than 1 / grid height (factor which determines number of resources, keep downsizing until they fall below number of resources)
    cur_cost = sys.float_info.max
    best_floorplan_info = {}
    while abs(percent_diff_dsps) >= 0.05 or abs(percent_diff_brams) >= 0.05:
        # Cost function
        # prev_cost = cur_cost
        # cur_cost = abs(percent_diff_dsps) + abs(percent_diff_brams) + abs(percent_diff_lbs)
        # if cur_cost < prev_cost:
        #     best_floorplan_info["pwr_region_lb_height"] = pwr_region_lb_height
        #     best_floorplan_info["pwr_region_lb_width"] = pwr_region_lb_width
        #     best_floorplan_info["pwr_region_grid_width"] = pwr_region_grid_width
        #     best_floorplan_info["pwr_region_grid_height"] = pwr_region_grid_height
        #     best_floorplan_info["num_dsp_cols"] = num_dsp_cols
        #     best_floorplan_info["num_bram_cols"] = num_bram_cols

        # determine sector height by resource columns
        if percent_diff_dsps > 0 or percent_diff_brams > 0:
            pwr_region_lb_height -= 1
        else:
            pwr_region_lb_height += 1

        num_dsp_cols = math.ceil(target_sector_resources["dsps"] / sector_lb_height)
        num_bram_cols = math.ceil(target_sector_resources["brams"] / sector_lb_height)
        sector_lb_height = pwr_region_lb_height * pwr_region_grid_height
        sector_lb_width = pwr_region_lb_width * pwr_region_grid_width
        num_dsps = sector_lb_height * num_dsp_cols
        num_brams = sector_lb_height * num_bram_cols
        percent_diff_dsps = (num_dsps - target_sector_resources["dsps"]) / target_sector_resources["dsps"]    
        percent_diff_brams = (num_brams - target_sector_resources["brams"]) / target_sector_resources["brams"]


    num_dsps = sector_lb_height * num_dsp_cols
    num_brams = sector_lb_height * num_bram_cols
    num_lbs = (sector_lb_height * sector_lb_width) - num_dsps * design_pdn.fpga_info.dsps.rel_area - num_brams * design_pdn.fpga_info.brams.rel_area
    percent_diff_lbs = (num_lbs - target_sector_resources["lbs"]) / target_sector_resources["lbs"]
    
    while abs(percent_diff_lbs) >= 0.10:
        # prev_cost = cur_cost
        # cur_cost = abs(percent_diff_dsps) + abs(percent_diff_brams) + abs(percent_diff_lbs)
        # if cur_cost < prev_cost:
        #     best_floorplan_info["pwr_region_lb_height"] = pwr_region_lb_height
        #     best_floorplan_info["pwr_region_lb_width"] = pwr_region_lb_width
        # determine sector height by resource columns
        if percent_diff_lbs > 0:
            pwr_region_lb_width -= 1
        else:
            pwr_region_lb_width += 1
        sector_lb_height = pwr_region_lb_height * pwr_region_grid_height
        sector_lb_width = pwr_region_lb_width * pwr_region_grid_width
        num_lbs = (sector_lb_height * sector_lb_width) - num_dsps * design_pdn.fpga_info.dsps.rel_area - num_brams * design_pdn.fpga_info.brams.rel_area
        percent_diff_lbs = (num_lbs - target_sector_resources["lbs"]) / target_sector_resources["lbs"]


    # sector_lb_height = pwr_region_lb_height * pwr_region_grid_height
    # sector_lb_width = pwr_region_lb_width * pwr_region_grid_width

    # Number of column spacing between power regions is equal to the power region dim - 1
    # Assign FPGA resource columns to available column regions in alternating fashion
    # TODO afterwards we should try to create a larger amount of spacing between the columns if such a luxary exists
    resource_cols = []
    used_dsp_cols = num_dsp_cols
    used_bram_cols = num_bram_cols
    resource_options = ["bram","dsp"]
    resource_idx = 0
    # len(resource_cols) < pwr_region_grid_width and
    while used_bram_cols > 0 or used_dsp_cols > 0:
        if resource_options[resource_idx] == "bram" and used_bram_cols > 0:
            resource_cols.append("bram")
            used_bram_cols -= 1
        elif resource_options[resource_idx] == "dsp" and used_dsp_cols > 0:
            resource_cols.append("dsp")
            used_dsp_cols -= 1
        # else:
        #     resource_cols.append("lb")
        resource_idx = (resource_idx + 1) % len(resource_options)
    # For now we will assume that 


    # first put down the stripes of resources and logic blocks into the sector
    sector_pwr_region_grid = []
    for i in range(sector_lb_width):
        col_list = []
        for j in range(sector_lb_height):
            block_region = rg_ds.BlockRegion(
                resource_tag = "lb",
                sector_coord = rg_ds.Coord(
                    x = i,
                    y = j,
                ),
                pwr_region_coord = rg_ds.Coord(
                    x = math.floor(i / sector_lb_width),
                    y = math.floor(j / sector_lb_height),
                ),
            )
            col_list.append(block_region)
        sector_pwr_region_grid.append(col_list)


    # Assign PWR/GND TSVs and columns of resources to the sector
    pwr_row_idxs = []
    pwr_gnd_col_idxs = []
    resource_idx = 0

    # pwr_region_grid_infos = [[pwr_region_grid_info]*pwr_region_grid_height]*pwr_region_grid_width
    for l in range(pwr_region_grid_width):
        # used_gnd_resources_cols = []
        for m in range(pwr_region_grid_height):
            # print(vertical_region_border)
            sector_used_gnd = 0
            for i in range(pwr_region_lb_width):
                for j in range(pwr_region_lb_height):
                    # Check if index is in bounds of TSV PWR holes
                    if i > math.ceil((pwr_region_lb_width - tsv_lb_grid_bounds[0]) / 2) - 1 and j > math.ceil((pwr_region_lb_height - tsv_lb_grid_bounds[1])/ 2) -1 and i < math.ceil((pwr_region_lb_width + tsv_lb_grid_bounds[0])/ 2) and j < math.ceil((pwr_region_lb_height + tsv_lb_grid_bounds[1]) / 2) :
                        sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "pwr"
                        pwr_row_idxs.append(j)
                        pwr_gnd_col_idxs.append(l * pwr_region_lb_width + i)
                    # Place TSV GND holes at corner of sector, if odd sized tsv grid then place it on the left pwr region
                    # if pwr_region_grid_infos[l][m]["placed_gnd"] < math.prod(tsv_lb_grid_bounds):
                    # CORNER BOTTOM LEFT pwr region so we only want to do top right placement
                    if l == 0 and m == 0:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["tr"])
                    # CORNER BOTTOM RIGHT
                    elif l == pwr_region_grid_width - 1 and m == 0:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["tl"])
                    # CORNER TOP RIGHT
                    elif l == pwr_region_grid_width - 1 and m == pwr_region_grid_height - 1:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["bl"])
                    # CORNER TOP LEFT
                    elif l == 0 and m == pwr_region_grid_height - 1:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["br"])
                    # LEFT EDGE
                    elif l == 0: 
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["tr","br"])
                    # TOP EDGE
                    elif m == pwr_region_grid_height - 1:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["bl", "br"])
                    # RIGHT EDGE
                    elif l == pwr_region_grid_width - 1:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["tl", "bl"])
                    # BOTTOM EDGE
                    elif m == 0:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["tl", "tr"])
                    else:
                        sector_used_gnd = gnd_placements(sector_pwr_region_grid, pwr_region_lb_width, pwr_region_lb_height, tsv_lb_grid_bounds, i, j, l, m, ["tl", "tr", "bl", "br"])
                    
                    if sector_used_gnd > 0:
                        pwr_gnd_col_idxs.append(l * pwr_region_lb_width + i)

                    # Assign resources into columns, they will be grouped as close to the border of the power sector as possible 
                    # Resource columns on the right side of the sector
                    """
                    elif resource_cols[resource_idx] == "bram" and resource_idx != len(resource_cols)-1 and i >= pwr_region_lb_width - math.ceil(design_pdn.fpga_info.brams.rel_area / 2):
                        sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "bram"
                    elif resource_cols[resource_idx] == "dsp" and resource_idx != len(resource_cols)-1 and i >= pwr_region_lb_width - math.ceil(design_pdn.fpga_info.dsps.rel_area / 2):
                        sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "dsp"
                    # Resource columns on the right side of the sector
                    elif resource_idx > 0 and resource_cols[resource_idx - 1] == "bram" and i < math.floor(design_pdn.fpga_info.brams.rel_area / 2):
                        sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "bram"
                    elif resource_idx > 0 and resource_cols[resource_idx - 1] == "dsp" and i < math.floor(design_pdn.fpga_info.dsps.rel_area / 2):
                        sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag = "dsp"
                    """
                    # print(f"{sector_pwr_region_grid[l * pwr_region_grid_width + i][m * pwr_region_grid_height + j].resource_tag: ^}")
            # pwr_region_grid_infos[l][m]["placed_gnd"] = sector_used_gnd
        # resource_idx += 1

    pwr_gnd_col_idxs = sorted(list(set(pwr_gnd_col_idxs)))

    valid_col_placement_idxs = []
    for idx1, idx2 in pairwise(pwr_gnd_col_idxs):
        if idx2 - idx1 != 1:
            valid_col_placement_idxs.append(idx1+1)
    
    
    
    pwr_gnd_x_max_dist = math.ceil(pwr_region_lb_width / 2) - math.ceil(tsv_lb_grid_bounds[0] / 2)
    pwr_gnd_x_min_dist = math.floor(pwr_region_lb_width / 2) - math.floor(tsv_lb_grid_bounds[0] / 2)

    resource_idx = 0
    cols_to_place = 0
    spacing_inc = 2
    col_placement_idx = resource_idx
    # Placement of FPGA column resources
    for i in range(sector_lb_width):
        for j in range(sector_lb_height):
            if i == valid_col_placement_idxs[col_placement_idx] and resource_idx < len(resource_cols):
                if resource_cols[resource_idx] == "bram":
                    cols_to_place = design_pdn.fpga_info.brams.rel_area
                    resource_tag = "bram"
                    resource_idx += 1
                elif resource_cols[resource_idx] == "dsp":
                    cols_to_place = design_pdn.fpga_info.dsps.rel_area
                    resource_tag = "dsp"
                    resource_idx += 1
                # is there enough space to place the rest of the resource columns and add additional spacing?
                #if len(valid_col_placement_idxs)-1 > col_placement_idx + spacing_inc: #+ (resource_idx - len(resource_cols)-1):
                #    col_placement_idx += spacing_inc
                if col_placement_idx < len(valid_col_placement_idxs)-1:
                    col_placement_idx += 1
                    
            if cols_to_place > 0:
                # if sector_pwr_region_grid[i][j].resource_tag != "lb":
                #     shift_fpga_resouce(sector_pwr_region_grid, i, j, [1,0], 1)
                sector_pwr_region_grid[i][j].resource_tag = resource_tag
        cols_to_place -= 1

    # Now print out the new dimensions of the sector and resouce count
    floorplan_out = {}
    floorplan_out["Sector LB Dimensions"] = f"{sector_lb_width}x{sector_lb_height}"
    floorplan_out["Sector Area (um^2)"] = sector_lb_width * sector_lb_height * design_pdn.fpga_info.lbs.abs_width * design_pdn.fpga_info.lbs.abs_height
    num_lbs = 0
    num_dsps = 0
    num_brams = 0
    for i in range(sector_lb_width):
        for j in range(sector_lb_height):
            if sector_pwr_region_grid[i][j].resource_tag == "lb":
                num_lbs += 1
            elif sector_pwr_region_grid[i][j].resource_tag == "dsp":
                num_dsps += 1
            elif sector_pwr_region_grid[i][j].resource_tag == "bram":
                num_brams += 1

    floorplan_out["# LBs"] = num_lbs
    floorplan_out["# DSPs"] = int(num_dsps / design_pdn.fpga_info.dsps.rel_area)
    floorplan_out["# BRAMs"] = int(num_brams / design_pdn.fpga_info.brams.rel_area)
    floorplan_out["% Change in LBs"] = f"{((num_lbs - target_sector_resources['lbs']) / target_sector_resources['lbs']) * 100}%"
    floorplan_out["% Change in DSPs"] = f"{((num_dsps / design_pdn.fpga_info.dsps.rel_area - target_sector_resources['dsps']) / target_sector_resources['dsps']) * 100}%"
    floorplan_out["% Change in BRAMs"] = f"{((num_brams / design_pdn.fpga_info.brams.rel_area - target_sector_resources['brams']) / target_sector_resources['brams']) * 100}%"


    floorplan_out_df = pd.DataFrame(floorplan_out, index=[0])
    for l in rg_utils.get_df_output_lines(floorplan_out_df):
        print(l)



    """
    pwr_row_idxs = list(set(pwr_row_idxs))
    
    # create a way to find distances between non LB resources and borders of device (x distances the most important as resources are in columns)
    # Only using first row of pwr region to get these

    resource_col_infos = []
    free_lb_x_idx_ranges = []

    j = pwr_row_idxs[0]
    last_non_lb_idx = -1
    start_res = "edge"
    for i in range(sector_lb_width):
        if i == sector_lb_width - 1:
            end_res = "edge"
        else:
            end_res = sector_pwr_region_grid[i][j].resource_tag

        idx_range = {
            "start": last_non_lb_idx + 1,
            "start_res": start_res,
            "end": i - 1,
            "end_res": end_res,
            "size": i - 1 - last_non_lb_idx,
        }

        # Assumes no pwr blocks on the edges of the device TODO maybe this is unsafe
        # We only care about indexes which are on power rows
        # Lb block to left of non lb block
        if j in pwr_row_idxs and sector_pwr_region_grid[i][j].resource_tag != "lb" and sector_pwr_region_grid[i-1][j].resource_tag == "lb":
            # Look at resource column wiggle room
            if len(free_lb_x_idx_ranges) > 0:
                resource_col_infos.append(
                    {
                        "left_dist": free_lb_x_idx_ranges[-1]["size"],
                        "right_dist": idx_range["size"],
                        "resource_tag": sector_pwr_region_grid[i][j].resource_tag,
                    }
                )
            free_lb_x_idx_ranges.append(idx_range)
            start_res = sector_pwr_region_grid[i][j].resource_tag

        if sector_pwr_region_grid[i][j].resource_tag != "lb":
            last_non_lb_idx = i
    """

    # Now we can look at the wiggle room and place unplaced resource columns between tsv holes OR place them at the edges 
    # For now we will just place at the edges on the condition that there is a single lb column between the very edge, else look for wiggle room
        

    # Now if there are any additional columns in resource cols we need to assign them to the grid
    
    print("*"*100 + "FPGA FLOORPLAN" + "*"*100)
    horizontal_region_border = "+" + ("-"*(5 + 1)*pwr_region_lb_width + "+") * pwr_region_grid_width
    for m in range(pwr_region_grid_height-1, -1, -1):
        print(horizontal_region_border)
        for j in range(pwr_region_lb_height-1, -1, -1):
            for l in range(pwr_region_grid_width):
                print("|", end="")
                for i in range(pwr_region_lb_width):
                    #print(f"[{i:>{3}},{j:>{3}}]:{sector_pwr_region_grid[i][j].resource_tag:<{5}} ", end="")
                    print(f"{sector_pwr_region_grid[l * pwr_region_lb_width + i][m * pwr_region_lb_height + j].resource_tag:<{5}} ", end="")
                    if i == pwr_region_lb_width - 1 and l == pwr_region_grid_width - 1:
                        print("|")
    print(horizontal_region_border)

            

    # Get the maximum possible dimensions for the power regions based on the floorplan LB dimensions
    # max_pwr_regions_lb_width = math.floor(init_sector_lb_width / pwr_regions_per_sector)


    # from the tsv lb bounds if the pwr_region_lb_dims are not large enough to have 




    # Place the PWR and GND C4 Grids
    # There will be twice as many as currently in the c4_info dimensions


    # Determine indexes which will have column resources placed
    #resource_col_idxs 
    # Assign Columns of resources to the sector
    # for row in range(design_pdn.fpga_info.sector_dims[0]):
    #     for col in range(design_pdn.fpga_info.sector_dims[1]):



    






def calc_tsv_grid_to_top_metal_via_stack(design_pdn: rg_ds.DesignPDN, pwr_rail_pitch: float):
    """
    This function takes the dimensions of TSV grid and determines the number of vias that can be placed on each intermediate metal layer and finds total resistance
    pwr_rail_pitch is in nm and is the distance between parallel wires in power grid layer
    """

    # Assume that pwr_rail_pitch > top metal via pitch

    ######################################## INTERMEDIATE VIA STACKS ########################################
    # use via stack to get to intermediate metal layers, via pitches can be denser
    # select the intermediate metal layer (via stacks are seperated by pitch so -2 would be the second highest metal pitch)
    inter_metal_via_stack = design_pdn.process_info.via_stack_infos[-2]
    # Take the via pitch from the metal layer indexed with the highest metal in the range of the via stack
    # via pitch in (nm)
    inter_via_pitch = design_pdn.process_info.mlayers[inter_metal_via_stack.mlayer_range[-1]].via_pitch
    # calculate via stacks per / um^2
    via_stacks_per_sq_um = 1 / ((inter_via_pitch*1e-3)**2)
    # calculate vias per tsv, assuming ceil as we could expand M1 to match vias that went over edge of tsvs
    via_stacks_per_tsv = math.floor(via_stacks_per_sq_um * design_pdn.tsv_info.single_tsv.area)
    # calculate # vias to intermediate metal layer
    inter_vias_per_tsv_grid = via_stacks_per_tsv * len(design_pdn.tsv_info.tsv_rect_placements.rects)
    inter_via_stack_res = sum([via_stack.res for via_stack in design_pdn.process_info.via_stack_infos[:-2]])
    inter_via_grid_res = inter_via_stack_res / inter_vias_per_tsv_grid
    # Now calc via stack from inter via grid to actual power rail
    ######################################## TOP VIA STACKS ########################################
    pwr_connecting_via_stack = design_pdn.process_info.via_stack_infos[-1]
    # pwr_connecting_via_pitch = design_pdn.process_info.mlayers[pwr_connecting_via_stack.mlayer_range[-1]].via_pitch
    via_stacks_per_sq_um = 1 / ((pwr_rail_pitch*1e-3)**2)
    # Assuming that we dedicate the metal area on intermediate layer equivalent to TSV area for the upper vias
    via_stacks_per_tsv = math.floor(via_stacks_per_sq_um * design_pdn.tsv_info.single_tsv.area)
    via_stacks_per_tsv_grid = via_stacks_per_tsv * len(design_pdn.tsv_info.tsv_rect_placements.rects)
    top_via_grid_res = pwr_connecting_via_stack.res / via_stacks_per_tsv_grid

    total_via_res = inter_via_grid_res + top_via_grid_res
    
    return total_via_res




def pdn_modeling(ic_3d_info: rg_ds.Ic3d):
    # Look at single grid of TSVs (unseperated by C4 bumps)
    tsv_out_infos = []
    # starting dimension to look for TSV grid
    ncols = 1        
    nrows = 1
    # koz_bounds = [0, 0]
    dims = [ncols, nrows]

    tsv_out_infos_cols, out_dims = find_tsv_info(ic_3d_info.design_pdn, dims, axis = 0)
    tsv_out_infos_rows, out_dims = find_tsv_info(ic_3d_info.design_pdn, out_dims, axis = 1)

    tsv_out_infos = tsv_out_infos_cols + tsv_out_infos_rows
        
    ic_3d_info.design_pdn.tsv_info.dims = out_dims
    print("************************ CONSTANT INFO ************************")
    tsv_constants = {
        "Placement Parameter": ic_3d_info.design_pdn.tsv_info.placement_setting,
    }
    constant_out_df = pd.DataFrame(tsv_constants, index=[0])
    for l in rg_utils.get_df_output_lines(constant_out_df):
        print(l)
    print("************************ TSV GRID INFO ************************")
    tsv_output_df = pd.DataFrame(tsv_out_infos)
    for l in rg_utils.get_df_output_lines(tsv_output_df): 
        print(l)

    if ic_3d_info.pdn_sim_settings.plot_settings["tsv_grid"]:
        fig = go.Figure()
        ic_3d_info.design_pdn.tsv_info.koz_rect_placements.gen_fig(fig, fill_color = "red", opacity = 0.1)
        ic_3d_info.design_pdn.tsv_info.tsv_rect_placements.gen_fig(fig, fill_color = "blue", opacity = 0.5)
        fig.update_layout(
            title=f"{(ic_3d_info.design_pdn.tsv_info.placement_setting).upper()} TSV Grid Placement on a single C4 bump",
            xaxis_title="X (um)",
            yaxis_title="Y (um)",
            legend_title="Box Types",
            showlegend=True,
        )
        fig.show()

    # Multiply the pitch by 2 to simulate interleaving of pwr and ground rails TODO make this a setting
    max_rails_per_um = 1 / (ic_3d_info.design_pdn.process_info.mlayers[-1].pitch * 2 * 1e-3)

    # Determine pitch of metal rail regions based on the user inputted metal layer usage
    ################## USING FACTORS OF CPP AND USER INPUTTED MLAYER USAGE TO DETERMINE PWR RAILS PER UM ##################
    mlayer_usage = 1.00
    pitch_factor = 1
    pwr_rails_per_um = 1 / (ic_3d_info.design_pdn.process_info.mlayers[-1].pitch*pitch_factor*1e-3)
    # So we have the ability to space the PDN metal layers as close or far together (disregarding possible DRC violations)
    # Run the RC calculation tools from [https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=827350]
    """
        r_calc_out = sp.run(["python3",pdn_modeling_info.r_script_path,"--pitch",f"{design_pdn.process_info.mlayers[-1].pitch}","--w_percent_pitch",f"{design_pdn.pwr_rail_info.mlayer_dist[-1]}","--t_barrier",f"{1.5}","--h",f"{design_pdn.process_info.mlayers[-1].height}"],stdout = sp.PIPE, stderr = sp.PIPE)
        stdout = r_calc_out.stdout.decode("utf-8")
        ohm_per_um = -1
        for line in stdout.split("\n"):
            if "Res" in line:
                ohm_per_um = float(line.split(" ")[-2])
        c_calc_out = sp.run(["python3",pdn_modeling_info.c_script_path,"--pitch",f"{design_pdn.process_info.mlayers[-1].pitch}","--w_percent_pitch",f"{design_pdn.pwr_rail_info.mlayer_dist[-1]}","--h",f"{design_pdn.process_info.mlayers[-1].height}","--eps_rel",f"{2.9}"],stdout = sp.PIPE, stderr = sp.PIPE)
        stdout = c_calc_out.stdout.decode("utf-8")
        fF_per_um = -1
        for line in stdout.split("\n"):
            if "Ct" in line:
                fF_per_um = float(line.split(" ")[-2])
    """
    # Now we have accurate RC for whatever percentage of the pitch metal width we want

    # pwr_rail_pitch = None
    while True:
        # Doesnt make sense to use cpp when the layers are in factor of top metal pitch
        pwr_rails_per_um = (1 / (ic_3d_info.design_pdn.process_info.mlayers[-1].pitch*pitch_factor*1e-3) )
        mlayer_usage = pwr_rails_per_um / max_rails_per_um
        if mlayer_usage <= ic_3d_info.design_pdn.pwr_rail_info.mlayer_dist[-1]:
            break
        pitch_factor += 1

    pwr_rail_pitch = ic_3d_info.design_pdn.process_info.mlayers[-1].pitch*pitch_factor

    # Assume we need 2 metal layers for each set of PWR/GND power rails (X,Y directions)
    pwr_rails_per_um *= (ic_3d_info.design_pdn.pwr_rail_info.num_mlayers / 2)
    # Based on the number of rails per sq um 
    # CPP
    ## via_stacks_per_sq_um = 1 / ((design_pdn.process_info.contact_poly_pitch*cpp_factor*1e-3) ** 2) # 1 via stack per pitch of metal rail (32 x CPP) = 32x54nm
    ## pwr_rails_per_um = 1 / (design_pdn.process_info.contact_poly_pitch*cpp_factor*1e-3)
    # PITCH

    ###################################### VIA RES INFO ######################################
    via_grid_res = calc_tsv_grid_to_top_metal_via_stack(ic_3d_info.design_pdn, pwr_rail_pitch)
    # deprecated below TODO remove
    via_stack_resistances = [via_stack_info.res for via_stack_info in ic_3d_info.design_pdn.process_info.via_stack_infos]
    single_via_stack_res = sum(via_stack_resistances) # [0:len(via_stack_resistances)-1]                   
    """
    via_stacks_per_sq_um = 1 / ((design_pdn.process_info.mlayers[-1].pitch*pitch_factor*1e-3) ** 2)

    via_stack_resistances = [via_stack_info.res for via_stack_info in design_pdn.process_info.via_stack_infos]
    # single via stack from active -> top 2 metal layers
    single_via_stack_res = sum(via_stack_resistances) # [0:len(via_stack_resistances)-1]
    # Gets to metal 8
    # vias / 1 tsv
    vias_per_tsv = math.floor(via_stacks_per_sq_um * (design_pdn.tsv_info.single_tsv.diameter ** 2))
    # tsvs / 1 grid
    # Old way using tsv grid
    # num_tsvs_per_grid = math.prod(design_pdn.tsv_info.tsv_grid.dims)
    num_tsvs_per_grid = len(design_pdn.tsv_info.tsv_rect_placements.rects)
    # vias / 1 grid
    vias_per_tsv_grid =  math.floor(vias_per_tsv * num_tsvs_per_grid)
    """
    # current A / um ^ 2
    current_per_sq_um = (ic_3d_info.design_pdn.power_budget / ic_3d_info.design_pdn.supply_voltage) / (ic_3d_info.design_pdn.floorplan.area)


    ############## TOP DIE PDN ##############
    # We want to do the same thing as on the bottom die except using the top die's ubumps as the C4 based power regions
    ubump_pitches = [55, 40, 36, 25, 10 ,5 , 1] 
    # https://ieeexplore.ieee.org/ielaam/5503870/8874597/8778761-aam.pdf?tag=1 -> Power Delivery Network Modeling and Benchmarking For Emerging Heterogeneous Integration Technologies
    #ubump_resistances = [(30.9e-3 * (40/pitch)**2 ) for pitch in ubump_pitches]  # scaling resistance from ubump value at 40 um pitch, quadratic scaling as cross sectional area decreases
    ubump_resistances = [8.26, 15.63, 19.29, 40, 99, 17, 97] #mOhm 
    summary_out_infos = []
    # ubump_resistivity = 1.72e-2 #Ohm um
    for pitch, res in zip(ubump_pitches, ubump_resistances):
        single_ubump_info = rg_ds.SingleUbumpInfo(
            pitch = pitch,
            diameter = pitch/2,
            height = pitch/2,
            resistance=res,
            # resistivity=ubump_resistivity
        )
        ic_3d_info.design_pdn.ubump_info.single_ubump = single_ubump_info
        ic_3d_info.design_pdn.update()
        ubump_out_infos = []
        ir_drop_out_infos = []
        # C4 Dimension Sweep
        c4_dim = 1
        # c4_dim_y = 1
        # Ubump Dimension Sweep
        dim = 1

        top_metal_rail_res = ic_3d_info.design_pdn.process_info.mlayers[-1].wire_res_per_um
        # print(f"Top Metal Rail Resistance: {top_metal_rail_res}")
        num_c4s_list = []
        num_ubumps_list = []
        while True:
            # Ubump Dimension Sweep
            ubump_dims = [dim, dim]
            c4_dims = [c4_dim, c4_dim]
            # Used for plotting values against PDN parameters
            num_c4s_list.append(math.prod(c4_dims))
            num_ubumps_list.append(math.prod(ubump_dims))
            ##################################
            # region_info = get_c4_placements_new(design_pdn, c4_dims)

            ubump_info = get_res_info_from_dims(ic_3d_info.design_pdn, ubump_dims, top_metal_rail_res, single_via_stack_res, pwr_rails_per_um, current_per_sq_um, region_info = None, source = "ubump") 
            c4_info = get_res_info_from_dims(ic_3d_info.design_pdn, c4_dims, top_metal_rail_res, single_via_stack_res, pwr_rails_per_um, current_per_sq_um, region_info = None, source = "c4") 
            
            # Info for IR Drop on each stage of the PDN
            bot_ir_drop_info = {}
            top_ir_drop_info = {}

            ubump_out_info = {}
            
            # Calculate Via stack resistance from TSV grid

            c4_res = (ic_3d_info.design_pdn.c4_info.single_c4.resistance + ic_3d_info.design_pdn.tsv_info.resistance) + via_grid_res
            # ubump resistance in mOhm
            ubump_res = c4_res + (ic_3d_info.design_pdn.ubump_info.single_ubump.resistance*1e-3)
            
            # ceil as the only thing holding us back from using more microbumps is the metal resistance
            num_ubumps_per_pwr_region = math.ceil(( 1 /((ic_3d_info.design_pdn.ubump_info.single_ubump.pitch)**2))*ic_3d_info.design_pdn.tsv_info.tsv_rect_placements.bb_poly.area)
            # We need to know how many Top die regions are inside of each bottom die region
            #top_regions_per_bot_region = math.prod(c4_info["region_dims"]) / math.prod(ubump_info["region_dims"])
            top_regions_per_bot_region = 1 
            # Now we get the amount of current for top region and bottom region (both being fed by 1 C4 bump)
            c4_current_draw = ( top_regions_per_bot_region * ubump_info["current_per_crit_region"] ) + c4_info["current_per_crit_region"]
            
            bottom_die_ir_drop = (c4_res * c4_current_draw) + c4_info["single_rail_voltage"]
            top_die_ir_drop = (c4_res * c4_current_draw) + ((ubump_res / num_ubumps_per_pwr_region) * ubump_info["current_per_crit_region"]) + ubump_info["single_rail_voltage"]

            # Save info into struct
            ic_3d_info.design_pdn.c4_info.pdn_dims = c4_dims

            # IMPORTANT INFO
            ########################## RESISTANCE INFO ##########################
            ubump_out_info["Ubump Dims"] = "x".join([f"{dim}" for dim in ubump_dims])
            ubump_out_info["C4 Dims"] = "x".join([f"{dim}" for dim in c4_dims])

            ubump_out_info["C4 Bump Res (Ohm)"] = ic_3d_info.design_pdn.c4_info.single_c4.resistance
            ubump_out_info["C4 Bump IR Drop (V)"] = ic_3d_info.design_pdn.c4_info.single_c4.resistance * c4_current_draw

            ubump_out_info["Ubump Res (mOhms)"] = round(ubump_res*1e3, 4)

            ubump_out_info["Top Die PWR Region Dimensions (um)"] = " x ".join([str(round(dim,3)) for dim in ubump_info["region_dims"]])
            ubump_out_info["Bot Die PWR Region Dimensions (um)"] = " x ".join([str(round(dim,3)) for dim in c4_info["region_dims"]])

            ########################## INFO FOR  ##########################
            ubump_out_info["Top Die Critical Path (um)"] = round(ubump_info["crit_path_distance"], 4)
            ubump_out_info["Bot Die Critical Path (um)"] = round(c4_info["crit_path_distance"], 4)

            ubump_out_info["Top Die Rail Critical Res (Ohms)"] = round(ubump_info["single_rail_path_res"], 4)
            ubump_out_info["Bot Die Rail Critical Res (Ohms)"] = round(c4_info["single_rail_path_res"], 4)

            ubump_out_info["Top Single Rail IR Drop (V)"] = round(ubump_info["single_rail_voltage"], 4)
            ubump_out_info["Bot Single Rail IR Drop (V)"] = round(c4_info["single_rail_voltage"], 4)

            ubump_out_info["Bot Via Stack Res (Ohms)"] = via_grid_res
            ubump_out_info["Bot Via Stack IR Drop (V)"] = (via_grid_res) * c4_current_draw

            
            # ubump_out_info["Top Single Rail IR Drop Tx (V)"] = round(ubump_info["single_rail_v_calc_tx"], 4)
            # ubump_out_info["Top Single Rail IR Drop Tx (V)"] = round(ubump_info["single_rail_v_calc_iavg"], 4)
            # ubump_out_info["Bot Single Rail IR Drop iavg (V)"] = round(c4_info["single_rail_v_calc_tx"], 4)
            # ubump_out_info["Bot Single Rail IR Drop iavg (V)"] = round(c4_info["single_rail_v_calc_iavg"], 4)

            ubump_out_info["C4 -> Top Metal Res (Ohms)"] = round(c4_res, 4)
            ubump_out_info["C4 -> Top Metal IR Drop (V)"] = round((c4_res * c4_current_draw), 4)

            ubump_out_info["Top Die Total IR Drop (V)"] = round(top_die_ir_drop, 4)
            ubump_out_info["Bot Die Total IR Drop (V)"] = round(bottom_die_ir_drop, 4)

            # ubump_out_info["Trans per PWR Rail"] = round(ubump_info["tx_per_pwr_rail"], 4)


            ubump_out_infos.append(ubump_out_info)

            # IR DROP INFO FOR EACH STAGE
            # BOTTOM DIE INFO
            bot_ir_drop_info["C4 Bump"] = {
                "R (Ohms)": ic_3d_info.design_pdn.c4_info.single_c4.resistance,
                "I (mA)": round(c4_current_draw*1e3,4),
                "IR Drop (V)": round(ic_3d_info.design_pdn.c4_info.single_c4.resistance * c4_current_draw, 4),
                f"% of Total IR Drop": round((ic_3d_info.design_pdn.c4_info.single_c4.resistance * c4_current_draw) / bottom_die_ir_drop, 4),
            }
            bot_ir_drop_info["TSV Grid"] = {
                "R (Ohms)": ic_3d_info.design_pdn.tsv_info.resistance,
                "I (mA)": round(c4_current_draw*1e3,4),
                "IR Drop (V)": round(ic_3d_info.design_pdn.tsv_info.resistance * c4_current_draw, 4),
                f"% of Total IR Drop": round((ic_3d_info.design_pdn.tsv_info.resistance * c4_current_draw) / bottom_die_ir_drop, 4),
            }
            bot_ir_drop_info["Metal Via Stack"] = {
                "R (Ohms)": via_grid_res, #(single_via_stack_res / vias_per_tsv_grid),
                "I (mA)": round(c4_current_draw*1e3,4),
                "IR Drop (V)": round((via_grid_res) * c4_current_draw, 4),
                f"% of Total IR Drop": round(((via_grid_res) * c4_current_draw) / bottom_die_ir_drop, 4),
            }
            bot_ir_drop_info["Base Die Metal Distribution"] = {
                "R (Ohms)": c4_info["single_rail_path_res"],
                "I (mA)": round(c4_info["current_per_pwr_rail"]*1e3,4),
                "IR Drop (V)": round(c4_info["single_rail_voltage"], 4),
                f"% of Total IR Drop": round((c4_info["single_rail_voltage"]) / bottom_die_ir_drop, 4),
            }
            # TOP DIE INFO
            top_ir_drop_info["C4 -> Ubump Base Die"] = {
                "R (Ohms)": c4_res,
                "I (mA)": c4_current_draw*1e3,
                "IR Drop (V)": round(c4_res * c4_current_draw, 4),
                f"% of Total IR Drop": round((c4_res * c4_current_draw) / top_die_ir_drop, 4),
            }
            top_ir_drop_info["Micro Bump"] = {
                "R (Ohms)": ic_3d_info.design_pdn.ubump_info.single_ubump.resistance*1e-3,
                "I (mA)": round(ubump_info["current_per_crit_region"]*1e3,4),
                "IR Drop (V)": round(ic_3d_info.design_pdn.ubump_info.single_ubump.resistance * ubump_info["current_per_crit_region"], 4),
                f"% of Total IR Drop": round(((ubump_res / num_ubumps_per_pwr_region) * ubump_info["current_per_crit_region"]) / top_die_ir_drop, 4),
            }
            top_ir_drop_info["Top Die Metal Distribution"] = {
                "R (Ohms)": ubump_info["single_rail_path_res"],
                "I (mA)": round(ubump_info["current_per_pwr_rail"]*1e3,4),
                "IR Drop (V)": round(ubump_info["single_rail_voltage"],4),
                f"% of Total IR Drop": round(ubump_info["single_rail_voltage"] / top_die_ir_drop, 4),
            }
            # dimensions of the power regions for the top and bottom layer TODO make it such that power regions can be different sizes
            ic_3d_info.design_pdn.pwr_region_dims = ubump_info["region_dims"]

            ir_drop_out_infos.append([ bot_ir_drop_info, top_ir_drop_info ])

            if max([bottom_die_ir_drop, top_die_ir_drop]) <= (ic_3d_info.design_pdn.ir_drop_budget*1e-3): #or dim > min(design_pdn.ubump_info.max_dims):
                break
            
            dim += 1
            c4_dim += 1
        
        # Break out of second loop TODO remove this as we will be incrementing the number of C4 bumps and ubumps at the same time just with different values
        # if max([bottom_die_ir_drop, top_die_ir_drop]) <= (design_pdn.ir_drop_budget*1e-3): #or c4_dim > min(design_pdn.c4_info.max_c4_dims):
        #     break

        print(f"************************ CONSTANT INFO ************************")
        const_dict = [{
            "C4 -> Bot Metal Res (Ohms)": c4_res*1e-3,
            "Single C4 Res (Ohms)": ic_3d_info.design_pdn.c4_info.single_c4.resistance*1e-3,
            "TSV Grid Res (Ohm)": ic_3d_info.design_pdn.tsv_info.resistance,
            "Single Via Stack Res (Ohms)": single_via_stack_res,
            "Total Via Stack Res (Ohms)": via_grid_res,
            "Single Ubump Res (Ohm)": ic_3d_info.design_pdn.ubump_info.single_ubump.resistance*1e-3,
            "Power Rails per um": pwr_rails_per_um,
            "Power Rail Pitch (nm)": (1/pwr_rails_per_um)*1e3,
            "Current Density (uA/um^2)": current_per_sq_um*1e6,
        }]
        constant_out_df = pd.DataFrame(const_dict)
        for l in rg_utils.get_df_output_lines(constant_out_df):
            print(l)
        print(f"************************ TOP DIE INFO UBUMP PITCH: {pitch} ************************")
        ubump_out_df = pd.DataFrame(ubump_out_infos)
        for l in rg_utils.get_df_output_lines(ubump_out_df):
            print(l)
        summary_out_info = {
            "Ubump Pitch": ic_3d_info.design_pdn.ubump_info.single_ubump.pitch,
            "C4 Dims": ubump_out_infos[-1]["C4 Dims"],
        }
        summary_out_infos.append(summary_out_info)
        print(f"************************ IR DROP INFO PER DIMENSION ************************")
        bot_ir_drop_dfs = []
        top_ir_drop_dfs = []
        for ir_drop_info_pair in ir_drop_out_infos:
            bot_ir_drop_df = pd.DataFrame.from_dict(ir_drop_info_pair[0])
            top_ir_drop_df = pd.DataFrame.from_dict(ir_drop_info_pair[1])
            # nrows should be equal for bot and top
            nrows = len(bot_ir_drop_df.index)
            bot_ir_drop_dfs.append(bot_ir_drop_df)
            top_ir_drop_dfs.append(top_ir_drop_df)

            # print(f"************************ BOTTOM DIE INFO ************************")
            # print(bot_ir_drop_df.to_markdown())
            # print(f"************************ TOP DIE INFO ************************")
            # print(top_ir_drop_df.to_markdown())
        ###################### PLOT IR INFORMATION ######################

        bottom_ir_drop_infos = [ir_drop_info_pair[0] for ir_drop_info_pair in ir_drop_out_infos]
        top_ir_drop_infos = [ir_drop_info_pair[1] for ir_drop_info_pair in ir_drop_out_infos]

        bot_plot_dicts = []
        for ir_portion in bottom_ir_drop_infos[0].keys():    
            # IR Drop / Resistance / Current / Percentage
            for value_catagory in bottom_ir_drop_infos[0][ir_portion].keys():
                bot_plot_dicts.append(
                    {
                        "y_values": [ir_drop_info[ir_portion][value_catagory] for ir_drop_info in bottom_ir_drop_infos],
                        "value_type": value_catagory,
                        "legend": ir_portion,
                    }
                )
        top_plot_dicts = []
        for ir_portion in top_ir_drop_infos[0].keys():    
            # IR Drop / Resistance / Current / Percentage
            for value_catagory in top_ir_drop_infos[0][ir_portion].keys():
                top_plot_dicts.append(
                    {
                        "y_values": [ir_drop_info[ir_portion][value_catagory] for ir_drop_info in top_ir_drop_infos],
                        "value_type": value_catagory,
                        "legend": ir_portion,
                    }
                )

        # bottom and top die will have same value types
        unique_value_types = set(plot_dict["value_type"] for plot_dict in bot_plot_dicts)
        # We want a figure for each value type and a line on the plot for each ir portion
        for value_type in unique_value_types:
            fig = make_subplots(rows=1, cols=2, subplot_titles=("Bottom Die", "Top Die"), shared_yaxes=True)
            for plot_dict in bot_plot_dicts:
                if plot_dict["value_type"] != value_type:
                    continue
                fig.add_trace(
                    go.Scatter(
                        name = plot_dict["legend"],
                        x = num_c4s_list,
                        y = plot_dict["y_values"],
                        legendgroup = plot_dict["legend"],
                    ),
                    row=1, 
                    col=1,
                )
            for plot_dict in top_plot_dicts:
                if plot_dict["value_type"] != value_type:
                    continue
                fig.add_trace(
                    go.Scatter(
                        name = plot_dict["legend"],
                        x = num_c4s_list,
                        y = plot_dict["y_values"],
                        legendgroup = plot_dict["legend"],
                    ),
                    row=1, 
                    col=2,
                )
            fig.update_layout(
                title = f"IR Information vs Number of C4 Bumps",
                xaxis_title = "Number of C4 Bumps",
                yaxis_title = value_type,
            )
            if ic_3d_info.pdn_sim_settings.plot_settings["pdn_sens_study"]:
                fig.show()
            ######################## GENERATING FPGA SECTOR FLOORPLAN ########################
        #generate_fpga_sectors(design_pdn)
    summary_out_infos_df = pd.DataFrame(summary_out_infos)
    print(f"************************ SUMMARY INFO ************************")
    for l in rg_utils.get_df_output_lines(summary_out_infos_df):
        print(l)
        
        
        
