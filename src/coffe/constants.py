# Track-access locality constants
OUTPUT_TRACK_ACCESS_SPAN = 0.25
INPUT_TRACK_ACCESS_SPAN = 0.50

# Delay weight constants:
DELAY_WEIGHT_SB_MUX = 0.4107
DELAY_WEIGHT_CB_MUX = 0.0989
DELAY_WEIGHT_LOCAL_MUX = 0.0736
DELAY_WEIGHT_LUT_A = 0.0396
DELAY_WEIGHT_LUT_B = 0.0379
DELAY_WEIGHT_LUT_C = 0.0704 # This one is higher because we had register-feedback coming into this mux.
DELAY_WEIGHT_LUT_D = 0.0202
DELAY_WEIGHT_LUT_E = 0.0121
DELAY_WEIGHT_LUT_F = 0.0186
DELAY_WEIGHT_LUT_FRAC = 0.0186
DELAY_WEIGHT_LOCAL_BLE_OUTPUT = 0.0267
DELAY_WEIGHT_GENERAL_BLE_OUTPUT = 0.0326
# The res of the ~15% came from memory, DSP, IO and FF based on my delay profiling experiments.
DELAY_WEIGHT_RAM = 0.15
HEIGHT_SPAN = 0.5

# Metal Layer definitions
LOCAL_WIRE_LAYER = 0

# Global Constants
CHAN_USAGE_ASSUMPTION = 0.5
CLUSTER_INPUT_USAGE_ASSUMPTION = 0.5
LUT_INPUT_USAGE_ASSUMPTION = 0.85

# This parameter determines if RAM core uses the low power transistor technology
# It is strongly suggested to keep it this way since our
# core RAM modules were designed to operate with low power transistors.
# Therefore, changing it might require other code changes.
# I have included placeholder functions in case someone really insists to remove it
# The easier alternative to removing it is to just provide two types of transistors which are actually the same
# In that case the user doesn't need to commit any code changes.
use_lp_transistor = 1
