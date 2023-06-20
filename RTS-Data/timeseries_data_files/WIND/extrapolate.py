import csv

# Wind forecast errors are too large (https://github.com/GridMod/RTS-GMLC/issues/114), so use the day ahead ones instead

csv_in = open('DAY_AHEAD_wind.csv', 'r')
csv_out = open('REAL_TIME_wind.csv', 'w')

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
