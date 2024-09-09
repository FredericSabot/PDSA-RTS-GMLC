import pypowsybl as pp
import pandas as pd
from math import pi, sqrt
import os
from lxml import etree
import numpy as np

def create_RTS(path):
    n = pp.network.create_empty()

    gens = pd.read_csv(os.path.join(path, 'gen' + ".csv")).to_dict('list')
    buses = pd.read_csv(os.path.join(path, 'bus' + ".csv")).to_dict('list')
    branches = pd.read_csv(os.path.join(path, 'branch' + ".csv")).to_dict('list')

    N_buses = len(buses['Bus ID'])
    N_branches = len(branches['UID'])
    N_gens = len(gens['GEN UID'])

    lines = {}
    transformers = {}
    for key in branches.keys():
        lines[key] = []
        transformers[key] = []
    for i in range(N_branches):
        for key in branches.keys():
            if branches['Tr Ratio'][i] == 0:
                lines[key].append(branches[key][i])
            else:
                transformers[key].append(branches[key][i])
    N_lines = len(lines['UID'])
    N_transfo = len(transformers['UID'])

    # Create one substation per bus (voltage level), but buses connected via a transformer must be in the same substation
    bus_substation_map = {}
    for name in buses['Bus ID']:
        bus_substation_map[name] = name

    for i in range(N_transfo):
        bus1 = transformers['From Bus'][i]
        bus2 = transformers['To Bus'][i]

        old_substation_name = max(bus_substation_map[bus1], bus_substation_map[bus2])
        new_substation_name = min(bus_substation_map[bus1], bus_substation_map[bus2])

        for bus in bus_substation_map:
            if bus_substation_map[bus] == old_substation_name:
                bus_substation_map[bus] = new_substation_name

    substations = []
    for name in bus_substation_map.values():
        if name not in substations:
            substations.append(name)

    n.create_substations(id=['S-{}'.format(name) for name in substations])  # TODO: add geographical info somehow

    for i in range(N_buses):
        id = buses['Bus ID'][i]
        n.create_voltage_levels(id='V-'+str(id), substation_id='S-'+str(bus_substation_map[id]), topology_kind='BUS_BREAKER', nominal_v=buses['BaseKV'][i])
        n.create_buses(id='B-'+str(id), voltage_level_id='V-'+str(id))

        P = buses['MW Load'][i]
        Q = buses['MVAR Load'][i] - buses['MVAR Shunt B'][i]
        n.create_loads(id='L-'+str(id), voltage_level_id='V-'+str(id), bus_id='B-'+str(id), p0=P, q0=Q)


    for i in range(N_lines):
        id = lines['UID'][i]
        bus1 = lines['From Bus'][i]
        bus2 = lines['To Bus'][i]

        index = buses['Bus ID'].index(bus1)
        Vb = buses['BaseKV'][index]
        Zb = Vb**2 / 100
        R = lines['R'][i] * Zb  # pu to Ohm
        X = lines['X'][i] * Zb
        B = lines['B'][i] / Zb / 2
        n.create_lines(id=id, voltage_level1_id='V-{}'.format(bus1), bus1_id='B-{}'.format(bus1),
                    voltage_level2_id='V-{}'.format(bus2), bus2_id='B-{}'.format(bus2),
                    r=R, x=X, b1=B, b2=B, g1=0, g2=0)

    for i in range(N_transfo):
        id = transformers['UID'][i]
        bus1 = transformers['From Bus'][i]
        bus2 = transformers['To Bus'][i]

        index1 = buses['Bus ID'].index(bus1)
        index2 = buses['Bus ID'].index(bus2)
        V1 = buses['BaseKV'][index1]
        V2 = buses['BaseKV'][index2]
        Vb = buses['BaseKV'][index2]  # Parameters should be given in secondary base
        Zb = Vb**2 / 100
        R = transformers['R'][i] * Zb  # pu to Ohm
        X = transformers['X'][i] * Zb
        B = transformers['B'][i] / Zb
        n.create_2_windings_transformers(id=id, voltage_level1_id='V-{}'.format(bus1), bus1_id='B-{}'.format(bus1),
                                        voltage_level2_id='V-{}'.format(bus2), bus2_id='B-{}'.format(bus2),
                                        rated_u1=V1, rated_u2=V2, r=R, x=X, b=B)
        tap = 1 / transformers['Tr Ratio'][i]
        tap_df = pd.DataFrame.from_records(
            index='id',
            columns=['id', 'target_deadband', 'target_v', 'on_load', 'low_tap', 'tap'],
            data=[(id, 2, V2, False, 0, 0)])
        steps_df = pd.DataFrame.from_records(
            index='id',
            columns=['id', 'b', 'g', 'r', 'x', 'rho'],
            data=[(id, 0, 0, 0, 0, tap)])
        n.create_ratio_tap_changers(tap_df, steps_df)

    for i in range(N_gens):
        id = gens['GEN UID'][i]
        bus = gens['Bus ID'][i]
        index = buses['Bus ID'].index(bus)
        Vb = buses['BaseKV'][index]
        P = gens['MW Inj'][i]
        Q = gens['MVAR Inj'][i]
        PMin = gens['PMin MW'][i]
        PMax = gens['PMax MW'][i]
        QMin = gens['QMin MVAR'][i]
        QMax = gens['QMax MVAR'][i]
        SNom = sqrt(PMax**2 + QMax**2)
        targetV = gens['V Setpoint p.u.'][i] * Vb
        energy = gens['Fuel'][i]  # HYDRO, NUCLEAR, WIND, THERMAL, SOLAR or OTHER
        if energy == 'Oil' or energy == 'Coal' or energy == 'NG':
            energy = 'THERMAL'
        elif energy == 'Nuclear':
            energy = 'NUCLEAR'
        elif energy == 'Hydro':
            energy = 'HYDRO'
        elif energy == 'Solar':
            energy = 'SOLAR'
        elif energy == 'PV':
            energy = 'SOLAR'
        elif energy == 'Wind':
            energy = 'WIND'
        elif energy == 'Sync_Cond':
            energy = 'OTHER'
        else:
            raise ValueError(energy, 'not in implemented options')
        n.create_generators(id=id, voltage_level_id='V-'+str(bus), bus_id='B-'+str(bus), target_p=P, target_q=Q, target_v=targetV, rated_s=SNom,
                            voltage_regulator_on=True, min_p=PMin, max_p=PMax, energy_source=energy)
        n.create_minmax_reactive_limits(id=id, min_q=QMin, max_q=QMax)

    print(pp.loadflow.run_ac(n))
    return n


