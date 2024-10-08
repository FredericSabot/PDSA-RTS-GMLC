import csv
import os
import numpy as np
import gams
import sys
import datetime
from cmath import pi
import pypowsybl as pp
from pathlib import Path
import shutil
import pickle

baseMVA = 100

# sys.argv = ['PSCACOPF.py', '167', 'january', 'Texas']  # Don't uncomment, copy paste to interpreter if needed (avoid mistakes)
hour = int(sys.argv[1])
case = sys.argv[2]
network_name = sys.argv[3]
tmp_path = None
if len(sys.argv) > 4:
    tmp_path = sys.argv[4]
print('Running PSCACOPF for case', case, 'hour:', hour, 'network:', network_name)

if network_name == 'RTS':
    LOWEST_CONTINGENCY_VOLTAGE = 138
elif network_name == 'Texas':
    LOWEST_CONTINGENCY_VOLTAGE = 345
else:
    raise NotImplementedError('Network not considered')

WITH_PRESCIENT = True  # If initialise OPF based on prescient outputs
if network_name == 'Texas':
    WITH_PRESCIENT = False  # Prescient too slow for large networks

if case == 'january':
    init_date = datetime.datetime(2020, 1, 1)
elif case == 'july':
    init_date = datetime.datetime(2020, 7, 1)
elif case == 'year':
    init_date = datetime.datetime(2020, 1, 1)
else:
    raise NotImplementedError('Case not yet considered')

date = init_date + datetime.timedelta(hours = hour)

def csvToDict(csv_file, dir='.'):
    with open(os.path.join(dir, csv_file), 'r') as file:
        reader = csv.reader(file)
        headers = next(reader)
        # return [dict(zip(headers, row)) for row in reader]

        first_row = next(reader)
        dic = {}
        for i in range(len(headers)):
            try:
                value = float(first_row[i])
            except ValueError:
                value = first_row[i]
            dic[headers[i]] = [value]
        for row in reader:
            for i in range(len(headers)):
                try:
                    dic[headers[i]].append(float(row[i]))
                except ValueError:
                    dic[headers[i]].append(row[i])
    return dic


def opf_results_to_powsybl(network:pp.network.Network, thermal_gens, thermal_connected, P_thermal, Q_thermal,
                           hydro_gens, P_hydro, Q_hydro, hydro_max,
                           wind_gens, P_wind, Q_wind, wind_max,
                           pv_gens, P_pv, Q_pv, pv_max,
                           rtpv_gens, rtpv_max,
                           syncon_gens, Q_syncon,
                           buses, demand_bus, demand_bus_Q,
                           gens, V_target):
    N_pv_gens = len(pv_gens['Gen ID'])
    N_rtpv_gens = len(rtpv_gens['Gen ID'])
    N_buses = len(buses['Bus ID'])
    N_gens = len(gens['GEN UID'])

    network.update_generators(id=thermal_gens['GEN UID'], connected=thermal_connected,
                            target_p=np.array(list(P_thermal.values())) * baseMVA,
                            target_q=np.array(list(Q_thermal.values())) * baseMVA)
    network.update_generators(id=hydro_gens['GEN UID'],
                            target_p=np.array(list(P_hydro.values())) * baseMVA,
                            target_q=np.array(list(Q_hydro.values())) * baseMVA,
                            max_p=hydro_max * baseMVA)
    network.update_generators(id=wind_gens['GEN UID'],
                            target_p=np.array(list(P_wind.values())) * baseMVA,
                            target_q=np.array(list(Q_wind.values())) * baseMVA,
                            max_p=wind_max * baseMVA)
    network.update_generators(id=pv_gens['GEN UID'],
                            target_p=np.array(list(P_pv.values())) * baseMVA,
                            target_q=np.array(list(Q_pv.values())) * baseMVA,
                            max_p=pv_max * baseMVA,
                            voltage_regulator_on=[True] * N_pv_gens)
    network.update_generators(id=rtpv_gens['GEN UID'],
                            target_p=rtpv_max * baseMVA,
                            max_p=rtpv_max * baseMVA,
                            voltage_regulator_on=[False] * N_rtpv_gens)
    network.update_generators(id=syncon_gens['GEN UID'], target_q=np.array(list(Q_syncon.values())) * baseMVA)

    # Disconnect PV generators at night
    for i in range(N_pv_gens):
        network.update_generators(id=pv_gens['GEN UID'][i], connected = pv_max[i] > 0)
    for i in range(N_rtpv_gens):
        network.update_generators(id=rtpv_gens['GEN UID'][i], connected = rtpv_max[i] > 0)

    load_ids = ['L-'+str(int(buses['Bus ID'][i])) for i in range(N_buses)]
    network.update_loads(id=load_ids, p0=demand_bus * baseMVA, q0=demand_bus_Q * baseMVA)

    for i in range(N_gens):
        bus_id = gens['Bus ID'][i]
        index = buses['Bus ID'].index(bus_id)
        V = list(V_target.values())[index] * buses['BaseKV'][index]
        network.update_generators(id=gens['GEN UID'][i], target_v=V)


def compute_PTDFs(branch_map, branch_admittances):
    # Long to compute and independent of operating conditions, so save to file
    PTDF_path = f'PTDFs_{network_name}.pickle'
    if os.path.exists(PTDF_path):
        with open(PTDF_path, 'rb') as file:
            PTDFs = pickle.load(file)
    else:
        # Actual computation

        # branch_map = np.zeros((N_branches, N_buses))
        branch_map = branch_map.T  # (N_branches, N_buses) to (N_buses, N_branches)
        branch_admittances = np.diag(branch_admittances)  # (N_branches, 1) to (N_branches, N_branches)
        B = branch_map @ branch_admittances @ branch_map.T
        PTDFs = branch_admittances @ branch_map.T @ np.linalg.inv(B)

        with open(PTDF_path, 'wb') as file:
            pickle.dump(PTDFs, file, protocol=pickle.HIGHEST_PROTOCOL)

    return PTDFs  # N_branches, N_buses


def compute_LODFs(PTDFs, branch_map, cont_rating):
    # Compute line outage distribution factor, i.e. change in flow in line i if line j is disconnected (to be multiplied by pre-fault flow in line j)

    LODF_path = f'LODFs_{network_name}.pickle'
    if os.path.exists(LODF_path):
        with open(LODF_path, 'rb') as file:
            LODFs = pickle.load(file)
    else:
        branch_map = branch_map.T  # (N_branches, N_buses) to (N_buses, N_branches)
        LODFs = -PTDFs @ branch_map

        N_branches = len(cont_rating)
        for i in range(N_branches):
            for j in range(N_branches):
                if abs(LODFs[i][j]) * cont_rating[i] < 0.01 * cont_rating[j]:
                    LODFs[i][j] = 0  # Neglect LODF if contingency of line i at max power flow (cont_rating[i]) impact line j by less than 1% of its rating

        with open(LODF_path, 'wb') as file:
            pickle.dump(LODFs, file, protocol=pickle.HIGHEST_PROTOCOL)

    return LODFs


data_dir = f'../{network_name}-Data'
timeseries_dir = f'../{network_name}-Data/timeseries_data_files'
prescient_dir = f'../1-Prescient/PrescientDispatch' + '_' + case

buses = csvToDict('bus.csv', data_dir)
branches = csvToDict('branch.csv', data_dir)
gens = csvToDict('gen.csv', data_dir)

if WITH_PRESCIENT:
    prescient_thermal_dispatch = csvToDict('Thermal-' + str(hour) + '.csv', prescient_dir)
    prescient_hydro_dispatch = csvToDict('Hydro-' + str(hour) + '.csv', prescient_dir)
    prescient_pv_dispatch = csvToDict('PV-' + str(hour) + '.csv', prescient_dir)
    prescient_wind_dispatch = csvToDict('Wind-' + str(hour) + '.csv', prescient_dir)

N_buses = len(buses['Bus ID'])
N_branches = len(branches['UID'])
N_gens = len(gens['GEN UID'])

loads_P = buses['MW Load']
loads_Q = buses['MVAR Load']
area = buses['Area']
area = [int(a) for a in area]
N_areas = len(set(area))
load_per_area = [0] * N_areas
for i in range(N_buses):
    load_per_area[area[i] - 1] += loads_P[i]

load_participation_area = []
for i in range(N_buses):
    load_participation_area.append(loads_P[i] / load_per_area[area[i] - 1])

admit = 1 / np.array(branches['X'])
branch_map = np.zeros((N_branches, N_buses))

for i in range(N_branches):
    branches['From Bus'][i] = buses['Bus ID'].index(branches['From Bus'][i])
    branches['To Bus'][i] = buses['Bus ID'].index(branches['To Bus'][i])
    branch_map[i, int(branches['From Bus'][i])] = 1
    branch_map[i, int(branches['To Bus'][i])] = -1

for j in range(N_buses):
    if buses['BaseKV'][j] < LOWEST_CONTINGENCY_VOLTAGE:
        continue
    if sum([abs(branch_map[i][j]) for i in range(N_branches)]) < 2:
        raise Exception('Bus', buses['Bus ID'][j], 'is only connected to one branch, system thus cannot be N-1 secure')

cont_rating = np.array(branches['Cont Rating'])
lte_rating  = np.array(branches['LTE Rating'])
if network_name == 'Texas':
    cont_rating *= 1.5  # Necessary for DC SCOPF to converge during summer
    lte_rating *= 1.5
    lte_rating = np.maximum(lte_rating, cont_rating * 1.2)  # Set LTE rating to at least equal to 120% of normal rating, because inconsistencies in Texas data

