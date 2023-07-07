import csv
import datetime
import os
from pathlib import Path
import sys

case = sys.argv[1]

folder_in = case + '_week_output_N_1'
folder_out = 'PrescientDispatch_' + case
Path(folder_out).mkdir(parents=True, exist_ok=True)

# Check init and end times
gen_names_thermal = []
with open(os.path.join(folder_in, 'thermal_detail.csv'), 'r') as thermal:
    reader = csv.reader(thermal)
    next(reader)  # Skip header
    row = next(reader)
    init_date = datetime.datetime.strptime(row[0], '%Y-%m-%d') + datetime.timedelta(hours = int(row[1]))

    for row in reader:
        pass  # Goto last line of file
    end_date = datetime.datetime.strptime(row[0], '%Y-%m-%d') + datetime.timedelta(hours=int(row[1]))
nb_t = int((end_date - init_date).total_seconds() / 3600) + 1


# Read thermal dispatch
power_thermal = [{} for i in range(nb_t)]
on = [{} for i in range(nb_t)]
with open(os.path.join(folder_in, 'thermal_detail.csv'), 'r') as thermal:
    reader = csv.reader(thermal)
    next(reader)  # Skip header

    for row in reader:
        date = row[0]
        hour = int(row[1])
        name = row[3]
        p = float(row[4])
        state = row[7]
        if state == 'True':
            state = 1
        else:
            state = 0
        
        if 'SYNC_COND' in name:
            continue
        
        date = datetime.datetime.strptime(date, '%Y-%m-%d') + datetime.timedelta(hours = hour)
        hour = int((date - init_date).total_seconds() / 3600)

        power_thermal[hour][name] = p
        on[hour][name] = state

# Read renew dispatch
power_hydro = [{} for i in range(nb_t)]
power_pv = [{} for i in range(nb_t)]
power_wind = [{} for i in range(nb_t)]
with open(os.path.join(folder_in, 'renewables_detail.csv'), 'r') as renew:
    reader = csv.reader(renew)
    next(reader)  # Skip header

    for row in reader:
        date = row[0]
        hour = int(row[1])
        name = row[3]
        p = float(row[4])
        
        date = datetime.datetime.strptime(date, '%Y-%m-%d') + datetime.timedelta(hours = hour)
        hour = int((date - init_date).total_seconds() / 3600)

        if 'RTPV' in name:  # RTPV generators are handled separatelly since their output is fixed
            continue
        elif 'HYDRO' in name:
            power_hydro[hour][name] = p
        elif 'PV' in name:
            power_pv[hour][name] = p
        elif 'WIND' in name:
            power_wind[hour][name] = p
        else:
            raise ValueError('Renewable generator names should contain either RTPV, HYDRO, PV, or WIND, name is', name)


# Write dispatchs
for t in range(nb_t):
    with open(os.path.join(folder_out, 'Thermal-' + str(t) + '.csv'), 'w') as out_file:
        writer = csv.writer(out_file)
        writer.writerow(['GenName', 'Output', 'State'])
        for key in power_thermal[t]:
            writer.writerow([key, power_thermal[t][key], on[t][key]])

for t in range(nb_t):
    with open(os.path.join(folder_out, 'Hydro-' + str(t) + '.csv'), 'w') as out_file:
        writer = csv.writer(out_file)
        writer.writerow(['GenName', 'Output'])
        for key, value in power_hydro[t].items():
            writer.writerow([key, value])

for t in range(nb_t):
    with open(os.path.join(folder_out, 'PV-' + str(t) + '.csv'), 'w') as out_file:
        writer = csv.writer(out_file)
        writer.writerow(['GenName', 'Output'])
        for key, value in power_pv[t].items():
            writer.writerow([key, value])

for t in range(nb_t):
    with open(os.path.join(folder_out, 'Wind-' + str(t) + '.csv'), 'w') as out_file:
        writer = csv.writer(out_file)
        writer.writerow(['GenName', 'Output'])
        for key, value in power_wind[t].items():
            writer.writerow([key, value])
