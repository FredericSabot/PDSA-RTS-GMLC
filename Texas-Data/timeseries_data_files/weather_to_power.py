import csv
import numpy as np
import glob
from pathlib import Path


def wind_power_factor(wind_speed):
    # Wind power curve of Siemens SWT-2.3-113 from https://en.wind-turbine-models.com/powercurves. Model seems reasonably common and similar to others based on https://en.wikipedia.org/wiki/Wind_power_in_Texas
    wind_speeds = [3, 4, 5, 11, 12, 20]
    wind_powers = [66, 171, 352, 2296, 2300, 2300]
    return np.interp(wind_speed, wind_speeds, wind_powers, left=0, right=0) / 2300  # 0 for wind speeds below 3m/s and above 20m/s

def pv_power_factor(GHI):
    return GHI / 1000  # Does not account for impact of temperature (85% efficiency at 65°C compared to standard 25°C https://sustainabletechnologies.ca/app/uploads/2017/10/Irrad-Eff-Tech-Brief_v11.pdf)


weather_data_files = glob.glob('weather_data/*.csv')  # Note: glob returns files in arbitrary order

def find_closest_point(latitude, longitude):
    min = 99999
    index = 0
    for i, weather_data_file in enumerate(weather_data_files):
        lat, lng = map(float, weather_data_file.split('_')[1:3])
        distance = (lat - latitude)**2 + (lng - longitude)**2
        if distance < min:
            min = distance
            index = i

    return weather_data_files[index]

data = {}
data['WIND'] = {}
data['PV'] = {}

with open('../generator_locations.csv') as f:
    reader = csv.reader(f)
    next(reader)

    for gen in reader:
        gen_uid = gen[0]
        gen_Pmax = float(gen[1])
        latitude = float(gen[2])
        longitude = float(gen[3])

        if 'WIND' in gen_uid or 'PV' in gen_uid:
            weather_file = find_closest_point(latitude, longitude)
            powers = []
            with open(weather_file) as data_file:
                data_reader = csv.reader(data_file)
                next(data_reader)
                next(data_reader)
                next(data_reader)  # Skip 3 lines of header
                for row in data_reader:
                    if 'WIND' in gen_uid:
                        wind_speed = float(row[6])
                        powers.append(wind_power_factor(wind_speed) * gen_Pmax)
                    else:
                        GHI = float(row[5])
                        powers.append(pv_power_factor(GHI) * gen_Pmax)

            if 'WIND' in gen_uid:
                data['WIND'][gen_uid] = powers
            else:
                data['PV'][gen_uid] = powers


for gen_type in ['WIND', 'PV']:
    Path(gen_type).mkdir(exist_ok=True)

    for period in ['DAY_AHEAD', 'REAL_TIME']:
        gen_type_lower_case = gen_type.lower()
        with open(f'{gen_type}/{period}_{gen_type}.csv', 'w') as f:
            writer = csv.writer(f)
            header = 'Year,Month,Day,Period'.split(',')
            header += list(data[gen_type].keys())
            writer.writerow(header)

            time_axis_file = open(weather_data_files[0])  # All files are assumed to have the same time axis
            time_reader = csv.reader(time_axis_file)

            next(time_reader); next(time_reader); next(time_reader)
            for t, time in enumerate(time_reader):
                row = time[:4]  # Year, month, day, hour

                for gen in data[gen_type]:
                    row.append(data[gen_type][gen][t])
                writer.writerow(row)