contingency_states = np.diag(np.full(N_branches, 1.0))  # Diagonal matrix of ones
considered_contingencies = []
for i in range(N_branches):  # Only consider contingencies at the highest voltage level(s)
    from_ = branches['From Bus'][i]
    to = branches['To Bus'][i]
    if buses['BaseKV'][from_] < LOWEST_CONTINGENCY_VOLTAGE or buses['BaseKV'][to] < LOWEST_CONTINGENCY_VOLTAGE:
        continue
    considered_contingencies.append(i)
N_contingencies = len(considered_contingencies)
print('Case with', N_contingencies, 'considered contingencies')

considered_contingencies_map = np.zeros((N_branches, N_contingencies))
for cont, branch in enumerate(considered_contingencies):
    considered_contingencies_map[branch][cont] = 1

thermal_gens = {}
hydro_gens = {}
pv_gens = {}
wind_gens = {}
rtpv_gens = {}
syncon_gens = {}

for key in gens.keys():
    thermal_gens[key] = []
    hydro_gens[key] = []
    pv_gens[key] = []
    wind_gens[key] = []
    rtpv_gens[key] = []
    syncon_gens[key] = []

for i in range(N_gens):
    for key in gens.keys():
        if gens['Fuel'][i] == 'Oil' or gens['Fuel'][i] == 'Coal' or gens['Fuel'][i] == 'NG' or gens['Fuel'][i] == 'Nuclear':
            thermal_gens[key].append(gens[key][i])
        elif gens['Fuel'][i] == 'Hydro':
            hydro_gens[key].append(gens[key][i])
        elif gens['Category'][i] == 'Solar PV' or gens['Category'][i] == 'PV':
            pv_gens[key].append(gens[key][i])
        elif gens['Fuel'][i] == 'Wind':
            wind_gens[key].append(gens[key][i])
        elif gens['Category'][i] == 'Solar RTPV':
            rtpv_gens[key].append(gens[key][i])
        elif gens['Fuel'][i] == 'Sync_Cond':
            syncon_gens[key].append(gens[key][i])
        else:
            raise ValueError('Unit ', gens['GEN UID'][i], ' is not considered', gens['Fuel'][i], gens['Category'][i])

N_thermal_gens = len(thermal_gens['Gen ID'])
N_hydro_gens = len(hydro_gens['Gen ID'])
N_pv_gens = len(pv_gens['Gen ID'])
N_wind_gens = len(wind_gens['Gen ID'])
N_rtpv_gens = len(rtpv_gens['Gen ID'])
N_syncon_gens = len(syncon_gens['Gen ID'])

thermal_gen_map = np.zeros((N_thermal_gens, N_buses))
hydro_gen_map = np.zeros((N_hydro_gens, N_buses))
pv_gen_map = np.zeros((N_pv_gens, N_buses))
wind_gen_map = np.zeros((N_wind_gens, N_buses))
rtpv_gen_map = np.zeros((N_rtpv_gens, N_buses))
syncon_gen_map = np.zeros((N_syncon_gens, N_buses))

for i in range(N_thermal_gens):
    thermal_gen_map[i][buses['Bus ID'].index(thermal_gens['Bus ID'][i])] = 1
for i in range(N_hydro_gens):
    hydro_gen_map[i][buses['Bus ID'].index(hydro_gens['Bus ID'][i])] = 1
for i in range(N_pv_gens):
    pv_gen_map[i][buses['Bus ID'].index(pv_gens['Bus ID'][i])] = 1
for i in range(N_wind_gens):
    wind_gen_map[i][buses['Bus ID'].index(wind_gens['Bus ID'][i])] = 1
for i in range(N_rtpv_gens):
    rtpv_gen_map[i][buses['Bus ID'].index(rtpv_gens['Bus ID'][i])] = 1
for i in range(N_syncon_gens):
    syncon_gen_map[i][buses['Bus ID'].index(syncon_gens['Bus ID'][i])] = 1

thermal_min = np.array(thermal_gens['PMin MW']) / baseMVA # * np.array(prescient_thermal_dispatch['State'])
thermal_max = np.array(thermal_gens['PMax MW']) / baseMVA # * np.array(prescient_thermal_dispatch['State'])

def extractRealTimeData(hour, dir, name):
    with open(os.path.join(timeseries_dir, dir, 'REAL_TIME_' + name + '.csv'), 'r') as data:
        reader = csv.reader(data)
        next(reader)  # Skip header
        for row in reader:
            year = int(row[0])
            month = int(row[1])
            day = int(row[2])
            period_minutes = int(row[3]) - 1
            if network_name == 'RTS':
                period_length = 5
            elif network_name == 'Texas':
                period_length = 60
            else:
                raise
            date = datetime.datetime(year, month, day) + datetime.timedelta(minutes = period_minutes * period_length)
            if init_date + datetime.timedelta(hours = hour) == date:
                data = []
                for value in row[4:]:
                    data.append(float(value))
                return data
    raise Exception('Hour', hour, 'not found in timeseries')

try:
    hydro_max = np.array(extractRealTimeData(hour, 'HYDRO', 'hydro')) / baseMVA
except FileNotFoundError:
    print('Warning: hydro availability file not found, assuming no water shortage')
    hydro_max = np.array(hydro_gens['PMax MW']) / baseMVA

pv_max = np.array(extractRealTimeData(hour, 'PV', 'pv')) / baseMVA
wind_max = np.array(extractRealTimeData(hour, 'WIND', 'wind')) / baseMVA
if len(rtpv_gens['GEN UID']) > 0:
    rtpv_max = np.array(extractRealTimeData(hour, 'RTPV', 'rtpv')) / baseMVA
else:
    rtpv_max = np.array([])

losses = 0.04
demand_area = np.array(extractRealTimeData(hour, 'Load', 'regional_Load')) / baseMVA
demand_bus = []

for i in range(N_buses):
    demand_bus.append(loads_P[i] / load_per_area[area[i] - 1] * demand_area[area[i] - 1])
demand_bus = np.array(demand_bus)

Q_AC_thermal = {i+1: 0 for i in range(N_thermal_gens)}  # Reactive outputs unkown at this stage
Q_AC_hydro = {i+1: 0 for i in range(N_hydro_gens)}
Q_AC_wind = {i+1: 0 for i in range(N_wind_gens)}
Q_AC_pv = {i+1: 0 for i in range(N_pv_gens)}
Q_AC_syncon = {i+1: 0 for i in range(N_syncon_gens)}
V_AC = {i+1: 1 for i in range(N_buses)}  # Flat start


def addGamsSet(db, name, description, lst):
    # Adds a 1-dimensional set
    set = db.add_set(name, 1, description)
    for i in lst:
        set.add_record(str(i))
    return set

def addGamsParams(db, name, description, sets, values):
    m = db.add_parameter_dc(name, sets, description)
    if len(sets) == 1:
        i_1 = sets[0]
        for i in range(len(i_1)):
            m.add_record(str(i+1)).value = values[i]
    elif len(sets) == 2:
        i_1, i_2 = sets[0], sets[1]
        for i in range(len(i_1)):
            for j in range(len(i_2)):
                if values[i][j] != 0:  # Only store non-zero values for performance
                    m.add_record((str(i+1),str(j+1))).value = values[i][j]

PTDFs = compute_PTDFs(branch_map, admit)
LODFs = compute_LODFs(PTDFs, branch_map, cont_rating)

# DCOPF: Send data to GAMS
print('\nPSCDCOPF')
if tmp_path is None:
    dcopf_path = os.path.join(os.getcwd(), 'a-PSCDCOPF', str(hour))
else:
    dcopf_path = os.path.join(tmp_path, 'a-PSCDCOPF', str(hour))
Path(dcopf_path).mkdir(parents=True, exist_ok=True)
ws = gams.GamsWorkspace(working_directory=dcopf_path, debug=gams.DebugLevel.Off)
db_preDC = ws.add_database()
shutil.copy(os.path.join('a-PSCDCOPF', 'cplex.opt'), dcopf_path)

i_thermal = addGamsSet(db_preDC, 'i_thermal', 'thermal generators', range(1, N_thermal_gens + 1))
i_hydro = addGamsSet(db_preDC, 'i_hydro', 'hydro generators', range(1, N_hydro_gens + 1))
i_pv = addGamsSet(db_preDC, 'i_pv', 'pv generators', range(1, N_pv_gens + 1))
i_wind = addGamsSet(db_preDC, 'i_wind', 'wind generators', range(1, N_wind_gens + 1))
i_rtpv = addGamsSet(db_preDC, 'i_rtpv', 'rtpv generators', range(1, N_rtpv_gens + 1))
i_syncon = addGamsSet(db_preDC, 'i_syncon', 'syncon generators', range(1, N_syncon_gens + 1))
i_bus = addGamsSet(db_preDC, 'i_bus', 'buses', range(1, N_buses + 1))
i_branch = addGamsSet(db_preDC, 'i_branch', 'branches', range(1, N_branches + 1))

