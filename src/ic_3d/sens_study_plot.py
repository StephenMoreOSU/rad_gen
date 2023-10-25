import pandas as pd
import plotly.graph_objects as go
import plotly.subplots as subplots
import plotly.express as px



df = pd.read_csv('sens_study_out.csv')

mlayer_df = df.drop_duplicates(subset=['mlayer_idx', 'mlayer_dist'])
# Create a line plot for each mlayer_idx
mlayer_fig = px.line(mlayer_df, x="mlayer_dist", y="max_total_delay", color="mlayer_idx",
              title="Max Total Delay vs MLayer Dist", labels={"max_total_delay": "Delay", "mlayer_dist": "MLayer Dist"})

# Add the via_factor and ubump_factor as annotations
for _, row in mlayer_df.iterrows():
    mlayer_fig.add_annotation(x=row["mlayer_dist"], y=row["max_total_delay"],
                    text=f"Via: {row['via_factor']}<br>Ubump: {row['ubump_factor']}",
                    showarrow=False, font=dict(size=8))

# Customize the layout
mlayer_fig.update_layout(xaxis_title="MLayer Dist", yaxis_title="Max Total Delay",
                  legend_title="MLayer Index", hovermode="x unified")

via_df = df.drop_duplicates(subset=['via_factor'])

# Create a line plot for each mlayer_idx
via_fig = px.line(via_df, x="via_factor", y="max_total_delay",
              title="Max Total Delay vs Via Factor", labels={"max_total_delay": "Delay", "via_factor": "Via Factor"})

# Add the via_factor and ubump_factor as annotations
for _, row in via_df.iterrows():
    via_fig.add_annotation(x=row["via_factor"], y=row["max_total_delay"],
                    text=f"Via: {row['via_factor']}<br>Ubump: {row['ubump_factor']}",
                    showarrow=False, font=dict(size=8))

# Customize the layout
via_fig.update_layout(xaxis_title="Via Factor", yaxis_title="Max Total Delay",
                  legend_title="Via Factor", hovermode="x unified")


ubump_df = df.drop_duplicates(subset=['ubump_factor'])

# Create a line plot for each mlayer_idx
ubump_fig = px.line(ubump_df, x="ubump_factor", y="max_total_delay",
              title="Max Total Delay vs Via Factor", labels={"max_total_delay": "Delay", "via_factor": "Via Factor"})

# Add the via_factor and ubump_factor as annotations
for _, row in ubump_df.iterrows():
    ubump_fig.add_annotation(x=row["ubump_factor"], y=row["max_total_delay"],
                    text=f"Via: {row['via_factor']}<br>Ubump: {row['mlayer_dist']}",
                    showarrow=False, font=dict(size=8))

# Customize the layout
ubump_fig.update_layout(xaxis_title="Ubump Factor", yaxis_title="Max Total Delay",
                        legend_title="Ubump Factor", hovermode="x unified")


# Show the plot
mlayer_fig.show()
via_fig.show()
ubump_fig.show()