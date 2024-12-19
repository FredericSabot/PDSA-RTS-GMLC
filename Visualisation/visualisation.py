from dash import Dash, html, Input, Output, callback
import dash_cytoscape as cyto
import pandas as pd
import os
import random
import math
import sys
sys.path.append('../3-DynData')
from add_dyn_data import select_gfm_generators
import pypowsybl as pp
random.seed(42)

NETWORK_NAME = 'RTS'
HOUR = 2000

GEOGRAPHIC_SCALE = 400

buses    = pd.read_csv(os.path.join(f'../{NETWORK_NAME}-Data', 'bus'    + ".csv")).to_dict('list')
branches = pd.read_csv(os.path.join(f'../{NETWORK_NAME}-Data', 'branch' + ".csv")).to_dict('list')
gens_csv = pd.read_csv(os.path.join(f'../{NETWORK_NAME}-Data', 'gen'    + ".csv")).to_dict('list')
N_buses = len(buses['Bus ID'])
N_branches = len(branches['UID'])
N_gens = len(gens_csv['GEN UID'])

n = pp.network.load(f'../2-SCOPF/d-Final-dispatch/year_{NETWORK_NAME}/{HOUR}.iidm')
gens = n.get_generators()
gfm_generators = select_gfm_generators(NETWORK_NAME, buses, gens_csv, gens, min_gfm_share_per_area=0.4)

MIN_VOLTAGE = 100  # Buses at a voltage level lower than MIN_VOLTAGE are not displayed

generator_buses = []  # Generator buses are displayed regardless of their voltage level
for gen_id in gens.index:
    vl = gens.at[gen_id, 'voltage_level_id']
    bus_id = vl.split('-')[1]
    if not gens.at[gen_id, 'connected']:
        continue
    generator_buses.append(bus_id)

elements = []
displayed_buses = []
voltage_levels = {}
voltage_classes = {}
bus_id_to_index = {}

for i in range(N_buses):
    id = buses['Bus ID'][i]
    bus_id_to_index[id] = i
    lat = buses['lat'][i]
    lng = buses['lng'][i]
    voltage_level = int(buses['BaseKV'][i])
    if voltage_level > 225:
        voltage_class = 400
    elif voltage_level > 100:
        voltage_class = 220
    else:
        voltage_class = 20
    voltage_levels[id] = voltage_level
    voltage_classes[id] = voltage_class

    if str(id) in ['245', '246', '247', '248', '135', '136', '137']:
        pass # voltage_class = 'searched'
    if str(id).startswith('220'):
        pass # voltage_class = 'searched'

    if buses['Area'][i] == 2 and lng < -98:
        pass # voltage_class = 'searched'

    if voltage_level >= MIN_VOLTAGE or str(id) in generator_buses:
        elements.append({'data': {'id': str(id), 'label': str(id), 'voltage_level': voltage_level},
                         'position': {'x': lng * GEOGRAPHIC_SCALE, 'y': -lat * GEOGRAPHIC_SCALE},
                         'classes': f'Node_{voltage_class}'})
        displayed_buses.append(id)

for i in range(N_branches):
    id = str(branches['UID'][i])
    from_ = str(branches['From Bus'][i])
    to = str(branches['To Bus'][i])
    voltage_class = voltage_classes[branches['From Bus'][i]]

    if id in ['110126-111216_1']:
        voltage_class = 'searched'

    if int(from_) in displayed_buses and int(to) in displayed_buses:
        elements.append({'data': {'label': id, 'source': from_, 'target': to, 'voltage_level_from': voltage_levels[int(from_)], 'voltage_level_to': voltage_levels[int(to)]},
                         'classes': f'Edge_{voltage_class}'})



for i in range(N_gens):
    gen_id = gens_csv['GEN UID'][i]
    bus_id = gens_csv['Bus ID'][i]
    bus_index = bus_id_to_index[bus_id]
    gen_number = gens_csv['Gen ID'][i]
    lat = buses['lat'][bus_index]
    lng = buses['lng'][bus_index]
    fuel = gens_csv['Fuel'][i]
    voltage_level = voltage_levels[bus_id]
    P = gens.at[gen_id, 'target_p']
    Snom = (gens_csv['PMax MW'][i] ** 2 + gens_csv['QMax MVAR'][i] ** 2) ** 0.5

    size = Snom
    size = size**0.5 * 30  # Make area (and not radius) proportional to Snom
    # size = P
    # size = size**0.5 * 50  # Make area (and not radius) proportional to Snom

    if NETWORK_NAME == 'RTS':
        size *= 0.3
    elif NETWORK_NAME == 'Texas':
        size *= 0.2
    else:
        raise NotImplementedError

    if not gens.at[gen_id, 'connected']:
        continue

    color_category = 'fuel'
    if color_category == 'fuel':
        if fuel == 'Nuclear':  # Colors from figure at https://electricgrids.engr.tamu.edu/texas7k/
            color = '#ff3333'  # Red
        elif fuel in ['Coal', 'Oil']:
            color = '#323232'  # Black
        elif fuel == 'NG':
            color = '#999900'  # Dark yellow
        elif fuel == 'Wind':
            color = '#01ff00'  # Green
        elif fuel in ['Solar', 'PV']:
            color = '#ffff33'  # Yellow
        elif fuel == 'Hydro':
            color = '#0000fb'  # Blue
        elif fuel == 'Sync_Cond':
            color = '#00ffad'  # Cyan
        else:
            raise NotImplementedError(fuel)
    elif color_category == 'gfm':
        if fuel in ['Nuclear', 'Coal', 'Oil', 'NG', 'Hydro', 'Sync_Cond']:
            color = '#0000FF'  # Blue, Synchronous machine
        elif fuel in ['Solar', 'PV', 'Wind']:
            if gen_id in gfm_generators:
                color = '#FF0000'  # Red
            else:
                color = '#FFFF00'  # Yellow
        else:
            raise NotImplementedError(fuel)
    else:
        raise NotImplementedError(color_category)

    lat += 0.2 * math.cos(gen_number * (2*math.pi) / 8)
    lng += 0.2 * math.sin(gen_number * (2*math.pi) / 8)

    elements.append({'data': {'id': str(gen_id), 'label': str(gen_id), 'voltage_level': voltage_level},
                     'position': {'x': lng * GEOGRAPHIC_SCALE, 'y': -lat * GEOGRAPHIC_SCALE},
                     'classes': f'Node_generator',
                     'style':{'background-color': color, 'width': size, 'height': size}})

    elements.append({'data': {'label': gen_id, 'source': gen_id, 'target': str(bus_id), 'voltage_level_from': voltage_level, 'voltage_level_to': voltage_level},
                     'classes': f'Edge_generator'})


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
                'width': '20px',
                'height': '20px',
                'background-color': '#FF0000',  # red
                'font-size': '20px'
            }
        },
        {
            'selector': '.Edge_400',
            'style': {
                'width': 6,
                'line-color': '#FF0000 ',  # red
                'font-size': '20px'
            }
        },
        {
            'selector': '.Node_220',
            'style': {
                'width': '10px',
                'height': '10px',
                'background-color': '#00FF00',  # green
                'font-size': '10px'
            }
        },
        {
            'selector': '.Edge_220',
            'style': {
                'width': 4,
                'line-color': '#00FF00',  # green
                'font-size': '10px'
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
        },
        {
            'selector': '.Node_generator',
            'style': {
                'font-size': '10px',
                'opacity': 0.7,
            }
        },
        {
            'selector': '.Edge_generator',
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