addGamsParams(db_preDC, 'thermal_map', 'thermal generators map', [i_thermal, i_bus], thermal_gen_map)
addGamsParams(db_preDC, 'hydro_map', 'hydro generators map', [i_hydro, i_bus], hydro_gen_map)
addGamsParams(db_preDC, 'pv_map', 'pv generators map', [i_pv, i_bus], pv_gen_map)
addGamsParams(db_preDC, 'wind_map', 'wind generators map', [i_wind, i_bus], wind_gen_map)
addGamsParams(db_preDC, 'rtpv_map', 'rtpv generators map', [i_rtpv, i_bus], rtpv_gen_map)
addGamsParams(db_preDC, 'syncon_map', 'syncon generators map', [i_syncon, i_bus], syncon_gen_map)
addGamsParams(db_preDC, 'branch_map', 'branches map', [i_branch, i_bus], branch_map)

addGamsParams(db_preDC, 'thermal_min', 'thermal generator minimum generation', [i_thermal], thermal_min)
addGamsParams(db_preDC, 'thermal_max', 'thermal generator maximum generation', [i_thermal], thermal_max)
addGamsParams(db_preDC, 'hydro_max', 'hydro generator maximum generation', [i_hydro], hydro_max)
addGamsParams(db_preDC, 'pv_max', 'pv generator maximum generation', [i_pv], pv_max)
addGamsParams(db_preDC, 'wind_max', 'wind generator maximum generation', [i_wind], wind_max)
addGamsParams(db_preDC, 'rtpv_max', 'rtpv generator maximum generation', [i_rtpv], rtpv_max)

addGamsParams(db_preDC, 'branch_admittance', 'branch admittance', [i_branch], admit)
addGamsParams(db_preDC, 'branch_max_N', 'Normal branch max power', [i_branch], cont_rating / baseMVA)
addGamsParams(db_preDC, 'branch_max_E', 'Emergency branch max power', [i_branch], lte_rating / baseMVA)

# considered_contingency_states = contingency_states[:, considered_contingencies]
i_contingency = addGamsSet(db_preDC, 'i_contingency', 'contingencies', range(1, 1 + N_contingencies))
if network_name == 'RTS':
    addGamsParams(db_preDC, 'contingency_states', 'Line states in the considered contingencies', [i_branch, i_contingency], contingency_states)
elif network_name == 'Texas':
    addGamsParams(db_preDC, 'considered_contingencies_map', 'contingencies map', [i_branch, i_contingency], considered_contingencies_map)
    addGamsParams(db_preDC, 'LODFs', 'Line outage distribution factors', [i_branch, i_contingency], LODFs[:, considered_contingencies])
else:
    raise

addGamsParams(db_preDC, 'demand', 'demand at each bus', [i_bus], demand_bus * (1 + losses))

if network_name == 'RTS':
    thermal_lincost = np.array(thermal_gens['HR_incr_3']) * 1000 * np.array(thermal_gens['Fuel Price $/MMBTU']) / 1e6
    hydro_lincost = np.array(hydro_gens['HR_incr_3']) * 1000 * np.array(hydro_gens['Fuel Price $/MMBTU']) / 1e6
    pv_lincost = np.array(pv_gens['HR_incr_3']) * 1000 * np.array(pv_gens['Fuel Price $/MMBTU']) / 1e6
    wind_lincost = np.array(wind_gens['HR_incr_3']) * 1000 * np.array(wind_gens['Fuel Price $/MMBTU']) / 1e6
elif network_name == 'Texas':
    thermal_lincost = np.array(thermal_gens['HR_incr_1']) * 1000 * np.array(thermal_gens['Fuel Price $/MMBTU']) / 1e6
    hydro_lincost = np.array(hydro_gens['HR_incr_1']) * 1000 * np.array(hydro_gens['Fuel Price $/MMBTU']) / 1e6
    pv_lincost = np.array(pv_gens['HR_incr_1']) * 1000 * np.array(pv_gens['Fuel Price $/MMBTU']) / 1e6
    wind_lincost = np.array(wind_gens['HR_incr_1']) * 1000 * np.array(wind_gens['Fuel Price $/MMBTU']) / 1e6
else:
    raise
addGamsParams(db_preDC, 'lincost_thermal', 'thermal linear cost', [i_thermal], thermal_lincost)
addGamsParams(db_preDC, 'lincost_hydro', 'hydro linear cost', [i_hydro], hydro_lincost)
addGamsParams(db_preDC, 'lincost_pv', 'pv linear cost', [i_pv], pv_lincost)
addGamsParams(db_preDC, 'lincost_wind', 'wind linear cost', [i_wind], wind_lincost)

if WITH_PRESCIENT:
    addGamsParams(db_preDC, 'P_thermal_0', 'Initial thermal outputs', [i_thermal], np.array(prescient_thermal_dispatch['Output']) / baseMVA)
    addGamsParams(db_preDC, 'P_hydro_0', 'Initial hydro outputs', [i_hydro], np.array(prescient_hydro_dispatch['Output']) / baseMVA)
    addGamsParams(db_preDC, 'P_pv_0', 'Initial pv outputs', [i_pv], np.array(prescient_pv_dispatch['Output']) / baseMVA)
    addGamsParams(db_preDC, 'P_wind_0', 'Initial wind outputs', [i_wind], np.array(prescient_wind_dispatch['Output']) / baseMVA)

    prescient_thermal_dispatch['State'] = [int(i) for i in prescient_thermal_dispatch['State']]
    addGamsParams(db_preDC, 'on_0', 'Initial commitment status of thermal generators', [i_thermal], prescient_thermal_dispatch['State'])

db_preDC.export('PrePSCDCOPF.gdx')
if WITH_PRESCIENT:
    t = ws.add_job_from_file(os.path.join(os.getcwd(), 'a-PSCDCOPF', 'PSCDCOPF.gms'))
else:
    t = ws.add_job_from_file(os.path.join(os.getcwd(), 'a-PSCDCOPF', 'PSCDCOPF_no_init.gms'))
print('Launching GAMS')
t.run()

db_postDC = ws.add_database_from_gdx("PostPSCDCOPF.gdx")

solve_status = int(db_postDC["sol"].first_record().value)
if solve_status != 1 and solve_status != 2 and solve_status != 7:
    raise RuntimeError('PSCDCOPF: no solution found, error code:', solve_status)

P_DC_thermal = {rec.keys[0]:rec.level for rec in db_postDC["P_thermal"]}
P_DC_hydro = {rec.keys[0]:rec.level for rec in db_postDC["P_hydro"]}
P_DC_pv = {rec.keys[0]:rec.level for rec in db_postDC["P_pv"]}
P_DC_wind = {rec.keys[0]:rec.level for rec in db_postDC["P_wind"]}
P_DC_pf = {rec.keys[0]:rec.level for rec in db_postDC["pf0"]}
theta_DC = {rec.keys[0]:rec.level for rec in db_postDC["theta0"]}

cost = db_postDC["total_cost"].first_record().level
if WITH_PRESCIENT:
    deviation = db_postDC["deviation"].first_record().level

for key in P_DC_thermal:
    P_DC_thermal[key] = round(P_DC_thermal[key], 4)

if WITH_PRESCIENT:
    print('Deviation:', round(deviation, 2))
else:
    print('Cost', cost)


if network_name == 'RTS':
    on_DC = {rec.keys[0]:rec.level for rec in db_postDC["on"]}
elif network_name == 'Texas':  # Network too large to run a mixed-integer DCOPF, so all generators are considered on
    on_DC = {i+1: 1 if P_DC_thermal[str(i+1)] > 1e-3 else 0 for i in range(N_thermal_gens)}
else:
    raise


#####
# ACOPF
#####
print('\nACOPF')

thermal_min = thermal_min * np.array(list(on_DC.values()))
thermal_max = thermal_max * np.array(list(on_DC.values()))

Y = np.zeros((N_buses, N_buses), complex)
branch_FromFrom = np.zeros(N_branches, complex)
branch_FromTo = np.zeros(N_branches, complex)
branch_ToFrom = np.zeros(N_branches, complex)
branch_ToTo = np.zeros(N_branches, complex)

for i in range(N_branches):
    # Line and transformer models according to https://www.powsybl.org/pages/documentation/grid/model/ (note transformers are gamma models and not pi ones)
    z = branches['R'][i] + 1j * branches['X'][i]
    tap = branches['Tr Ratio'][i]
    if tap == 0:  # Line
        y1 = 1j * branches['B'][i] / 2
        y2 = 1j * branches['B'][i] / 2
        branch_FromFrom[i] = y1 + 1/z
        branch_FromTo[i] = -1/z
        branch_ToFrom[i] = -1/z
        branch_ToTo[i] = y2 + 1/z
    else:  # Transformer (no phase shift in RTS data format)
        tap = 1/tap  # Inverse conventions in Powsybl and RTS/Matpower
        y = 1j * branches['B'][i]
        branch_FromFrom[i] = (y/2 + 1/z) * tap**2
        branch_FromTo[i] = -1/z * tap
        branch_ToFrom[i] = -1/z * tap
        branch_ToTo[i] = 1/z + y/2

    Y[branches['From Bus'][i]][branches['From Bus'][i]] += branch_FromFrom[i]
    Y[branches['From Bus'][i]][branches['To Bus'][i]] += branch_FromTo[i]
    Y[branches['To Bus'][i]][branches['From Bus'][i]] += branch_ToFrom[i]
    Y[branches['To Bus'][i]][branches['To Bus'][i]] += branch_ToTo[i]

