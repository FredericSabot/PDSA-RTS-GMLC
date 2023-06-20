import csv

# There are issues with the real-time loads (https://github.com/GridMod/RTS-GMLC/issues/129), so use the day ahead ones instead

csv_in = open('DAY_AHEAD_regional_Load.csv', 'r')
csv_out = open('REAL_TIME_regional_load.csv', 'w')

reader = csv.reader(csv_in)
writer = csv.writer(csv_out)

header = True
for row in reader:
    if header:
        writer.writerow(row)
        header = False
        continue
    else:
        for i in range(int(60/5)):
            writer.writerow(row)
