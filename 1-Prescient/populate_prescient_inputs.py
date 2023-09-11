import csv
from pathlib import Path
import shutil

Path('data').mkdir(exist_ok=True)

# Reduces the branch ratings in the PRESCIENT model to have margins, to ease differences between DC and AC formulations
# Replace emergency ratings (used by PRESCIENT for N-1 analysis) by the long term ones
with open('../RTS-Data/branch.csv', 'r') as branches:
    with open('data/branch.csv', 'w') as new_branches:
        reader = csv.reader(branches)
        writer = csv.writer(new_branches)

        writer.writerow(next(reader))  # Copy headers
        for row in reader:
            cont_rating = round(float(row[6]) * 0.95, 1)  # 5% Margin
            short_rating = round(float(row[7]) * 0.95, 1)
            emergency_rating = short_rating  # PRESCIENT uses emergency ratings for N-1, use short-term instead
            writer.writerow(row[:6] + [cont_rating, short_rating, emergency_rating] + row[9:])

shutil.copy('../RTS-Data/bus.csv', 'data/')
shutil.copy('../RTS-Data/dc_branch.csv', 'data/')
shutil.copy('../RTS-Data/gen.csv', 'data/')
shutil.copy('../RTS-Data/reserves.csv', 'data/')
shutil.copy('../RTS-Data/simulation_objects.csv', 'data/')
shutil.copy('../RTS-Data/timeseries_pointers.csv', 'data/')

Path('data/timeseries_data_files').mkdir(exist_ok=True)

shutil.copytree('../RTS-Data/timeseries_data_files/HYDRO', 'data/timeseries_data_files/HYDRO', dirs_exist_ok=True)
shutil.copytree('../RTS-Data/timeseries_data_files/Load', 'data/timeseries_data_files/Load', dirs_exist_ok=True)
shutil.copytree('../RTS-Data/timeseries_data_files/PV', 'data/timeseries_data_files/PV', dirs_exist_ok=True)
shutil.copytree('../RTS-Data/timeseries_data_files/RTPV', 'data/timeseries_data_files/RTPV', dirs_exist_ok=True)
shutil.copytree('../RTS-Data/timeseries_data_files/WIND', 'data/timeseries_data_files/WIND', dirs_exist_ok=True)


# Add transmission losses to loads to better match AC and DC computations
losses = 0.04

csv_in = open('../RTS-Data/timeseries_data_files/Load/REAL_TIME_regional_load.csv', 'r')
csv_out = open('data/timeseries_data_files/Load/REAL_TIME_regional_load.csv', 'w')

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
