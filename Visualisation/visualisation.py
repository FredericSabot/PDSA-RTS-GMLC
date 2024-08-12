from dash import Dash, html, Input, Output, callback
import dash_cytoscape as cyto
import pandas as pd
import os

buses    = pd.read_csv(os.path.join('../RTS-Data', 'bus'    + ".csv")).to_dict('list')
branches = pd.read_csv(os.path.join('../RTS-Data', 'branch' + ".csv")).to_dict('list')
N_buses = len(buses['Bus ID'])
N_branches = len(branches['UID'])

elements = []

for i in range(N_buses):
    id = buses['Bus ID'][i]
    lat = buses['lat'][i] * 400
    lng = buses['lng'][i] * 400
    elements.append({'data': {'id': str(id), 'label': str(id)}, 'position': {'x': lat, 'y': lng}})
    # n.create_voltage_levels(id='V-'+str(id), substation_id='S-'+str(bus_substation_map[id]), topology_kind='BUS_BREAKER', nominal_v=buses['BaseKV'][i])

for i in range(N_branches):
    id = str(branches['UID'][i])
    from_ = str(branches['From Bus'][i])
    to = str(branches['To Bus'][i])
    elements.append({'data': {'label': str(id), 'source': from_, 'target': to}})

app = Dash(__name__)

styles = {
    'pre': {
        'border': 'thin lightgrey solid',
        'overflowX': 'scroll'
    }
}

app.layout = html.Div([
    cyto.Cytoscape(
        id='RTS-GMLC',
        layout={'name': 'preset'},
        style={'width': '100%', 'height': '800px'},
        # autolock=True,
        elements=elements,
        stylesheet=[
        {
            'selector': 'node',
            'style': {
                'label': 'data(label)',
                'width': '30px',
                'height': '30px',
                'background-color': '#0074D9',
                'tooltip': 'data(tooltip)'
            }
        },
        {
            'selector': 'edge',
            'style': {
                'label': 'data(label)',
                'width': 2,
                'line-color': '#9CAEBB',
                'curve-style': 'bezier'
            }
        }
    ]
    ),
    html.Pre(id='node-data-output', style=styles['pre'])
])

@callback(Output('node-data-output', 'children'),
              Input('RTS-GMLC', 'tapNodeData'))

def display_node_data(data):
    if data:
        return html.Div([
            html.H5(f"Bus ID: {data['label']}"),
            # html.P(f"Customer: {data['cust_info']}")
        ])
    return "Click on a node to see its details"


if __name__ == '__main__':
    app.run(debug=True)