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

baseMVA = 100

# sys.argv = ['PSCACOPF.py', '167', 'january']  # Don't uncomment, copy paste to interpreter if needed (avoid mistakes)
hour = int(sys.argv[1])
case = sys.argv[2]
print('Running PSCACOPF for case', case, 'hour:', hour)

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


data_dir = '../RTS-Data'
timeseries_dir = '../RTS-Data/timeseries_data_files'
prescient_dir = '../1-Prescient/PrescientDispatch' + '_' + case

buses = csvToDict('bus.csv', data_dir)
branches = csvToDict('branch.csv', data_dir)
gens = csvToDict('gen.csv', data_dir)
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
load_per_area = [0] * 3
for i in range(N_buses):
    load_per_area[area[i] - 1] += loads_P[i]
load_participation_area = [[], [], []]
for i in range(N_buses):
    load_participation_area[area[i] -1].append(loads_P[i] / load_per_area[area[i] - 1])


admit = 1 / np.array(branches['X'])
Imax = np.array(branches['Cont Rating']) / baseMVA

branch_map = np.zeros((N_branches, N_buses))

for i in range(N_branches):
    branches['From Bus'][i] = buses['Bus ID'].index(branches['From Bus'][i])
    branches['To Bus'][i] = buses['Bus ID'].index(branches['To Bus'][i])
    branch_map[i, int(branches['From Bus'][i])] = 1
    branch_map[i, int(branches['To Bus'][i])] = -1

for j in range(N_buses):
    if sum([abs(branch_map[i][j]) for i in range(N_branches)]) < 2:
        raise Exception('Bus', buses['Bus ID'][j], 'is only connected to one branch, system thus cannot be N-1 secure')


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
        elif gens['Category'][i] == 'Solar PV':
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
            min5 = int(row[3]) - 1
            date = datetime.datetime(year, month, day) + datetime.timedelta(minutes = min5*5)
            if init_date + datetime.timedelta(hours = hour) == date:
                data = []
                for value in row[4:]:
                    data.append(float(value))
                return data
    raise Exception('Hour', hour, 'not found in timeseries')

hydro_max = np.array(extractRealTimeData(hour, 'HYDRO', 'hydro')) / baseMVA
pv_max = np.array(extractRealTimeData(hour, 'PV', 'pv')) / baseMVA
wind_max = np.array(extractRealTimeData(hour, 'WIND', 'wind')) / baseMVA
rtpv_max = np.array(extractRealTimeData(hour, 'RTPV', 'rtpv')) / baseMVA

losses = 0.04
demand_area = np.array(extractRealTimeData(hour, 'Load', 'regional_load')) / baseMVA
demand_bus = []
for i in range(3):
    demand_bus.append(demand_area[i] * np.array(load_participation_area[i]))
demand_bus = np.concatenate((demand_bus[0], demand_bus[1], demand_bus[2]))


# DCOPF: Send data to GAMS
print('\nPSCDCOPF')
dcopf_path = os.path.join('a-PSCDCOPF', str(hour))
Path(dcopf_path).mkdir(parents=True, exist_ok=True)
ws = gams.GamsWorkspace(working_directory=os.path.join(os.getcwd(), dcopf_path), debug=gams.DebugLevel.Off)
db_preDC = ws.add_database()

def addGamsSet(db, name, description, lst):
    # Adds a 1-dimensional set
    set = db.add_set(name, 1, description)
    for i in lst:
        set.add_record(str(i))
    return set

i_thermal = addGamsSet(db_preDC, 'i_thermal', 'thermal generators', range(1, N_thermal_gens + 1))
i_hydro = addGamsSet(db_preDC, 'i_hydro', 'hydro generators', range(1, N_hydro_gens + 1))
i_pv = addGamsSet(db_preDC, 'i_pv', 'pv generators', range(1, N_pv_gens + 1))
i_wind = addGamsSet(db_preDC, 'i_wind', 'wind generators', range(1, N_wind_gens + 1))
i_rtpv = addGamsSet(db_preDC, 'i_rtpv', 'rtpv generators', range(1, N_rtpv_gens + 1))
i_syncon = addGamsSet(db_preDC, 'i_syncon', 'syncon generators', range(1, N_syncon_gens + 1))
i_bus = addGamsSet(db_preDC, 'i_bus', 'buses', range(1, N_buses + 1))
i_branch = addGamsSet(db_preDC, 'i_branch', 'branches', range(1, N_branches + 1))

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
                m.add_record((str(i+1),str(j+1))).value = values[i][j]

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