def validate_branch_limits(path, network:pp.network.Network):
    pp.loadflow.run_ac(network)

    branches = pd.read_csv(os.path.join(path, 'branch' + ".csv")).to_dict('list')
    line_results = network.get_lines()
    transformer_results = network.get_2_windings_transformers()
    N_branches = len(branches['UID'])
    P1 = np.zeros(N_branches)
    Q1 = np.zeros(N_branches)
    for i in range(N_branches):
        UID = branches['UID'][i]
        if branches['Tr Ratio'][i] == 0:
            P1[i] = line_results['p1'][UID]
            Q1[i] = line_results['q1'][UID]
        else:
            P1[i] = transformer_results['p1'][UID]
            Q1[i] = transformer_results['q1'][UID]

    cont_rating = np.array(branches['Cont Rating'])
    for i in range(N_branches):
        flow = (P1[i]**2 + Q1[i]**2)**0.5
        if flow > 1.1 * cont_rating[i]:
            print('Warning: overload of branch', branches['UID'][i], ':', flow, '>', cont_rating[i])


if __name__ == '__main__':
    network = create_RTS('.')
    validate_branch_limits('.', network)

    network_string = network.dump_to_string('XIIDM', {'iidm.export.xml.version' : '1.4'})
    network_string = network_string.encode()
    XMLparser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(network_string, XMLparser)
    root.set('sourceFormat', 'RTS-GMLC')

    with open('Texas.iidm', 'wb') as doc:
        doc.write(etree.tostring(root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