G = Y.real
B = Y.imag
G_branch_FromFrom = branch_FromFrom.real
B_branch_FromFrom = branch_FromFrom.imag
G_branch_FromTo = branch_FromTo.real
B_branch_FromTo = branch_FromTo.imag
G_branch_ToFrom = branch_ToFrom.real
B_branch_ToFrom = branch_ToFrom.imag
G_branch_ToTo = branch_ToTo.real
B_branch_ToTo = branch_ToTo.imag


# Run a first AC load flow to initialise the AC OPF
demand_bus_Q = np.zeros(N_buses)
for i in range(N_buses):
    if loads_P[i] != 0:
        demand_bus_Q[i] = loads_Q[i]/loads_P[i] * demand_bus[i]
    else:
        demand_bus_Q[i] = 0
    demand_bus_Q[i] += - buses['MVAR Shunt B'][i] / baseMVA

network = pp.network.load(f'../{network_name}-Data/{network_name}.iidm')
thermal_connected = [True if on == 1 else False for on in on_DC.values()]

opf_results_to_powsybl(network, thermal_gens, thermal_connected, P_DC_thermal, Q_AC_thermal,
                           hydro_gens, P_DC_hydro, Q_AC_hydro, hydro_max,
                           wind_gens, P_DC_wind, Q_AC_wind, wind_max,
                           pv_gens, P_DC_pv, Q_AC_pv, pv_max,
                           rtpv_gens, rtpv_max,
                           syncon_gens, Q_AC_syncon,
                           buses, demand_bus, demand_bus_Q,
                           gens, V_AC)


load_ids = ['L-'+str(int(buses['Bus ID'][i])) for i in range(N_buses)]
for i in range(N_buses):
    if loads_P[i] != 0:
        demand_bus_Q[i] = loads_Q[i]/loads_P[i] * demand_bus[i]
    else:
        demand_bus_Q[i] = 0
    # demand_bus_Q[i] += - buses['MVAR Shunt B'][i] / baseMVA
network.update_loads(id=load_ids, q0=demand_bus_Q * baseMVA)

# Represent shunts as static var compensators because continuous variables are easier to manage in an OPF. They will be put back
# as negative loads for the PSCACOPF (assume shunts do not directly react following disturbances (as capacitor banks do not react
# before a few dozens seconds to minutes))
shunt_indices = []
shunt_Qmin = []
shunt_Qmax = []
for i in range(N_buses):
    Q_shunt = buses['MVAR Shunt B'][i] / baseMVA
    bus_id = str(int(buses['Bus ID'][i]))
    if Q_shunt != 0:
        shunt_indices.append(i)
        # shunt_capability = [0, Q_shunt]
        # Q_min, Q_max = min(shunt_capability), max(shunt_capability)
        Q_max = abs(Q_shunt)  # Assuming shunts can go both directions (otherwise Texas case does not converge)
        Q_min = -abs(Q_shunt)
        shunt_Qmin.append(Q_min)
        shunt_Qmax.append(Q_max)
        b_min = Q_min * baseMVA / buses['BaseKV'][i]**2
        b_max = Q_max * baseMVA / buses['BaseKV'][i]**2
        network.create_static_var_compensators(id = 'Shunt-' + bus_id, voltage_level_id='V-' + bus_id, bus_id='B-' + bus_id,
                                                b_max = b_max, b_min = b_min,
                                                target_v=buses['V Mag'][i] * buses['BaseKV'][i], regulation_mode='VOLTAGE')
N_shunts = len(shunt_indices)

shunt_map = np.zeros((N_shunts, N_buses))
for i in range(N_shunts):
    shunt_map[i][buses['Bus ID'].index(buses['Bus ID'][shunt_indices[i]])] = 1

sol = pp.loadflow.run_dc(network)
print(sol)
sol = pp.loadflow.run_ac(network)
print(sol)

if str(sol[0].status) == 'ComponentStatus.MAX_ITERATION_REACHED' or str(sol[0].status) == 'ComponentStatus.FAILED':
    parameters = pp.loadflow.Parameters(no_generator_reactive_limits = True)
    sol = pp.loadflow.run_ac(network, parameters)
    print('Warning: Non convergence of initial load flow, retrying without reactive limits')
    if str(sol[0].status) == 'ComponentStatus.MAX_ITERATION_REACHED' or str(sol[0].status) == 'ComponentStatus.FAILED':
        raise RuntimeError('Non convergence of initial load flow, even without reactive limits')

gen_results = network.get_generators()
np.nan_to_num(gen_results['p'], copy=False)  # Set 0 output for disconnected generators instead of nan
np.nan_to_num(gen_results['q'], copy=False)
P_AC_thermal = {}
P_AC_hydro = {}
P_AC_wind = {}
P_AC_pv = {}
for i in range(N_thermal_gens):
    P_AC_thermal[i+1] = -gen_results['p'][thermal_gens['GEN UID'][i]] / baseMVA  # Receptor convention
    Q_AC_thermal[i+1] = -gen_results['q'][thermal_gens['GEN UID'][i]] / baseMVA
for i in range(N_hydro_gens):
    P_AC_hydro[i+1] = -gen_results['p'][hydro_gens['GEN UID'][i]] / baseMVA
    Q_AC_hydro[i+1] = -gen_results['q'][hydro_gens['GEN UID'][i]] / baseMVA
for i in range(N_wind_gens):
    P_AC_wind[i+1] = -gen_results['p'][wind_gens['GEN UID'][i]] / baseMVA
    Q_AC_wind[i+1] = -gen_results['q'][wind_gens['GEN UID'][i]] / baseMVA
for i in range(N_pv_gens):
    P_AC_pv[i+1] = -gen_results['p'][pv_gens['GEN UID'][i]] / baseMVA
    Q_AC_pv[i+1] = -gen_results['q'][pv_gens['GEN UID'][i]] / baseMVA
for i in range(N_syncon_gens):
    Q_AC_syncon[i+1] = -gen_results['q'][syncon_gens['GEN UID'][i]] / baseMVA

shunt_results = network.get_static_var_compensators()
Q_AC_shunt = {}
for i in range(N_shunts):
    Q_AC_shunt[i+1] = -shunt_results['q']['Shunt-' + str(int(buses['Bus ID'][shunt_indices[i]]))] / baseMVA

V = []
theta = []
bus_results = network.get_buses()
vl_results = network.get_voltage_levels()
for i in range(N_buses):
    id = int(buses['Bus ID'][i])
    bus_id = 'V-' + str(id) + '_0'  # Powsybl renames buses for fun
    vl_id = 'V-' + str(id)
    V_bus = bus_results.loc[bus_id, 'v_mag'] / vl_results.loc[vl_id, 'nominal_v']
    V.append(V_bus)
    theta.append(bus_results.loc[bus_id, 'v_angle'] * pi/180)

    if V_bus < 0.9 or V_bus > 1.1:
        print('Warning: unacceptable voltage at bus', bus_id, 'in initial load flow', V_bus)
    elif V_bus < 0.95 or V_bus > 1.08:
        print('Warning: problematic voltage  at bus', bus_id, 'in initial load flow', V_bus)

theta_AC = {}
for i in range(N_buses):
    V_AC[i+1] = V[i]
    theta_AC[i+1] = theta[i]

P1 = np.zeros(N_branches)
Q1 = np.zeros(N_branches)
line_results = network.get_lines()
transformer_results = network.get_2_windings_transformers()
for i in range(N_branches):
    UID = branches['UID'][i]
    if branches['Tr Ratio'][i] == 0:
        P1[i] = line_results['p1'][UID] / baseMVA
        Q1[i] = line_results['q1'][UID] / baseMVA
    else:
        P1[i] = transformer_results['p1'][UID] / baseMVA
        Q1[i] = transformer_results['q1'][UID] / baseMVA


if tmp_path is None:
    acopf_path = os.path.join(os.getcwd(), 'b-ACOPF', str(hour))
else:
    acopf_path = os.path.join(tmp_path, 'b-ACOPF', str(hour))
Path(acopf_path).mkdir(parents=True, exist_ok=True)
ws = gams.GamsWorkspace(working_directory=acopf_path, debug=gams.DebugLevel.Off) # Off, KeepFilesOnError, KeepFiles, ShowLog, Verbose
db_preAC = ws.add_database()
shutil.copy(os.path.join('b-ACOPF', 'ipopt.opt'), acopf_path)

i_thermal = addGamsSet(db_preAC, 'i_thermal', 'thermal generators', range(1, N_thermal_gens + 1))
i_hydro = addGamsSet(db_preAC, 'i_hydro', 'hydro generators', range(1, N_hydro_gens + 1))
i_pv = addGamsSet(db_preAC, 'i_pv', 'pv generators', range(1, N_pv_gens + 1))
i_wind = addGamsSet(db_preAC, 'i_wind', 'wind generators', range(1, N_wind_gens + 1))
i_rtpv = addGamsSet(db_preAC, 'i_rtpv', 'rtpv generators', range(1, N_rtpv_gens + 1))
i_syncon = addGamsSet(db_preAC, 'i_syncon', 'syncon generators', range(1, N_syncon_gens + 1))
i_shunt = addGamsSet(db_preAC, 'i_shunt', 'shunts', range(1, N_shunts + 1))
i_bus = addGamsSet(db_preAC, 'i_bus', 'buses', range(1, N_buses + 1))
i_branch = addGamsSet(db_preAC, 'i_branch', 'branches', range(1, N_branches + 1))

