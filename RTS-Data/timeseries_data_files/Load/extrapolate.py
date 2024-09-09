import csv

# There are issues with the real-time loads (https://github.com/GridMod/RTS-GMLC/issues/129), so use the day ahead ones instead

csv_in = open('DAY_AHEAD_regional_Load.csv', 'r')
csv_out = open('REAL_TIME_regional_Load.csv', 'w')

reader = csv.reader(csv_in)
writer = csv.writer(csv_out)

header = next(reader)
writer.writerow(header)

for row in reader:
    for i in range(int(60/5)):
        year, month, day = row[0:3]
        period = int(row[3])
        load = [float(j) for j in row[4:]]
        writer.writerow([year, month, day, int((period-1)*60/5 + i + 1)] + load)