addGamsParams(db_preDC, 'branch_admittance', 'branch admittance', [i_branch], 1 / np.array(branches['X']))
addGamsParams(db_preDC, 'branch_max_N', 'Normal branch max power', [i_branch], np.array(branches['Cont Rating']) / baseMVA)
addGamsParams(db_preDC, 'branch_max_E', 'Emergency branch max power', [i_branch], np.array(branches['LTE Rating']) / baseMVA)

contingency_states = np.ones((N_branches, N_branches)) - np.diag(np.diag(np.ones((N_branches, N_branches))))  # Matrix full of ones, but zeroes on the diagonal
addGamsParams(db_preDC, 'contingency_states', 'Line states in the considered contingencies', [i_branch, i_branch], contingency_states)

addGamsParams(db_preDC, 'demand', 'demand at each bus', [i_bus], demand_bus * (1 + losses))

lincost = np.array(thermal_gens['HR_incr_3']) * 1000 * np.array(thermal_gens['Fuel Price $/MMBTU']) / 1e6
addGamsParams(db_preDC, 'lincost', 'linear cost', [i_thermal], lincost)

addGamsParams(db_preDC, 'P_thermal_0', 'Initial thermal outputs', [i_thermal], np.array(prescient_thermal_dispatch['Output']) / baseMVA)
addGamsParams(db_preDC, 'P_hydro_0', 'Initial hydro outputs', [i_hydro], np.array(prescient_hydro_dispatch['Output']) / baseMVA)
addGamsParams(db_preDC, 'P_pv_0', 'Initial pv outputs', [i_pv], np.array(prescient_pv_dispatch['Output']) / baseMVA)
addGamsParams(db_preDC, 'P_wind_0', 'Initial wind outputs', [i_wind], np.array(prescient_wind_dispatch['Output']) / baseMVA)

prescient_thermal_dispatch['State'] = [int(i) for i in prescient_thermal_dispatch['State']]
addGamsParams(db_preDC, 'on_0', 'Initial commitment status of thermal generators', [i_thermal], prescient_thermal_dispatch['State'])

db_preDC.export('PrePSCDCOPF.gdx')
t = ws.add_job_from_file('../PSCDCOPF.gms')
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
on_DC = {rec.keys[0]:rec.level for rec in db_postDC["on"]}

cost = db_postDC["total_cost"].first_record().level
deviation = db_postDC["deviation"].first_record().level

for key in P_DC_thermal:
    P_DC_thermal[key] = round(P_DC_thermal[key], 4)

print('Demand + estimated losses', sum(demand_bus) * (1 + losses))
print('Total generation',
      sum(np.array(prescient_thermal_dispatch['Output']) / baseMVA) +
      sum(np.array(prescient_hydro_dispatch['Output']) / baseMVA) +
      sum(np.array(prescient_pv_dispatch['Output']) / baseMVA) +
      sum(np.array(prescient_wind_dispatch['Output']) / baseMVA) +
      sum(rtpv_max))

print('Deviation:', round(deviation, 2))


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
    else:  # Transformer (no phase shift in RTS data)
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

acopf_path = os.path.join('b-ACOPF', str(hour))
Path(acopf_path).mkdir(parents=True, exist_ok=True)
ws = gams.GamsWorkspace(working_directory=os.path.join(os.getcwd(), acopf_path), debug=gams.DebugLevel.Off)
db_preAC = ws.add_database()

i_thermal = addGamsSet(db_preAC, 'i_thermal', 'thermal generators', range(1, N_thermal_gens + 1))
i_hydro = addGamsSet(db_preAC, 'i_hydro', 'hydro generators', range(1, N_hydro_gens + 1))
i_pv = addGamsSet(db_preAC, 'i_pv', 'pv generators', range(1, N_pv_gens + 1))
i_wind = addGamsSet(db_preAC, 'i_wind', 'wind generators', range(1, N_wind_gens + 1))
i_rtpv = addGamsSet(db_preAC, 'i_rtpv', 'rtpv generators', range(1, N_rtpv_gens + 1))
i_syncon = addGamsSet(db_preAC, 'i_syncon', 'syncon generators', range(1, N_syncon_gens + 1))
i_bus = addGamsSet(db_preAC, 'i_bus', 'buses', range(1, N_buses + 1))
i_branch = addGamsSet(db_preAC, 'i_branch', 'branches', range(1, N_branches + 1))