addGamsParams(db_preAC, 'thermal_map', 'thermal generators map', [i_thermal, i_bus], thermal_gen_map)
addGamsParams(db_preAC, 'hydro_map', 'hydro generators map', [i_hydro, i_bus], hydro_gen_map)
addGamsParams(db_preAC, 'pv_map', 'pv generators map', [i_pv, i_bus], pv_gen_map)
addGamsParams(db_preAC, 'wind_map', 'wind generators map', [i_wind, i_bus], wind_gen_map)
addGamsParams(db_preAC, 'rtpv_map', 'rtpv generators map', [i_rtpv, i_bus], rtpv_gen_map)
addGamsParams(db_preAC, 'syncon_map', 'syncon generators map', [i_syncon, i_bus], syncon_gen_map)
addGamsParams(db_preAC, 'shunt_map', 'shunt generators map', [i_shunt, i_bus], shunt_map)
addGamsParams(db_preAC, 'branch_map', 'branches map', [i_branch, i_bus], branch_map)

addGamsParams(db_preAC, 'thermal_min', 'thermal generator minimum generation', [i_thermal], thermal_min)
addGamsParams(db_preAC, 'thermal_max', 'thermal generator maximum generation', [i_thermal], thermal_max)
addGamsParams(db_preAC, 'hydro_max', 'hydro generator maximum generation', [i_hydro], hydro_max)
addGamsParams(db_preAC, 'pv_max', 'pv generator maximum generation', [i_pv], pv_max)
addGamsParams(db_preAC, 'wind_max', 'wind generator maximum generation', [i_wind], wind_max)
addGamsParams(db_preAC, 'rtpv_max', 'rtpv generator maximum generation', [i_rtpv], rtpv_max)
thermal_Qmin = np.array(thermal_gens['QMin MVAR']) / baseMVA * np.array(list(on_DC.values()))
thermal_Qmax = np.array(thermal_gens['QMax MVAR']) / baseMVA * np.array(list(on_DC.values()))
hydro_Qmin = np.array(hydro_gens['QMin MVAR']) / baseMVA
hydro_Qmax = np.array(hydro_gens['QMax MVAR']) / baseMVA
syncon_Qmin = np.array(syncon_gens['QMin MVAR']) / baseMVA
syncon_Qmax = np.array(syncon_gens['QMax MVAR']) / baseMVA
pv_connected = []
for P_pv in P_DC_pv.values():
    if P_pv > 0:
        pv_connected.append(1)
    else:
        pv_connected.append(0)
pv_Qmin = np.array(pv_gens['QMin MVAR']) / baseMVA * np.array(pv_connected)
pv_Qmax = np.array(pv_gens['QMax MVAR']) / baseMVA * np.array(pv_connected)
wind_Qmin = np.array(wind_gens['QMin MVAR']) / baseMVA
wind_Qmax = np.array(wind_gens['QMax MVAR']) / baseMVA
addGamsParams(db_preAC, 'thermal_Qmin', 'thermal generator minimum reactive generation', [i_thermal], thermal_Qmin)
addGamsParams(db_preAC, 'thermal_Qmax', 'thermal generator maximum reactive generation', [i_thermal], thermal_Qmax)
addGamsParams(db_preAC, 'hydro_Qmin', 'hydro generator minimum reactive generation', [i_hydro], hydro_Qmin)
addGamsParams(db_preAC, 'hydro_Qmax', 'hydro generator maximum reactive generation', [i_hydro], hydro_Qmax)
addGamsParams(db_preAC, 'syncon_Qmin', 'syncon generator minimum reactive generation', [i_syncon], syncon_Qmin)
addGamsParams(db_preAC, 'syncon_Qmax', 'syncon generator maximum reactive generation', [i_syncon], syncon_Qmax)
addGamsParams(db_preAC, 'shunt_Qmin', 'shunt generator minimum reactive generation', [i_shunt], shunt_Qmin)
addGamsParams(db_preAC, 'shunt_Qmax', 'shunt generator maximum reactive generation', [i_shunt], shunt_Qmax)
addGamsParams(db_preAC, 'pv_Qmin', 'pv generator minimum reactive generation', [i_pv], pv_Qmin)
addGamsParams(db_preAC, 'pv_Qmax', 'pv generator maximum reactive generation', [i_pv], pv_Qmax)
addGamsParams(db_preAC, 'wind_Qmin', 'wind generator minimum reactive generation', [i_wind], wind_Qmin)
addGamsParams(db_preAC, 'wind_Qmax', 'wind generator maximum reactive generation', [i_wind], wind_Qmax)

addGamsParams(db_preAC, 'G', 'conductance matrix', [i_bus, i_bus], G)
addGamsParams(db_preAC, 'B', 'susceptance matrix', [i_bus, i_bus], B)
addGamsParams(db_preAC, 'Gff', 'line conductance (from-from)', [i_branch], G_branch_FromFrom)
addGamsParams(db_preAC, 'Gft', 'line conductance (from-to)', [i_branch], G_branch_FromTo)
addGamsParams(db_preAC, 'Bff', 'line susceptance (from-from)', [i_branch], B_branch_FromFrom)
addGamsParams(db_preAC, 'Bft', 'line susceptance (from-to)', [i_branch], B_branch_FromTo)
addGamsParams(db_preAC, 'branch_max_N', 'Normal branch max power', [i_branch], cont_rating / baseMVA)

addGamsParams(db_preAC, 'demand', 'demand at each bus', [i_bus], demand_bus)
addGamsParams(db_preAC, 'demandQ', 'reactive demand at each bus', [i_bus], demand_bus_Q)

addGamsParams(db_preAC, 'P_thermal_0', 'Initial thermal outputs', [i_thermal], list(P_AC_thermal.values()))
addGamsParams(db_preAC, 'P_hydro_0', 'Initial hydro outputs', [i_hydro], list(P_AC_hydro.values()))
addGamsParams(db_preAC, 'P_pv_0', 'Initial pv outputs', [i_pv], list(P_AC_pv.values()))
addGamsParams(db_preAC, 'P_wind_0', 'Initial wind outputs', [i_wind], list(P_AC_wind.values()))
addGamsParams(db_preAC, 'Ppf_0', 'Initial line active power flows', [i_branch], P1)
addGamsParams(db_preAC, 'Q_thermal_0', 'Initial thermal reactive outputs', [i_thermal], list(Q_AC_thermal.values()))
addGamsParams(db_preAC, 'Q_hydro_0', 'Initial hydro reactive outputs', [i_hydro], list(Q_AC_hydro.values()))
addGamsParams(db_preAC, 'Q_syncon_0', 'Initial syncon reactive outputs', [i_syncon], list(Q_AC_syncon.values()))
addGamsParams(db_preAC, 'Q_shunt_0', 'Initial shunt reactive outputs', [i_shunt], list(Q_AC_shunt.values()))
addGamsParams(db_preAC, 'Q_pv_0', 'Initial pv reactive outputs', [i_pv], list(Q_AC_pv.values()))
addGamsParams(db_preAC, 'Q_wind_0', 'Initial wind reactive outputs', [i_wind], list(Q_AC_wind.values()))
addGamsParams(db_preAC, 'Qpf_0', 'Initial line active power flows', [i_branch], Q1)
addGamsParams(db_preAC, 'V_0', 'Initial voltages', [i_bus], list(V_AC.values()))
addGamsParams(db_preAC, 'theta_0', 'Initial angles', [i_bus], list(theta_AC.values()))

db_preAC.export('PreACOPF.gdx')
t = ws.add_job_from_file(os.path.join(os.getcwd(), 'b-ACOPF', 'ACOPF.gms'))
print('Launching GAMS')
t.run()

db_postAC = ws.add_database_from_gdx("PostACOPF.gdx")

solve_status = int(db_postAC["sol"].first_record().value)
if solve_status != 1 and solve_status != 2 and solve_status != 7:
    raise RuntimeError('ACOPF: no solution found, error code:', solve_status)
print('ACOPF solution found')

P_AC_thermal = {rec.keys[0]:rec.level for rec in db_postAC["P_thermal"]}
P_AC_hydro = {rec.keys[0]:rec.level for rec in db_postAC["P_hydro"]}
P_AC_pv = {rec.keys[0]:rec.level for rec in db_postAC["P_pv"]}
P_AC_wind = {rec.keys[0]:rec.level for rec in db_postAC["P_wind"]}

Q_AC_thermal = {rec.keys[0]:rec.level for rec in db_postAC["Q_thermal"]}
Q_AC_hydro = {rec.keys[0]:rec.level for rec in db_postAC["Q_hydro"]}
Q_AC_syncon = {rec.keys[0]:rec.level for rec in db_postAC["Q_syncon"]}
Q_AC_shunt = {rec.keys[0]:rec.level for rec in db_postAC["Q_shunt"]}
Q_AC_pv = {rec.keys[0]:rec.level for rec in db_postAC["Q_pv"]}
Q_AC_wind = {rec.keys[0]:rec.level for rec in db_postAC["Q_wind"]}

V_AC = {rec.keys[0]:rec.level for rec in db_postAC["V"]}
theta_AC = {rec.keys[0]:rec.level for rec in db_postAC["theta"]}

deviation = db_postAC["deviation"].first_record().level

print('Demand + estimated losses:', sum(demand_bus) * (1 + losses))
print('Generation:',
      sum(P_AC_thermal.values()) +
      sum(P_AC_hydro.values()) +
      sum(P_AC_pv.values()) +
      sum(P_AC_wind.values()) +
      sum(rtpv_max))

