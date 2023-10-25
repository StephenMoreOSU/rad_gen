import os, sys
import pandas as pd

import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


pd.options.plotting.backend = "plotly"

def flatten_mixed_list(input_list):
    """
        Flattens a list with mixed value Ex. ["hello", ["billy","bob"],[["johnson"]]] -> ["hello", "billy","bob","johnson"]
    """
    # Create flatten list lambda function
    flat_list = lambda input_list:[element for item in input_list for element in flat_list(item)] if type(input_list) is list else [input_list]
    # Call lambda function
    flattened_list = flat_list(input_list)
    return flattened_list



# inv_df = pd.read_csv("buffer_inv_report.csv")




df = pd.read_csv("buffer_summary_report.csv")

if len(sys.argv) > 1 and sys.argv[1] == "-f":
    df = df.loc[(df["n_stages"] == 2) & (df["ubump_pitch"] == 1)]

# print(df)

trace_groups = []

# Grouping traces by "n_stages", "ubump_pitch", and "process"
for n_stages in df["n_stages"].unique(): 
    for ubump_pitch in df["ubump_pitch"].unique():
        for process in df["process"].unique():
            trace_groups.append(df.loc[(df["n_stages"] == n_stages) & (df["ubump_pitch"] == ubump_pitch) & (df["process"] == process)])
    

colors = [
    '#1f77b4',  # muted blue
    '#ff7f0e',  # safety orange
    '#2ca02c',  # cooked asparagus green
    '#d62728',  # brick red
    '#9467bd',  # muted purple
    '#8c564b',  # chestnut brown
    '#e377c2',  # raspberry yogurt pink
    '#7f7f7f',  # middle gray
    '#bcbd22',  # curry yellow-green
    '#17becf'   # blue-teal
]

fig = make_subplots(rows=len(df['n_stages'].unique()), cols = 2, subplot_titles=flatten_mixed_list([[f"Stage Ratio vs. Delay (n_stages: {n_stages})",f"Stage Ratio vs. Area (um^2) (n_stages: {n_stages})"] for n_stages in df['n_stages'].unique()]))

for stage_id, n_stages in enumerate(df["n_stages"].unique()):
    for trace_id, trace_df in enumerate(trace_groups):
        trace_df = trace_df.loc[trace_df["n_stages"] == n_stages]
        if trace_df.empty:
            continue

        fig.add_trace(go.Scatter(
                x = trace_df["stage_ratio"],
                y = trace_df["max_prop_delay"],
                fillcolor = colors[trace_id % len(colors)],
                name = f"Delay (n/ps) ubump_pitch: {trace_df['ubump_pitch'].iloc[0]}, process: {trace_df['process'].iloc[0]}",
            ),
            row = stage_id + 1,
            col = 1,
        )
        fig.add_trace(go.Scatter(
                x = trace_df["stage_ratio"],
                y = trace_df["area"],
                fillcolor = colors[trace_id % len(colors)],
                name = f"Area (um^2) ubump_pitch: {trace_df['ubump_pitch'].iloc[0]}, process: {trace_df['process'].iloc[0]}",
            ),
            row = stage_id + 1,
            col = 2,
        )

fig.show()


# buffer_dse_df = buffer_dse_df.loc[buffer_dse_df["n_stages"] == 2]

# fig = buffer_dse_df.plot(
#         x = "stage_ratio",
#         y = "max_prop_delay",
#         labels = {"stage_ratio": "Stage Ratio", "max_prop_delay": "Delay (ps)"},
# )

# fig.show()



# (buffer_dse_df
# .plot(x = "stage_ratio",
#       y = "max_prop_delay",
#       labels = {"stage_ratio": "Stage Ratio", "max_prop_delay": "Delay (ps)"},
#       )
# )

# Create separate traces for "ubump_pitch", "process", and "n_stages"
# fig = px.scatter(buffer_dse_df, x="stage_ratio", y=["max_prop_delay", "area"],
#                  color="ubump_pitch", symbol="process", facet_col="n_stages",
#                  line_group="ubump_pitch")


# # Update axis labels and layout
# fig.update_xaxes(title_text="Target Frequency")
# fig.update_yaxes(title_text="Value")
# fig.update_layout(
#     title="Scatter Plot of max_prop_delay and area",
#     legend_title="ubump_pitch",
#     legend=dict(orientation="h"),
# )

# # Show the plot
# fig.show()