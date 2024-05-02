import numpy as np
import pypowsybl as pp
import os
import csv

case = 'year'

"""
This scripts estimates the operating costs for all disptatches in ../d-Final-dispatch/$case
For the sake of simplicity, the only costs considered are fuel costs of thermal generators
and they are computed as HR_incr_3 (from RTS data) times the power production of the generators,
i.e. the third piece of the piece-wise linear cost function is used regardless of the actual power.
"""

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

thermal_gens = {}
for key in gens.keys():
    thermal_gens[key] = []

for i in range(len(gens)):
    for key in gens.keys():
        if gens['Fuel'][i] == 'Oil' or gens['Fuel'][i] == 'Coal' or gens['Fuel'][i] == 'NG' or gens['Fuel'][i] == 'Nuclear':
            thermal_gens[key].append(gens[key][i])
        else:
            pass  # Only thermal generators have a modelled cost

lincost = np.array(thermal_gens['HR_incr_3']) * 1000 * np.array(thermal_gens['Fuel Price $/MMBTU']) / 1e6

costs = {}
loads = {}
for i in range(8736):
    file = '../d-Final-dispatch/{}/{}.iidm'.format(case, i)
    print('Loading hour {} out of 8736'.format(i), end='\r')
    if not os.path.exists(file):
        costs[i] = ''
        loads[i] = ''
        continue

    n = pp.network.load(file)
    gens = n.get_generators()
    P = []

    for gen_id in thermal_gens['GEN UID']:
        if not gens.at[gen_id, 'connected']:
            P.append(0)
        else:
            P.append(-gens.at[gen_id, 'p'])
    costs[i] = sum(lincost * np.array(P))

    P = []
    for gen_id in gens.index:
        if not gens.at[gen_id, 'connected']:
            P.append(0)
        else:
            P.append(-gens.at[gen_id, 'p'])
    loads[i] = sum(P)

print()

with open('Cost_{}.csv'.format(case), 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['Hour', 'Load', 'Cost'])
    for hour in costs:
        writer.writerow([hour, loads[hour], costs[hour]])