print('Deviation:', round(deviation, 2))

#####
# PSCACOPF
#####
print('\nPSCACOPF')

network = pp.network.load(f'../{network_name}-Data/{network_name}.iidm')  # Reload network, this remove static var compensators that are now represented as loads

# Model shunts as negative loads
load_ids = ['L-'+str(int(buses['Bus ID'][i])) for i in range(N_buses)]
Q_bus_shunt = np.array(list(Q_AC_shunt.values())) @ shunt_map
for i in range(N_buses):
    if loads_P[i] != 0:
        demand_bus_Q[i] = loads_Q[i]/loads_P[i] * demand_bus[i]
    else:
        demand_bus_Q[i] = 0
    demand_bus_Q[i] += - Q_bus_shunt[i]

thermal_connected = [True if on == 1 else False for on in on_DC.values()]

opf_results_to_powsybl(network, thermal_gens, thermal_connected, P_AC_thermal, Q_AC_thermal,
                           hydro_gens, P_AC_hydro, Q_AC_hydro, hydro_max,
                           wind_gens, P_AC_wind, Q_AC_wind, wind_max,
                           pv_gens, P_AC_pv, Q_AC_pv, pv_max,
                           rtpv_gens, rtpv_max,
                           syncon_gens, Q_AC_syncon,
                           buses, demand_bus, demand_bus_Q,
                           gens, V_AC)


