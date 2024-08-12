from lxml import etree
import csv

"""
Based on the results of the PDSA (../AnalysisOutput.xml), this scripts counts for each contingency,
what is the share of sampled scenarios that led to green, yellow, orange or red scenarios:
- Green: No load shedding, no security violations (here, counted as no trip of transmission or generation element)
- Yellow: No load shedding, with security violation(s)
- Orange: Load shedding < 20%
- Red: Load shedding > 20%

A high share of yellow scenarios indicates that it is useful to simulate cascading outages instead of
automatically counting scenarios with security violations as unacceptable.
"""

DYNAWO_NAMESPACE = 'http://www.rte-france.com/dynawo'
NETWORK_NAME = 'RTS'

if __name__ == '__main__':
    root = etree.parse('../AnalysisOutput.xml').getroot()
    worst_contingencies = sorted(root, key=lambda x : float(x.get('cost')), reverse=True)

    f = open('contingency_classification.csv', 'w')
    writer = csv.writer(f)

    writer.writerow(['Contingency', 'Frequency', 'Cost', 'Green', 'Yellow', 'Orange', 'Red'])

    for contingency in worst_contingencies:
        green = 0
        yellow = 0
        orange = 0
        red = 0

        N = len(contingency)

        for j, sample in enumerate(contingency):
            trip_0 = sample.get('trip_0')
            trip_1 = sample.get('trip_1')
            trip_2 = sample.get('trip_2')
            if trip_0 is None or 'RTPV' in trip_0:
                trip_0 = ''
            if trip_1 is None or 'RTPV' in trip_1:
                trip_1 = ''
            if trip_2 is None or 'RTPV' in trip_2:
                trip_2 = ''
            load_shedding = float(sample.get('mean_load_shed'))

            if load_shedding > 20:
                red += 1 / N * 100
            elif load_shedding > 0:
                orange += 1 / N * 100
            elif trip_0 != '' or trip_1 != '' or trip_2 != '':
                yellow += 1 / N * 100
            else:
                green += 1 / N * 100

        writer.writerow([contingency.get('id'), contingency.get('frequency'), contingency.get('cost'), green, yellow, orange, red])
