import csv
import os
import numpy as np
import datetime

baseMVA = 100
hour = 0
case = 'year'

"""
Simple script used to find the index of elements with a given name in the arrays sent to GAMS.
Used to manually define the support-vector machine constraints defined in the security enhancement step.
"""

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


data_dir = '../../RTS-Data'

buses = csvToDict('bus.csv', data_dir)
branches = csvToDict('branch.csv', data_dir)
gens = csvToDict('gen.csv', data_dir)

N_buses = len(buses['Bus ID'])
N_branches = len(branches['UID'])
N_gens = len(gens['GEN UID'])

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


print(branches['UID'].index('A34') + 1)
print(wind_gens['GEN UID'].index('122_WIND_1') + 1)
print(branches['UID'].index('B21') + 1)
print(thermal_gens['GEN UID'].index('321_CC_1') + 1)
print(branches['UID'].index('A28') + 1)
print(thermal_gens['GEN UID'].index('115_STEAM_3') + 1)
print(branches['UID'].index('B12-1') + 1)
print(branches['UID'].index('B13-2') + 1)
print(branches['UID'].index('A30') + 1)
print(branches['UID'].index('B21') + 1)
print(thermal_gens['GEN UID'].index('101_STEAM_3') + 1)
print(branches['UID'].index('A6') + 1)