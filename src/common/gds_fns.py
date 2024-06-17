#!/usr/bin/python3

# Scale the final GDS by a factor of 4
# This is called by a tech hook that should be inserted post write_design

import sys, glob, os, re
from typing import List


# All functions in this file will take in [gds_tool, cell_list, gds_file]

            
# Args are [stdcells, gds_file, gds_function]
def main(argv: List[str]):
    stdcells = argv[0]
    gds_file = argv[1]
    gds_function = argv[2]
    try:
        # Prioritize gdstk
        gds_tool = __import__('gdstk')
    except ImportError:
        try:
            print("gdstk not found, falling back to gdspy...")
            gds_tool = __import__('gdspy')
        except ImportError:
            print('Check your gdspy installation!')
            sys.exit()

    print(f"Using {gds_tool.__name__} to get area results from {gds_file}...")

    cell_list = [line.rstrip() for line in open(stdcells, 'r')]

    fn_to_call = getattr(sys.modules[__name__], gds_function, None)
    if callable(fn_to_call):
       ret_val = fn_to_call(gds_tool, cell_list, gds_file)
    
    return ret_val

def get_area(gds_tool, cell_list, gds_file):
    # TODO implement with gdspy as well
    if gds_tool.__name__ == 'gdstk':
        total_area = 0.0
        # load gds
        gds_lib = gds_tool.read_gds(infile=gds_file)
        top_cell = None
        for cell in gds_lib.cells:
            if cell.name == "TOPCELL":
                top_cell = cell
                break            
        for e in top_cell.polygons:
              total_area += e.area()
            
        return total_area
    else:
        raise NotImplementedError("gdspy not supported yet")
    
def asap7_scale_gds(gds_tool, cell_list, gds_file):
    print('Scaling down {gds} using {tool}...'.format(gds=gds_file, tool=gds_tool.__name__))
    if gds_tool.__name__ == 'gdstk':
        # load original_gds
        gds_lib = gds_tool.read_gds(infile=gds_file)
        # Non STDCELL cells
        non_stdcells = list(filter(lambda c: c.name not in cell_list, gds_lib.cells))
        # Iterate through cells that aren't part of standard cell library and scale
        for cell in list(filter(lambda c: c.name not in cell_list, gds_lib.cells)):
            print('Scaling down ' + cell.name)
            # Need to remove 'blk' layer from any macros, else LVS rule deck interprets it as a polygon
            # This has a layer datatype of 4
            # Then scale down the polygon
            non_stdcell_pgs_uniq_layers = set([pg.layer for pg in cell.polygons])
            blk_layer_dtype = 4
            for layer in non_stdcell_pgs_uniq_layers:
                # For all polygon layers that exist in all cells, filter out the polygons with datatype 4
                cell.filter(spec=[(layer, blk_layer_dtype)], remove=True)
            for poly in cell.polygons:
                poly.scale(0.25)

            # Scale paths
            for path in cell.paths:
                path.scale(0.25)

            # Scale and move labels
            for label in cell.labels:
                # Bug fix for some EDA tools that didn't set MAG field in gds file
                # Maybe this is expected behavior in ASAP7 PDK
                label.magnification = 0.25
                label.origin = tuple(i * 0.25 for i in label.origin)

            # Move references (which are scaled if needed)
            for ref in cell.references:
                ref.origin = tuple(i * 0.25 for i in ref.origin)

        # We can also write an SVG of the top cell with gdstk
        gds_lib.top_level()[0].write_svg(os.path.splitext(gds_file)[0] + '.svg')

    elif gds_tool.__name__ == 'gdspy':
        # load original_gds
        gds_lib = gds_tool.GdsLibrary().read_gds(infile=gds_file, units='import')
        # Iterate through cells that aren't part of standard cell library and scale
        for k,v in gds_lib.cell_dict.items():
            if not any(cell in k for cell in cell_list):
                print('Scaling down ' + k)

                # Need to remove 'blk' layer from any macros, else LVS rule deck interprets it as a polygon
                # This has a layer datatype of 4
                # Then scale down the polygon
                v.polygons = [poly.scale(0.25) for poly in v.polygons if not 4 in poly.datatypes]

                # Scale paths
                for path in v.paths:
                    path.scale(0.25)
                    # gdspy v1.4 bug: we also need to scale custom path extensions
                    # Fixed by gdspy/pull#101 in next release
                    if gds_tool.__version__ == '1.4':
                        for i, end in enumerate(path.ends):
                            if isinstance(end, tuple):
                                path.ends[i] = tuple([e*0.25 for e in end])

                # Scale and move labels
                for label in v.labels:
                    # Bug fix for some EDA tools that didn't set MAG field in gds file
                    # Maybe this is expected behavior in ASAP7 PDK
                    # In gdspy/__init__.py: `kwargs['magnification'] = record[1][0]`
                    label.magnification = 0.25
                    label.translate(-label.position[0]*0.75, -label.position[1]*0.75)

                # Move references (which are scaled if needed)
                for ref in v.references:
                    ref.translate(-ref.origin[0]*0.75, -ref.origin[1]*0.75)

    # Overwrite original GDS file
    gds_lib.write_gds(gds_file)

    # For Calibre DRC, we need to rename the top cell to 'TOPCELL'
    gds_lib.top_level()[0].name = 'TOPCELL'
    gds_lib.write_gds(os.path.splitext(gds_file)[0] + '_drc.gds')


if __name__ == '__main__':
    main(sys.argv[1:])