critical_contingencies = []  # Contingencies that lead to issues and have to be included in the PSCACOPF (iteratively added to the problem)
while True:
    print(pp.loadflow.run_ac(network))

    if network_name == 'Texas':
        break  # Network too large to fully consider AC constraints with my current knowledge and time limitations

    P1 = np.zeros(N_branches)
    Q1 = np.zeros(N_branches)
    P2 = np.zeros(N_branches)
    Q2 = np.zeros(N_branches)
    line_results = network.get_lines()
    transformer_results = network.get_2_windings_transformers()
    for i in range(N_branches):
        UID = branches['UID'][i]
        if branches['Tr Ratio'][i] == 0:
            P1[i] = line_results['p1'][UID] / baseMVA
            Q1[i] = line_results['q1'][UID] / baseMVA
            P2[i] = line_results['p2'][UID] / baseMVA
            Q2[i] = line_results['q2'][UID] / baseMVA
        else:
            P1[i] = transformer_results['p1'][UID] / baseMVA
            Q1[i] = transformer_results['q1'][UID] / baseMVA
            P2[i] = transformer_results['p2'][UID] / baseMVA
            Q2[i] = transformer_results['q2'][UID] / baseMVA

    P1_cont = np.zeros((N_branches, N_branches))
    Q1_cont = np.zeros((N_branches, N_branches))
    P2_cont = np.zeros((N_branches, N_branches))
    Q2_cont = np.zeros((N_branches, N_branches))
    Q_thermal_cont = np.zeros((N_thermal_gens, N_branches))
    Q_hydro_cont = np.zeros((N_hydro_gens, N_branches))
    Q_syncon_cont = np.zeros((N_syncon_gens, N_branches))
    Q_pv_cont = np.zeros((N_pv_gens, N_branches))
    Q_wind_cont = np.zeros((N_wind_gens, N_branches))
    V_cont = np.zeros((N_buses, N_branches))
    theta_cont = np.zeros((N_buses, N_branches))

    # Compute power flows for each N-1 contingency
    current_critical_contingencies = []
    for j in considered_contingencies:
        print('Running load flow for contingency of line', branches['UID'][j], end='\r')
        # Disconnect line (or transformer)
        if branches['Tr Ratio'][j] == 0:
            network.update_lines(id=branches['UID'][j], connected1=False, connected2=False)
        else:
            network.update_2_windings_transformers(id=branches['UID'][j], connected1=False, connected2=False)

        sol = pp.loadflow.run_ac(network)
        if str(sol[0].status) == 'ComponentStatus.MAX_ITERATION_REACHED':
            print('Non convergence for contingency of line', branches['UID'][j])
            parameters = pp.loadflow.Parameters(no_generator_reactive_limits = True)
            sol = pp.loadflow.run_ac(network, parameters)
            print(sol)

            if j not in current_critical_contingencies:
                current_critical_contingencies.append(j)
                print('Critical contingency', branches['UID'][j], ': non converging power flow (with reactive limits)')

            if str(sol[0].status) == 'ComponentStatus.MAX_ITERATION_REACHED':
                raise RuntimeError('Load flow did not converge (even without reactive limits) for contingency of line', branches['UID'][j])

            # Find buses with lack/too much reactive power for further investigation
            gen_results = network.get_generators()
            np.nan_to_num(gen_results['q'], copy=False)
            for i in range(N_buses):
                q_bus_tot = 0
                q_bus_min = 0
                q_bus_max = 0
                for g in range(N_thermal_gens):
                    if thermal_gens['Bus ID'][g] == buses['Bus ID'][i]:
                        q_bus_tot += -gen_results['q'][thermal_gens['GEN UID'][g]] / baseMVA  # Receptor convention
                        q_bus_min += thermal_Qmin[g]
                        q_bus_max += thermal_Qmax[g]
                for g in range(N_hydro_gens):
                    if hydro_gens['Bus ID'][g] == buses['Bus ID'][i]:
                        q_bus_tot += -gen_results['q'][hydro_gens['GEN UID'][g]] / baseMVA
                        q_bus_min += hydro_Qmin[g]
                        q_bus_max += hydro_Qmax[g]
                for g in range(N_syncon_gens):
                    if syncon_gens['Bus ID'][g] == buses['Bus ID'][i]:
                        q_bus_tot += -gen_results['q'][syncon_gens['GEN UID'][g]] / baseMVA
                        q_bus_min += syncon_Qmin[g]
                        q_bus_max += syncon_Qmax[g]
                for g in range(N_pv_gens):
                    if pv_gens['Bus ID'][g] == buses['Bus ID'][i]:
                        q_bus_tot += -gen_results['q'][pv_gens['GEN UID'][g]] / baseMVA
                        q_bus_min += pv_Qmin[g]
                        q_bus_max += pv_Qmax[g]
                for g in range(N_wind_gens):
                    if wind_gens['Bus ID'][g] == buses['Bus ID'][i]:
                        q_bus_tot += -gen_results['q'][wind_gens['GEN UID'][g]] / baseMVA
                        q_bus_min += wind_Qmin[g]
                        q_bus_max += wind_Qmax[g]
                if q_bus_min > q_bus_tot:
                    print('Too much reactive power at bus', int(buses['Bus ID'][i]), 'for contingency of line', branches['UID'][j])
                    print(q_bus_min, q_bus_tot)
                if q_bus_tot > q_bus_max:
                    print('Lack of reactive power at bus', int(buses['Bus ID'][i]), 'for contingency of line', branches['UID'][j])
                    print(q_bus_tot, q_bus_max)
            # raise RuntimeError('Load flow did not converge (when considering reactive limits) for contingency of line', branches['UID'][j])

        # Reconnect line
        if branches['Tr Ratio'][j] == 0:
            network.update_lines(id=branches['UID'][j], connected1=True, connected2=True)
        else:
            network.update_2_windings_transformers(id=branches['UID'][j], connected1=True, connected2=True)

        line_results = network.get_lines()
        transformer_results = network.get_2_windings_transformers()
        for i in range(N_branches):
            UID = branches['UID'][i]
            if branches['Tr Ratio'][i] == 0:
                P1_cont[i][j] = line_results['p1'][UID] / baseMVA
                Q1_cont[i][j] = line_results['q1'][UID] / baseMVA
                P2_cont[i][j] = line_results['p2'][UID] / baseMVA
                Q2_cont[i][j] = line_results['q2'][UID] / baseMVA
            else:
                P1_cont[i][j] = transformer_results['p1'][UID] / baseMVA
                Q1_cont[i][j] = transformer_results['q1'][UID] / baseMVA
                P2_cont[i][j] = transformer_results['p2'][UID] / baseMVA
                Q2_cont[i][j] = transformer_results['q2'][UID] / baseMVA
        for i in range(N_branches):
            P1_cont[i][i] = 0  # There is no flow in the disconnected line (but Powsybl returns NaN)
            Q1_cont[i][i] = 0
            P2_cont[i][i] = 0
            Q2_cont[i][i] = 0

        gen_results = network.get_generators()
        np.nan_to_num(gen_results['q'], copy=False)  # Set 0 Q output for disconnected generators instead of nan
        for i in range(N_thermal_gens):
            Q_thermal_cont[i][j] = -gen_results['q'][thermal_gens['GEN UID'][i]] / baseMVA  # Receptor convention
        for i in range(N_hydro_gens):
            Q_hydro_cont[i][j] = -gen_results['q'][hydro_gens['GEN UID'][i]] / baseMVA
        for i in range(N_syncon_gens):
            Q_syncon_cont[i][j] = -gen_results['q'][syncon_gens['GEN UID'][i]] / baseMVA
        for i in range(N_pv_gens):
            Q_pv_cont[i][j] = -gen_results['q'][pv_gens['GEN UID'][i]] / baseMVA
        for i in range(N_wind_gens):
            Q_wind_cont[i][j] = -gen_results['q'][wind_gens['GEN UID'][i]] / baseMVA

        V = []
        theta = []
        bus_results = network.get_buses()
        vl_results = network.get_voltage_levels()
        for i in range(N_buses):
            id = int(buses['Bus ID'][i])
            bus_id = 'V-' + str(id) + '_0'  # Powsybl renames buses for fun
            vl_id = 'V-' + str(id)
            V.append(bus_results.loc[bus_id, 'v_mag'] / vl_results.loc[vl_id, 'nominal_v'])
            theta.append(bus_results.loc[bus_id, 'v_angle'] * pi/180)
        V_cont[:,j] = np.array(V)
        theta_cont[:,j] = np.array(theta)

    # Check contingencies that lead to issues with the current dispatch
    for j in considered_contingencies:
        for i in range(N_branches):
            if (P1_cont[i][j]**2 + Q1_cont[i][j]**2)**0.5 > 1.05 * lte_rating[i] / baseMVA:
                if j not in current_critical_contingencies:
                    current_critical_contingencies.append(j)
                    print('Critical contingency', branches['UID'][j], ': high current in branch', branches['UID'][i], ':', (P1_cont[i][j]**2 + Q1_cont[i][j]**2)**0.5 * baseMVA,  '>', lte_rating[i])
        for i in range(N_buses):
            if V_cont[i,j] < 0.8499:  # Note: this neglects buses with nan voltage (disconnected)
                if j not in current_critical_contingencies:
                    current_critical_contingencies.append(j)
                    print('Critical contingency', branches['UID'][j], ': low voltage at bus', int(buses['Bus ID'][i]), V_cont[i,j])

    if set(current_critical_contingencies).issubset(critical_contingencies):  # No new critical contingencies compared to last iteration
        break

    for j in current_critical_contingencies:
        if j not in critical_contingencies:
            critical_contingencies.append(j)
            break  # Only add one contingency at a time to the OPF problem

    print()
    print()
    print('Running PSCACOPF for contingencies of lines: ', [branches['UID'][i] for i in critical_contingencies])

    if tmp_path is None:
        pscacopf_path = os.path.join(os.getcwd(), 'c-PSCACOPF', str(hour))
    else:
        pscacopf_path = os.path.join(tmp_path, 'c-PSCACOPF', str(hour))
    Path(pscacopf_path).mkdir(parents=True, exist_ok=True)
    ws = gams.GamsWorkspace(working_directory=pscacopf_path, debug=gams.DebugLevel.Off)
    db_prePSCAC = ws.add_database()
    shutil.copy(os.path.join('c-PSCACOPF', 'ipopt.opt'), pscacopf_path)

    i_thermal = addGamsSet(db_prePSCAC, 'i_thermal', 'thermal generators', range(1, N_thermal_gens + 1))
    i_hydro = addGamsSet(db_prePSCAC, 'i_hydro', 'hydro generators', range(1, N_hydro_gens + 1))
    i_pv = addGamsSet(db_prePSCAC, 'i_pv', 'pv generators', range(1, N_pv_gens + 1))
    i_wind = addGamsSet(db_prePSCAC, 'i_wind', 'wind generators', range(1, N_wind_gens + 1))
    i_rtpv = addGamsSet(db_prePSCAC, 'i_rtpv', 'rtpv generators', range(1, N_rtpv_gens + 1))
    i_syncon = addGamsSet(db_prePSCAC, 'i_syncon', 'syncon generators', range(1, N_syncon_gens + 1))
    i_bus = addGamsSet(db_prePSCAC, 'i_bus', 'buses', range(1, N_buses + 1))
    i_branch = addGamsSet(db_prePSCAC, 'i_branch', 'branches', range(1, N_branches + 1))
    i_contingency = addGamsSet(db_prePSCAC, 'i_contingency', 'contingencies', range(1, 1 + len(critical_contingencies)))

    addGamsParams(db_prePSCAC, 'thermal_map', 'thermal generators map', [i_thermal, i_bus], thermal_gen_map)
    addGamsParams(db_prePSCAC, 'hydro_map', 'hydro generators map', [i_hydro, i_bus], hydro_gen_map)
    addGamsParams(db_prePSCAC, 'pv_map', 'pv generators map', [i_pv, i_bus], pv_gen_map)
    addGamsParams(db_prePSCAC, 'wind_map', 'wind generators map', [i_wind, i_bus], wind_gen_map)
    addGamsParams(db_prePSCAC, 'rtpv_map', 'rtpv generators map', [i_rtpv, i_bus], rtpv_gen_map)
    addGamsParams(db_prePSCAC, 'syncon_map', 'syncon generators map', [i_syncon, i_bus], syncon_gen_map)
    addGamsParams(db_prePSCAC, 'branch_map', 'branches map', [i_branch, i_bus], branch_map)

    addGamsParams(db_prePSCAC, 'thermal_min', 'thermal generator minimum generation', [i_thermal], thermal_min)
    addGamsParams(db_prePSCAC, 'thermal_max', 'thermal generator maximum generation', [i_thermal], thermal_max)
    addGamsParams(db_prePSCAC, 'hydro_max', 'hydro generator maximum generation', [i_hydro], hydro_max)
    addGamsParams(db_prePSCAC, 'pv_max', 'pv generator maximum generation', [i_pv], pv_max)
    addGamsParams(db_prePSCAC, 'wind_max', 'wind generator maximum generation', [i_wind], wind_max)
    addGamsParams(db_prePSCAC, 'rtpv_max', 'rtpv generator maximum generation', [i_rtpv], rtpv_max)

    addGamsParams(db_prePSCAC, 'thermal_Qmin', 'thermal generator minimum reactive generation', [i_thermal], thermal_Qmin)
    addGamsParams(db_prePSCAC, 'thermal_Qmax', 'thermal generator maximum reactive generation', [i_thermal], thermal_Qmax)
    addGamsParams(db_prePSCAC, 'hydro_Qmin', 'hydro generator minimum reactive generation', [i_hydro], hydro_Qmin)
    addGamsParams(db_prePSCAC, 'hydro_Qmax', 'hydro generator maximum reactive generation', [i_hydro], hydro_Qmax)
    addGamsParams(db_prePSCAC, 'syncon_Qmin', 'syncon generator minimum reactive generation', [i_syncon], syncon_Qmin)
    addGamsParams(db_prePSCAC, 'syncon_Qmax', 'syncon generator maximum reactive generation', [i_syncon], syncon_Qmax)
    addGamsParams(db_prePSCAC, 'pv_Qmin', 'pv generator minimum reactive generation', [i_pv], pv_Qmin)
    addGamsParams(db_prePSCAC, 'pv_Qmax', 'pv generator maximum reactive generation', [i_pv], pv_Qmax)
    addGamsParams(db_prePSCAC, 'wind_Qmin', 'wind generator minimum reactive generation', [i_wind], wind_Qmin)
    addGamsParams(db_prePSCAC, 'wind_Qmax', 'wind generator maximum reactive generation', [i_wind], wind_Qmax)

    addGamsParams(db_prePSCAC, 'Gff', 'line conductance (from-from)', [i_branch], G_branch_FromFrom)
    addGamsParams(db_prePSCAC, 'Bff', 'line susceptance (from-from)', [i_branch], B_branch_FromFrom)
    addGamsParams(db_prePSCAC, 'Gft', 'line conductance (from-to)', [i_branch], G_branch_FromTo)
    addGamsParams(db_prePSCAC, 'Bft', 'line susceptance (from-to)', [i_branch], B_branch_FromTo)
    addGamsParams(db_prePSCAC, 'Gtf', 'line conductance (to-from)', [i_branch], G_branch_ToFrom)
    addGamsParams(db_prePSCAC, 'Btf', 'line susceptance (to-from)', [i_branch], B_branch_ToFrom)
    addGamsParams(db_prePSCAC, 'Gtt', 'line conductance (to-to)', [i_branch], G_branch_ToTo)
    addGamsParams(db_prePSCAC, 'Btt', 'line susceptance (to-to)', [i_branch], B_branch_ToTo)
    addGamsParams(db_prePSCAC, 'branch_max_N', 'Normal branch max power', [i_branch], cont_rating / baseMVA)
    addGamsParams(db_prePSCAC, 'branch_max_E', 'Emergency branch max power', [i_branch], lte_rating / baseMVA)

    addGamsParams(db_prePSCAC, 'contingency_states', 'Line states in the considered contingencies', [i_branch, i_contingency], contingency_states[:, critical_contingencies])

    addGamsParams(db_prePSCAC, 'demand', 'demand at each bus', [i_bus], demand_bus)
    addGamsParams(db_prePSCAC, 'demandQ', 'reactive demand at each bus', [i_bus], demand_bus_Q)

    addGamsParams(db_prePSCAC, 'P_thermal_0', 'Initial thermal outputs', [i_thermal], list(P_AC_thermal.values()))
    addGamsParams(db_prePSCAC, 'P_hydro_0', 'Initial hydro outputs', [i_hydro], list(P_AC_hydro.values()))
    addGamsParams(db_prePSCAC, 'P_pv_0', 'Initial pv outputs', [i_pv], list(P_AC_pv.values()))
    addGamsParams(db_prePSCAC, 'P_wind_0', 'Initial wind outputs', [i_wind], list(P_AC_wind.values()))
    addGamsParams(db_prePSCAC, 'Q_thermal_0', 'Initial thermal reactive outputs', [i_thermal], list(Q_AC_thermal.values()))
    addGamsParams(db_prePSCAC, 'Q_hydro_0', 'Initial hydro reactive outputs', [i_hydro], list(Q_AC_hydro.values()))
    addGamsParams(db_prePSCAC, 'Q_syncon_0', 'Initial syncon reactive outputs', [i_syncon], list(Q_AC_syncon.values()))
    addGamsParams(db_prePSCAC, 'Q_pv_0', 'Initial pv reactive outputs', [i_pv], list(Q_AC_pv.values()))
    addGamsParams(db_prePSCAC, 'Q_wind_0', 'Initial wind reactive outputs', [i_wind], list(Q_AC_wind.values()))
    addGamsParams(db_prePSCAC, 'Q_thermal_ck_0', 'thermal reactive outputs after contingency i', [i_thermal, i_contingency], Q_thermal_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'Q_hydro_ck_0', 'hydro reactive outputs after contingency i', [i_hydro, i_contingency], Q_hydro_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'Q_syncon_ck_0', 'syncon reactive outputs after contingency i', [i_syncon, i_contingency], Q_syncon_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'Q_pv_ck_0', 'pv reactive outputs after contingency i', [i_pv, i_contingency], Q_pv_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'Q_wind_ck_0', 'wind reactive outputs after contingency i', [i_wind, i_contingency], Q_wind_cont[:, critical_contingencies])

    addGamsParams(db_prePSCAC, 'P_thermal_dc', 'thermal output in DC solution (used as reference)', [i_thermal], list(P_DC_thermal.values()))
    addGamsParams(db_prePSCAC, 'P_hydro_dc', 'hydro output in DC solution (used as reference)', [i_hydro], list(P_DC_hydro.values()))
    addGamsParams(db_prePSCAC, 'P_pv_dc', 'pv output in DC solution (used as reference)', [i_pv], list(P_DC_pv.values()))
    addGamsParams(db_prePSCAC, 'P_wind_dc', 'wind output in DC solution (used as reference)', [i_wind], list(P_DC_wind.values()))

    addGamsParams(db_prePSCAC, 'V_0', 'Initial voltages', [i_bus], list(V_AC.values()))
    addGamsParams(db_prePSCAC, 'theta_0', 'Initial angles', [i_bus], list(theta_AC.values()))
    addGamsParams(db_prePSCAC, 'V_ck_0', 'Voltages after contingency i', [i_bus, i_contingency], V_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'theta_ck_0', 'Angles after contingency i', [i_bus, i_contingency], theta_cont[:, critical_contingencies])

    addGamsParams(db_prePSCAC, 'P1_0', 'Initial active flows (from-to)', [i_branch], P1)
    addGamsParams(db_prePSCAC, 'Q1_0', 'Initial reactive flows (from-to)', [i_branch], Q1)
    addGamsParams(db_prePSCAC, 'P2_0', 'Initial active flows (to-from)', [i_branch], P2)
    addGamsParams(db_prePSCAC, 'Q2_0', 'Initial reactive flows (to-from)', [i_branch], Q2)

    addGamsParams(db_prePSCAC, 'P1_ck_0', 'Active flows (from-to) after contingency', [i_branch, i_contingency], P1_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'Q1_ck_0', 'Reactive flows (from-to) after contingency', [i_branch, i_contingency], Q1_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'P2_ck_0', 'Active flows (to-from) after contingency', [i_branch, i_contingency], P2_cont[:, critical_contingencies])
    addGamsParams(db_prePSCAC, 'Q2_ck_0', 'Reactive flows (to-from) after contingency', [i_branch, i_contingency], Q2_cont[:, critical_contingencies])

    db_prePSCAC.export('PrePSCACOPF.gdx')
    t = ws.add_job_from_file(os.path.join(os.getcwd(), 'c-PSCACOPF', 'PSCACOPF.gms'))
    print('Launching GAMS')
    t.run()

    db_postPSCAC = ws.add_database_from_gdx("PostPSCACOPF.gdx")

    solve_status = int(db_postPSCAC["sol"].first_record().value)
    if solve_status != 1 and solve_status != 2 and solve_status != 7:
        raise RuntimeError('PSCACOPF: no solution found, error code:', solve_status)

    P_AC_thermal = {rec.keys[0]:rec.level for rec in db_postPSCAC["P_thermal"]}
    P_AC_hydro = {rec.keys[0]:rec.level for rec in db_postPSCAC["P_hydro"]}
    P_AC_pv = {rec.keys[0]:rec.level for rec in db_postPSCAC["P_pv"]}
    P_AC_wind = {rec.keys[0]:rec.level for rec in db_postPSCAC["P_wind"]}

    Q_AC_thermal = {rec.keys[0]:rec.level for rec in db_postPSCAC["Q_thermal"]}
    Q_AC_hydro = {rec.keys[0]:rec.level for rec in db_postPSCAC["Q_hydro"]}
    Q_AC_syncon = {rec.keys[0]:rec.level for rec in db_postPSCAC["Q_syncon"]}
    Q_AC_pv = {rec.keys[0]:rec.level for rec in db_postPSCAC["Q_pv"]}
    Q_AC_wind = {rec.keys[0]:rec.level for rec in db_postPSCAC["Q_wind"]}

    V_AC = {rec.keys[0]:rec.level for rec in db_postPSCAC["V"]}
    theta_AC = {rec.keys[0]:rec.level for rec in db_postPSCAC["theta"]}

    deviation = db_postPSCAC["deviation"].first_record().level

    print('Demand + estimated losses', sum(demand_bus) * (1 + losses))
    print('Total generation',
        sum(P_AC_thermal.values()) +
        sum(P_AC_hydro.values()) +
        sum(P_AC_pv.values()) +
        sum(P_AC_wind.values()) +
        sum(rtpv_max))

    print('Deviation:', round(deviation, 2))

    """ for rec in db_postPSCAC["err_P_pos"]:
        if rec.level > 1e-4:
            raise RuntimeError('Slack variable', rec.keys, 'is not zero')
    for rec in db_postPSCAC["err_Q_pos"]:
        if rec.level > 1e-4:
            raise RuntimeError('Slack variable', rec.keys, 'is not zero')
    for rec in db_postPSCAC["err_P_neg"]:
        if rec.level > 1e-4:
            raise RuntimeError('Slack variable', rec.keys, 'is not zero')
    for rec in db_postPSCAC["err_Q_neg"]:
        if rec.level > 1e-4:
            raise RuntimeError('Slack variable', rec.keys, 'is not zero') """

    # Send dispatch to Powsybl
    opf_results_to_powsybl(network, thermal_gens, thermal_connected, P_AC_thermal, Q_AC_thermal,
                           hydro_gens, P_AC_hydro, Q_AC_hydro, hydro_max,
                           wind_gens, P_AC_wind, Q_AC_wind, wind_max,
                           pv_gens, P_AC_pv, Q_AC_pv, pv_max,
                           rtpv_gens, rtpv_max,
                           syncon_gens, Q_AC_syncon,
                           buses, demand_bus, demand_bus_Q,
                           gens, V_AC)
