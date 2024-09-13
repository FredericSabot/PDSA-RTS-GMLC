import pypowsybl as pp
import os
import csv

"""
Generate a csv with the total power generation for each generation category (wind, nuclear, etc.) for a given day.
Used to generate stackplots in LaTeX/Tikz.
"""

network_name = 'Texas'

def csvToDict(csv_file, dir='.'):
    with open(os.path.join(dir, csv_file), 'r') as file:
        reader = csv.reader(file)
        headers = next(reader)

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

gens_csv = csvToDict('gen.csv', f'../../{network_name}-Data')
keys = gens_csv['GEN UID']
values = gens_csv['Fuel']
gen_fuel_map = dict(zip(keys, values))

hours = list(range(25))

coal_gen = []
hydro_gen = []
gas_gen = []  # NG
nuclear_gen = []
oil_gen = []
solar_gen = []
wind_gen = []


for h in hours:
    h += 182 * 24
    n = pp.network.load(f'../d-Final-dispatch/year_{network_name}/{h}.iidm')
    gens = n.get_generators()

    coal = 0
    hydro = 0
    gas = 0
    nuclear = 0
    oil = 0
    solar = 0
    wind = 0
    for gen_id in gens.index:
        if gens.at[gen_id, 'connected']:
            if gen_fuel_map[gen_id] == 'Coal':
                coal += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'Hydro':
                hydro += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'NG':  # Gas
                gas += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'Nuclear':
                nuclear += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'Oil':
                oil += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'Solar':
                solar += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'PV':
                solar += -gens.at[gen_id, 'p']
            elif gen_fuel_map[gen_id] == 'Wind':
                wind += -gens.at[gen_id, 'p']

    coal_gen.append(coal)
    hydro_gen.append(hydro)
    gas_gen.append(gas)
    nuclear_gen.append(nuclear)
    oil_gen.append(oil)
    solar_gen.append(solar)
    wind_gen.append(wind)


with open('dispatch.txt', 'w') as f:
    f.write('\t'.join(['hour', 'coal', 'hydro', 'gas', 'nuclear', 'oil', 'solar', 'wind']) + '\n')
    for i in range(len(hours)):
        f.write('\t'.join([str(i), str(coal_gen[i]), str(hydro_gen[i]), str(gas_gen[i]), str(nuclear_gen[i]),
                           str(oil_gen[i]), str(solar_gen[i]), str(wind_gen[i])]) + '\n')