addGamsParams(db_preAC, 'thermal_map', 'thermal generators map', [i_thermal, i_bus], thermal_gen_map)
addGamsParams(db_preAC, 'hydro_map', 'hydro generators map', [i_hydro, i_bus], hydro_gen_map)
addGamsParams(db_preAC, 'pv_map', 'pv generators map', [i_pv, i_bus], pv_gen_map)
addGamsParams(db_preAC, 'wind_map', 'wind generators map', [i_wind, i_bus], wind_gen_map)
addGamsParams(db_preAC, 'rtpv_map', 'rtpv generators map', [i_rtpv, i_bus], rtpv_gen_map)
addGamsParams(db_preAC, 'syncon_map', 'syncon generators map', [i_syncon, i_bus], syncon_gen_map)
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
addGamsParams(db_preAC, 'branch_max_N', 'Normal branch max power', [i_branch], np.array(branches['Cont Rating']) / baseMVA)

addGamsParams(db_preAC, 'demand', 'demand at each bus', [i_bus], demand_bus)
demand_bus_Q = np.zeros(N_buses)
for i in range(N_buses):
    if loads_P[i] != 0:
        demand_bus_Q[i] = loads_Q[i]/loads_P[i] * demand_bus[i] - buses['MVAR Shunt B'][i] / baseMVA
    # else = 0
addGamsParams(db_preAC, 'demandQ', 'reactive demand at each bus', [i_bus], demand_bus_Q)

addGamsParams(db_preAC, 'P_thermal_0', 'Initial thermal outputs', [i_thermal], list(P_DC_thermal.values()))
addGamsParams(db_preAC, 'P_hydro_0', 'Initial hydro outputs', [i_hydro], list(P_DC_hydro.values()))
addGamsParams(db_preAC, 'P_pv_0', 'Initial pv outputs', [i_pv], list(P_DC_pv.values()))
addGamsParams(db_preAC, 'P_wind_0', 'Initial wind outputs', [i_wind], list(P_DC_wind.values()))
addGamsParams(db_preAC, 'Ppf_0', 'Initial line active power flows', [i_branch], list(P_DC_pf.values()))

db_preAC.export('PreACOPF.gdx')
t = ws.add_job_from_file('../ACOPF.gms')
t.run()

db_postAC = ws.add_database_from_gdx("PostACOPF.gdx")

solve_status = int(db_postAC["sol"].first_record().value)
if solve_status != 1 and solve_status != 2 and solve_status != 7:
    raise RuntimeError('ACOPF: no solution found, error code:', solve_status)

P_AC_thermal = {rec.keys[0]:rec.level for rec in db_postAC["P_thermal"]}
P_AC_hydro = {rec.keys[0]:rec.level for rec in db_postAC["P_hydro"]}
P_AC_pv = {rec.keys[0]:rec.level for rec in db_postAC["P_pv"]}
P_AC_wind = {rec.keys[0]:rec.level for rec in db_postAC["P_wind"]}

Q_AC_thermal = {rec.keys[0]:rec.level for rec in db_postAC["Q_thermal"]}
Q_AC_hydro = {rec.keys[0]:rec.level for rec in db_postAC["Q_hydro"]}
Q_AC_syncon = {rec.keys[0]:rec.level for rec in db_postAC["Q_syncon"]}
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

network = pp.network.load('../RTS-Data/RTS.iidm')

connected = [True if on == 1 else False for on in on_DC.values()]
network.update_generators(id=thermal_gens['GEN UID'], connected=connected,
                          target_p=np.array(list(P_AC_thermal.values())) * baseMVA,
                          target_q=np.array(list(Q_AC_thermal.values())) * baseMVA)
network.update_generators(id=hydro_gens['GEN UID'],
                          target_p=np.array(list(P_AC_hydro.values())) * baseMVA,
                          target_q=np.array(list(Q_AC_hydro.values())) * baseMVA,
                          max_p=hydro_max * baseMVA)
network.update_generators(id=wind_gens['GEN UID'],
                          target_p=np.array(list(P_AC_wind.values())) * baseMVA,
                          target_q=np.array(list(Q_AC_wind.values())) * baseMVA,
                          max_p=wind_max * baseMVA)