# end while


sol = pp.loadflow.run_ac(network)[0]

if sol.distributed_active_power > 100 or sol.slack_bus_active_power_mismatch > 100:
    raise RuntimeError('Mismatch between OPF and Powsybl')

# Balance reactive power production in buses with multiple generator (Powsybl puts same power everywhere, use pro rata capacity instead)
bus_results = network.get_buses()
gen_results = network.get_generators()
connected_gen_results = gen_results.loc[gen_results['connected'] == True]
for bus_id in bus_results.index:
    gen_ids = []
    for gen_id in connected_gen_results.index:
        if connected_gen_results.loc[gen_id, 'bus_id'] == bus_id:
            gen_ids.append(gen_id)
    total_max_q = 0
    total_min_q = 0
    total_q = 0
    for gen_id in gen_ids:
        total_max_q += connected_gen_results.loc[gen_id, 'max_q']
        total_min_q += connected_gen_results.loc[gen_id, 'min_q']
        total_q += -connected_gen_results.loc[gen_id, 'q']
    if total_min_q == total_max_q:
        ratio = 0
    else:
        ratio = (total_q - total_min_q) / (total_max_q - total_min_q)
    for gen_id in gen_ids:
        Q = connected_gen_results.loc[gen_id, 'min_q'] + ratio * (connected_gen_results.loc[gen_id, 'max_q'] - connected_gen_results.loc[gen_id, 'min_q'])
        if abs(Q) < 1e-4:
            Q = 0  # Helps with initialisation of dynamic simulations (avoids div by almost 0)
        network.update_generators(id=gen_id, q=Q, target_q=Q)
        if abs(float(connected_gen_results.loc[gen_id, 'max_p'])) < 1e-3 and Q == 0:
            network.update_generators(id=gen_id, connected=False)

# Write final dispatch
output_path = os.path.join('d-Final-dispatch', f'{case}_{network_name}')
Path(output_path).mkdir(parents=True, exist_ok=True)

output_name = os.path.join(output_path, str(hour) + '.iidm')
network.dump(output_name, 'XIIDM', {'iidm.export.xml.version' : '1.4'})
[file, ext] = output_name.rsplit('.', 1)  # Set extension to iidm instead of xiidm
if ext != 'xiidm':
    os.rename(file + '.xiidm', output_name)

print('\nPSCACOPF for hour:', hour, 'successfully run')
