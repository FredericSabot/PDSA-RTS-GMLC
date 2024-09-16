from dash import Dash, html, Input, Output, callback
import dash_cytoscape as cyto
import pandas as pd
import os

NETWORK_NAME = 'Texas'

buses    = pd.read_csv(os.path.join(f'../{NETWORK_NAME}-Data', 'bus'    + ".csv")).to_dict('list')
branches = pd.read_csv(os.path.join(f'../{NETWORK_NAME}-Data', 'branch' + ".csv")).to_dict('list')
N_buses = len(buses['Bus ID'])
N_branches = len(branches['UID'])

MIN_VOLTAGE = 100

elements = []
displayed_buses = []
voltage_levels = {}
voltage_classes = {}

for i in range(N_buses):
    id = buses['Bus ID'][i]
    lat = buses['lat'][i] * 400
    lng = buses['lng'][i] * 400
    voltage_level = int(buses['BaseKV'][i])
    if voltage_level > 225:
        voltage_class = 400
    elif voltage_level > 100:
        voltage_class = 220
    else:
        voltage_class = 20
    voltage_levels[id] = voltage_level
    voltage_classes[id] = voltage_class

    if id == 1:  # Modify to search a given bus
        voltage_class = 'searched'

    if voltage_level >= MIN_VOLTAGE:
        elements.append({'data': {'id': str(id), 'label': str(id), 'voltage_level': voltage_level}, 'position': {'x': lng, 'y': -lat}, 'classes': f'Node_{voltage_class}'})
        displayed_buses.append(id)
    # n.create_voltage_levels(id='V-'+str(id), substation_id='S-'+str(bus_substation_map[id]), topology_kind='BUS_BREAKER', nominal_v=buses['BaseKV'][i])

for i in range(N_branches):
    id = str(branches['UID'][i])
    from_ = str(branches['From Bus'][i])
    to = str(branches['To Bus'][i])
    voltage_class = voltage_classes[branches['From Bus'][i]]

    if int(from_) < 10000 or int(to) < 10000:
        voltage_class = 'searched'

    if int(from_) in displayed_buses and int(to) in displayed_buses:
        elements.append({'data': {'label': id, 'source': from_, 'target': to, 'voltage_level_from': voltage_levels[int(from_)], 'voltage_level_to': voltage_levels[int(to)]}, 'classes': f'Edge_{voltage_class}'})

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
        # Group selectors
        {
            'selector': 'node',
            'style': {
                'label': 'data(label)',
                'tooltip': 'data(tooltip)',
                'text-valign': 'center'
            }
        },
        {
            'selector': 'edge',
            'style': {
                'label': 'data(label)',
                'curve-style': 'bezier'
            }
        },

        # Class selectors
        {
            'selector': '.Node_searched',
            'style': {
                'width': '60px',
                'height': '60px',
                'background-color': '#0000FF',  # blue
                'font-size': '20px',
                'text-valign': 'top'
            }
        },
        {
            'selector': '.Edge_searched',
            'style': {
                'width': 10,
                'line-color': '#0000FF',  # blue
                'font-size': '20px'
            }
        },
        {
            'selector': '.Node_400',
            'style': {
                'width': '30px',
                'height': '30px',
                'background-color': '#FF0000',  # red
                'font-size': '10px'
            }
        },
        {
            'selector': '.Edge_400',
            'style': {
                'width': 6,
                'line-color': '#FF0000 ',  # red
                'font-size': '10px'
            }
        },
        {
            'selector': '.Node_220',
            'style': {
                'width': '10px',
                'height': '10px',
                'background-color': '#00FF00',  # green
                'font-size': '6px'
            }
        },
        {
            'selector': '.Edge_220',
            'style': {
                'width': 4,
                'line-color': '#00FF00',  # green
                'font-size': '6px'
            }
        },
        {
            'selector': '.Node_20',
            'style': {
                'width': '5px',
                'height': '5px',
                'background-color': '#d2ff00',  # yellow
                'font-size': '4px'
            }
        },
        {
            'selector': '.Edge_20',
            'style': {
                'width': 4,
                'line-color': '#d2ff00',  # yellow
                'font-size': '4px'
            }
        }
    ]
    ),
    html.Pre(id='node-data-output', style=styles['pre']),
    html.Pre(id='edge-data-output', style=styles['pre'])
])

@callback(Output('node-data-output', 'children'),
              Input('RTS-GMLC', 'tapNodeData'))
def display_node_data(data):
    if data:
        return html.Div([
            html.H5(f"Bus ID: {data['label']}\nVoltage level: {data['voltage_level']}"),
        ])
    return "Click on a node to see its details"

@callback(Output('edge-data-output', 'children'),
              Input('RTS-GMLC', 'tapEdgeData'))
def display_edge_data(data):
    if data:
        return html.Div([
            html.H5(f"Bus ID: {data['label']}\nVoltage level 1: {data['voltage_level_from']}\nVoltage level 2: {data['voltage_level_to']}"),
        ])
    return "Click on an edge to see its details"


if __name__ == '__main__':
    app.run(debug=True)