network.update_generators(id=pv_gens['GEN UID'],
                          target_p=np.array(list(P_AC_pv.values())) * baseMVA,
                          target_q=np.array(list(Q_AC_pv.values())) * baseMVA,
                          max_p=pv_max * baseMVA,
                          voltage_regulator_on=[True] * N_pv_gens)
network.update_generators(id=rtpv_gens['GEN UID'],
                          target_p=rtpv_max * baseMVA,
                          max_p=rtpv_max * baseMVA,
                          voltage_regulator_on=[False] * N_rtpv_gens)
network.update_generators(id=syncon_gens['GEN UID'], target_q=np.array(list(Q_AC_syncon.values())) * baseMVA)

# Disconnect PV generators at night
for i in range(N_pv_gens):
    network.update_generators(id=pv_gens['GEN UID'][i], connected = pv_max[i] > 0)
for i in range(N_rtpv_gens):
    network.update_generators(id=rtpv_gens['GEN UID'][i], connected = rtpv_max[i] > 0)

load_ids = ['L-'+str(int(buses['Bus ID'][i])) for i in range(N_buses)]
network.update_loads(id=load_ids, p0=demand_bus * baseMVA, q0=demand_bus_Q * baseMVA)

critical_contingencies = []  # Contingencies that lead to issues and have to be included in the PSCACOPF (iteratively added to the problem)
while True:
    for i in range(N_gens):
        bus_id = gens['Bus ID'][i]
        index = buses['Bus ID'].index(bus_id)
        V = list(V_AC.values())[index] * buses['BaseKV'][index]
        network.update_generators(id=gens['GEN UID'][i], target_v=V)

    print(pp.loadflow.run_ac(network))
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
    for j in range(N_branches):
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
            P1_cont[i][i] = 0  # No flow in disconnected line (Powsybl returns NaN)
            Q1_cont[i][i] = 0
            P2_cont[i][i] = 0
            Q2_cont[i][i] = 0

        gen_results = network.get_generators()
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

    # Replace NaN's with zeroes for disconnected elements
    np.nan_to_num(Q_thermal_cont, copy=False)
    np.nan_to_num(Q_hydro_cont, copy=False)
    np.nan_to_num(Q_syncon_cont, copy=False)
    np.nan_to_num(Q_pv_cont, copy=False)
    np.nan_to_num(Q_wind_cont, copy=False)

    # Check contingencies that lead to issues with the current dispatch
    for j in range(N_branches):
        for i in range(N_branches):
            if (P1_cont[i][j]**2 + Q1_cont[i][j]**2)**0.5 > 1.05 * branches['LTE Rating'][i] / baseMVA:
                if j not in current_critical_contingencies:
                    current_critical_contingencies.append(j)
                    print('Critical contingency', branches['UID'][j], ': high current in branch', branches['UID'][i], ':', (P1_cont[i][j]**2 + Q1_cont[i][j]**2)**0.5 * baseMVA,  '>', branches['LTE Rating'][i])
        for i in range(N_buses):
            if V_cont[i,j] < 0.8499:
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

    pscacopf_path = os.path.join('c-PSCACOPF', str(hour))
    Path(pscacopf_path).mkdir(parents=True, exist_ok=True)
    ws = gams.GamsWorkspace(working_directory=os.path.join(os.getcwd(), pscacopf_path), debug=gams.DebugLevel.Off)
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
    addGamsParams(db_prePSCAC, 'branch_max_N', 'Normal branch max power', [i_branch], np.array(branches['Cont Rating']) / baseMVA)
    addGamsParams(db_prePSCAC, 'branch_max_E', 'Emergency branch max power', [i_branch], np.array(branches['LTE Rating']) / baseMVA)

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
    t = ws.add_job_from_file('../PSCACOPF.gms')
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
        sum(np.array(prescient_thermal_dispatch['Output']) / baseMVA) +
        sum(np.array(prescient_hydro_dispatch['Output']) / baseMVA) +
        sum(np.array(prescient_pv_dispatch['Output']) / baseMVA) +
        sum(np.array(prescient_wind_dispatch['Output']) / baseMVA) +
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
    network.update_generators(id=thermal_gens['GEN UID'],
                              target_p=np.array(list(P_AC_thermal.values())) * baseMVA,
                              target_q=np.array(list(Q_AC_thermal.values())) * baseMVA)
    network.update_generators(id=hydro_gens['GEN UID'],
                              target_p=np.array(list(P_AC_hydro.values())) * baseMVA,
                              target_q=np.array(list(Q_AC_hydro.values())) * baseMVA)
    network.update_generators(id=wind_gens['GEN UID'],
                              target_p=np.array(list(P_AC_wind.values())) * baseMVA,
                              target_q=np.array(list(Q_AC_wind.values())) * baseMVA)
    network.update_generators(id=pv_gens['GEN UID'],
                              target_p=np.array(list(P_AC_pv.values())) * baseMVA,
                              target_q=np.array(list(Q_AC_pv.values())) * baseMVA)
    network.update_generators(id=syncon_gens['GEN UID'], target_q=np.array(list(Q_AC_syncon.values())) * baseMVA)

    for i in range(N_gens):
        bus_id = gens['Bus ID'][i]
        index = buses['Bus ID'].index(bus_id)
        V = list(V_AC.values())[index] * buses['BaseKV'][index]
        network.update_generators(id=gens['GEN UID'][i], target_v=V)
