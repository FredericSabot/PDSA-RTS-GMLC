from lxml import etree

"""
Based on the results of the PDSA (../AnalysisOutput.xml), this scripts shows that many scenarios
for a given contingency have the same starting tripping sequence.
"""


XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
file = '../AnalysisOutput.xml'
root = etree.parse(file, XMLparser).getroot()

for contingency in sorted(root, key = lambda item:item.get('cost'), reverse=True):
    break  # Only look at the most critical contingency

trip_sets = {}

for static_id in contingency:
    if static_id.tag != 'Static_Id':
        continue
    trip_0 = static_id.get('trip_0')
    trip_1 = static_id.get('trip_1')
    trip_2 = static_id.get('trip_2')
    if trip_0 is None or 'RTPV' in trip_0:
        trip_0 = ''
    if trip_1 is None or 'RTPV' in trip_1:
        trip_1 = ''
    if trip_2 is None or 'RTPV' in trip_2:
        trip_2 = ''

    trips = [trip_0, trip_1, trip_2]
    while '' in trips:
        trips.remove('')
    if '121_NUCLEAR_1_UVA' in trips and '121_NUCLEAR_1_InternalAngle' in trips:
        trips.remove('121_NUCLEAR_1_UVA')
    if len(trips) > 2:
        del([trips[-1]])
    trips = frozenset(trips)
    # trips = tuple(trips)

    if trips in trip_sets:
        trip_sets[trips] += 1
    else:
        trip_sets[trips] = 1

for trips, number_occurences in sorted(trip_sets.items(), key=lambda x: x[1], reverse=True):
    print(number_occurences / len(contingency) * 100, trips)