import csv
from pathlib import Path
import shutil


for network_name in ['RTS', 'Texas']:
    Path(f'data-{network_name}').mkdir(exist_ok=True)

    # Reduces the branch ratings in the PRESCIENT model to have margins, to ease differences between DC and AC formulations
    # Replace emergency ratings (used by PRESCIENT for N-1 analysis) by the long term ones
    with open(f'../{network_name}-Data/branch.csv', 'r') as branches:
        with open(f'data-{network_name}/branch.csv', 'w') as new_branches:
            reader = csv.reader(branches)
            writer = csv.writer(new_branches)

            writer.writerow(next(reader))  # Copy headers
            for row in reader:
                cont_rating = round(float(row[6]) * 0.95, 1)  # 5% Margin
                short_rating = round(float(row[7]) * 0.95, 1)
                emergency_rating = short_rating  # PRESCIENT uses emergency ratings for N-1, use short-term instead
                writer.writerow(row[:6] + [cont_rating, short_rating, emergency_rating] + row[9:])

    shutil.copy(f'../{network_name}-Data/bus.csv',                 f'data-{network_name}/')
    shutil.copy(f'../{network_name}-Data/dc_branch.csv',           f'data-{network_name}/')
    shutil.copy(f'../{network_name}-Data/gen.csv',                 f'data-{network_name}/')
    shutil.copy(f'../{network_name}-Data/reserves.csv',            f'data-{network_name}/')
    shutil.copy(f'../{network_name}-Data/simulation_objects.csv',  f'data-{network_name}/')
    shutil.copy(f'../{network_name}-Data/timeseries_pointers.csv', f'data-{network_name}/')

    Path(f'data-{network_name}/timeseries_data_files').mkdir(exist_ok=True)

    if network_name == 'RTS':
        shutil.copytree(f'../{network_name}-Data/timeseries_data_files/HYDRO', f'data-{network_name}/timeseries_data_files/HYDRO', dirs_exist_ok=True)
        shutil.copytree(f'../{network_name}-Data/timeseries_data_files/RTPV',  f'data-{network_name}/timeseries_data_files/RTPV',  dirs_exist_ok=True)
    shutil.copytree(f'../{network_name}-Data/timeseries_data_files/PV',    f'data-{network_name}/timeseries_data_files/PV',    dirs_exist_ok=True)
    shutil.copytree(f'../{network_name}-Data/timeseries_data_files/Load',  f'data-{network_name}/timeseries_data_files/Load',  dirs_exist_ok=True)
    shutil.copytree(f'../{network_name}-Data/timeseries_data_files/WIND',  f'data-{network_name}/timeseries_data_files/WIND',  dirs_exist_ok=True)


    # Add transmission losses to loads to better match AC and DC computations
    losses = 0.04
    for period in ['DAY_AHEAD', 'REAL_TIME']:
        csv_in = open(f'../{network_name}-Data/timeseries_data_files/Load/{period}_regional_Load.csv', 'r')
        csv_out = open(f'data-{network_name}/timeseries_data_files/Load/{period}_regional_Load.csv', 'w')

        reader = csv.reader(csv_in)
        writer = csv.writer(csv_out)

        header = next(reader)
        writer.writerow(header)

        for row in reader:
            year, month, day, period = row[0:4]
            load = [float(j) for j in row[4:]]
            load_with_losses = [float(i) * (1 + losses) for i in load]
            writer.writerow([year, month, day, period] + load_with_losses)

        csv_in.close()
        csv_out.close()