# end while

# Check if the PSCACOPF solution satisfy all criteria (N-1 cases)
for j in range(N_branches):
    # Disconnect line (or transformer)
    if branches['Tr Ratio'][j] == 0:
        network.update_lines(id=branches['UID'][j], connected1=False, connected2=False)
    else:
        network.update_2_windings_transformers(id=branches['UID'][j], connected1=False, connected2=False)

    sol = pp.loadflow.run_ac(network)
    if str(sol[0].status) == 'ComponentStatus.MAX_ITERATION_REACHED':
        raise RuntimeError('Post PSCACOPF: load flow did not converge for contingency of line', branches['UID'][j])

    # Reconnect line
    if branches['Tr Ratio'][j] == 0:
        network.update_lines(id=branches['UID'][j], connected1=True, connected2=True)
    else:
        network.update_2_windings_transformers(id=branches['UID'][j], connected1=True, connected2=True)

    line_results = network.get_lines()
    transformer_results = network.get_2_windings_transformers()
    for i in range(N_branches):
        if i == j:
            continue
        UID = branches['UID'][i]
        if branches['Tr Ratio'][i] == 0:
            if (line_results['p1'][UID]**2 + line_results['q1'][UID]**2)**0.5 > 1.05 * branches['LTE Rating'][i]:
                raise RuntimeError('Overcurrent in branch', UID, 'following contingency of branch',
                                   branches['UID'][j], (line_results['p1'][UID]**2 + line_results['q1'][UID]**2)**0.5, '>', 1.05 * branches['LTE Rating'][i])
        else:
            if (transformer_results['p1'][UID]**2 + transformer_results['q1'][UID]**2)**0.5 > 1.05 * branches['LTE Rating'][i]:
                raise RuntimeError('Overcurrent in branch', UID)

    V = []
    bus_results = network.get_buses()
    vl_results = network.get_voltage_levels()
    for i in range(N_buses):
        id = int(buses['Bus ID'][i])
        bus_id = 'V-' + str(id) + '_0'  # Powsybl renames buses for fun
        vl_id = 'V-' + str(id)
        V.append(bus_results.loc[bus_id, 'v_mag'] / vl_results.loc[vl_id, 'nominal_v'])
    V_cont[:,j] = np.array(V)
    for i in range(N_buses):
        if V_cont[i,j] < 0.8:
            raise RuntimeError('Error: low voltage:', V_cont[i,j], 'at bus', int(buses['Bus ID'][i]), 'for contingency of line', branches['UID'][j])

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
        continue
    ratio = (total_q - total_min_q) / (total_max_q - total_min_q)
    for gen_id in gen_ids:
        Q = connected_gen_results.loc[gen_id, 'min_q'] + ratio * (connected_gen_results.loc[gen_id, 'max_q'] - connected_gen_results.loc[gen_id, 'min_q'])
        network.update_generators(id=gen_id, target_q=Q)

# Write final dispatch
output_path = os.path.join('d-Final-dispatch', case)
Path(output_path).mkdir(parents=True, exist_ok=True)

output_name = os.path.join(output_path, str(hour) + '.iidm')
network.dump(output_name, 'XIIDM', {'iidm.export.xml.version' : '1.4'})
[file, ext] = output_name.rsplit('.', 1)  # Set extension to iidm instead of xiidm
if ext != 'xiidm':
    os.rename(file + '.xiidm', output_name)

print('\nPSCACOPF for hour:', hour, 'successfully run')
