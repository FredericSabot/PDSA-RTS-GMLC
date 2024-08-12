from lxml import etree
import pypowsybl as pp
import numpy as np

"""
This scripts computes various statistics based on the results of the PDSA (../AnalysisOutput.xml) such
as false/true positives/negatives rates of the screening process (assuming all scenarios were actually
simulated, otherwise the false positives rate will be estimated as 0), computation time and number of
simulations per contingency type, etc.
"""

# TODO: clean up this mess

n = pp.network.load('../../RTS-Data/RTS.iidm')
lines = n.get_lines()
buses = n.get_buses()
gens = n.get_generators()
false_negatives_list = []
false_positives_list = []

wind_lines = []

for line_id in lines.index:
    has_wind = False
    bus1_id = lines.at[line_id, 'bus1_id']
    bus2_id = lines.at[line_id, 'bus2_id']
    for bus_id in [bus1_id, bus2_id]:
        for gen_id in gens.index:
            if gens.at[gen_id, 'bus_id'] != bus_id:
                continue
            if gens.at[gen_id, 'energy_source'] == 'WIND':
                has_wind = True
                break

        if has_wind:
            wind_lines.append(line_id)
            break

def positive(static_id, contingency_id):
    found = False
    for line in wind_lines:
        if line in contingency_id:
            found = True
            break
    if found:
        pass# return True

    contingency_type = get_contingency_type(contingency_id)
    if contingency_type == 0:
        CCT_threshold = 0.25
    else:
        CCT_threshold = 0.25

    transient_unstable = False
    if float(static_id.get('CCT')) < CCT_threshold:
        transient_unstable = True

    frequency_unstable = False
    if float(static_id.get('dP_over_reserves')) > 0.7 or float(static_id.get('RoCoF')) > 0.4:
        frequency_unstable = True
    return transient_unstable or static_id.get('voltage_stable') == 'False' or frequency_unstable#(static_id.get('frequency_stable') == 'False' and close_frequency)


XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
file = '../AnalysisOutput.xml'
root = etree.parse(file, XMLparser).getroot()

total_computation_time = [0, 0, 0]
total_risk = [0, 0, 0]
total_cost = [0, 0, 0]
ind_1 = [0, 0, 0]
ind_2 = [0, 0, 0]

total_total_computation_time = 0
total_computation_time_no_consequences = 0
total_cases = 0
total_cases_no_consequences = 0

# N-1 delayed
# 0.7463191996236379
# 0 (one case, trip of PV on opposite side of line)
# Not clear (probably more trips than expected)
# Same

false_positives = 0
false_negatives = 0
true_positives = 0
true_negatives = 0
false_negatives_per_contingency = {}
false_negatives_max_consequences_per_contingency = {}
positives_per_contingency = {}

total_risk_true = 0
total_risk_screening = 0
total_computation_time_true = 0
total_computation_time_screening = 0

total_protection_cases = 0
total_protection_cases_with_consequences = 0
total_protection_cases_with_consequences_protection_impact = 0
total_protection_cases_with_consequences_cascading_path = 0

share_protection_failure_potential = {contingency.get('id'): 0 for contingency in root}
freq_protection_failure_potential = 0
share_unsecure = {}
total_freq = 0

def get_contingency_type(contingency_id):
    if 'BREAKER' in contingency_id:
        return 2  # N-2 event
    elif 'DELAYED' in contingency_id:
        return 1  # N-1 event with delayed clearing
    else:
        return 0  # N-1 event with normal clearing

for contingency in root:
    total_freq += float(contingency.get('frequency'))
    contingency_id = contingency.get('id')
    contingency_type = get_contingency_type(contingency_id)

    risk_contingency = []
    risk_contingency_screening = []

    found = False
    for line in wind_lines:
        if line in contingency_id:
            found = True
            break
    if found:
        pass #continue

    for static_id in contingency:
        once = True
        for job in static_id:
            total_computation_time[contingency_type] += float(job.get('simulation_time')) / 3600

            if True: # contingency_type == 2:
                total_total_computation_time += float(job.get('simulation_time')) / 3600
                if once:
                    total_cases += 1

                if float(job.get('load_shedding')) == 0:
                    total_computation_time_no_consequences += float(job.get('simulation_time')) / 3600
                    if once:
                        total_cases_no_consequences += 1
                once = False


        if static_id.get('variable_order') == 'True' or static_id.get('missing_events') == 'True':
            load_shedding_per_job = []
            cascading_path_per_job = []
            for job in static_id:
                load_shedding_per_job.append(float(job.get('load_shedding')))
                cascading_path = ''
                if 'trip_0' in job.attrib:
                    cascading_path += job.get('trip_0')
                if 'trip_1' in job.attrib:
                    cascading_path += job.get('trip_1')
                if 'trip_2' in job.attrib:
                    cascading_path += job.get('trip_2')
                cascading_path_per_job.append(cascading_path)

            total_protection_cases += 1
            if float(static_id.get('mean_load_shed')) > 0:
                total_protection_cases_with_consequences += 1
                if len(set(load_shedding_per_job)) > 1:  # True if some jobs have different amount of load shedding
                    total_protection_cases_with_consequences_protection_impact += 1  # Note that only 5 runs are performed, so some cases might be missed
            if float(static_id.get('mean_load_shed')) >0: # == 0:
                if len(set(cascading_path_per_job)) > 1:
                    total_protection_cases_with_consequences_cascading_path += 1  # Note: only accounts for the first 3 trips (a bit more if rtpv)


        if True:#contingency_type == 1:
            # if float(static_id.get('mean_load_shed')) > 100:
            #     continue

            risk_contingency.append(float(static_id.get('cost')))
            if positive(static_id, contingency_id):
                risk_contingency_screening.append(float(static_id.get('cost')))
            else:
                risk_contingency_screening.append(0)
            for job in static_id:
                total_computation_time_true += float(job.get('simulation_time')) / 3600
                if positive(static_id, contingency_id):
                    total_computation_time_screening += float(job.get('simulation_time')) / 3600


            if float(static_id.get('mean_load_shed')) == 0:
                if positive(static_id, contingency_id):
                    false_positives += 1
                    false_positives_list.append((contingency_id, static_id.get('static_id'), static_id.get('CCT'), static_id.get('shc_ratio'),
                                                 static_id.get('RoCoF'), static_id.get('dP_over_reserves')))
                else:
                    true_negatives += 1
            else:
                positives_per_contingency[contingency_id] = positives_per_contingency.get(contingency_id, 0) + 1
                if positive(static_id, contingency_id):
                    true_positives += 1
                else:
                    false_negatives += 1
                    false_negatives_list.append((contingency_id, static_id.get('static_id'), static_id.get('CCT'), static_id.get('shc_ratio'),
                                                 static_id.get('RoCoF'), static_id.get('dP_over_reserves')))
                    false_negatives_per_contingency[contingency_id] = false_negatives_per_contingency.get(contingency_id, 0) + 1
                    false_negatives_max_consequences_per_contingency[contingency_id] = max(false_negatives_max_consequences_per_contingency.get(contingency_id, 0),
                                                                                           float(static_id.get('mean_load_shed')))

            total_risk_true += np.mean(risk_contingency) / len(contingency)
            total_risk_screening += np.mean(risk_contingency_screening) / len(contingency)

        if float(static_id.get('mean_load_shed')) < 100:
            trips = []
            if 'trip_0' in job.attrib:
                trips.append(job.get('trip_0'))
            if 'trip_1' in job.attrib:
                trips.append(job.get('trip_1'))
            if 'trip_2' in job.attrib:
                trips.append(job.get('trip_2'))
            nb_potential_cases = sum(['Distance' in trip for trip in trips])
            if nb_potential_cases > 0:
                if static_id.get('variable_order') == 'True' or static_id.get('missing_events') == 'True':
                    pass
                    share_protection_failure_potential[contingency_id] += nb_potential_cases / len(contingency)
                    freq_protection_failure_potential += float(contingency.get('frequency')) * nb_potential_cases / len(contingency)
                else:
                    share_protection_failure_potential[contingency_id] += nb_potential_cases / len(contingency)
                    freq_protection_failure_potential += float(contingency.get('frequency')) * nb_potential_cases / len(contingency)
    share_unsecure[contingency_id] = contingency.get('share_unsecure')

    # if contingency.get('id')[0] == 'B':
    total_risk[contingency_type] += float(contingency.get('risk'))
    total_cost[contingency_type] += float(contingency.get('cost'))

    if float(contingency.get('ind_1')) >= float(contingency.get('ind_2')):
        ind_1[contingency_type] += 1
    else:
        ind_2[contingency_type] += 1


print('Computation time', total_computation_time)
print('Total risk', total_risk)
print('Total cost', total_cost)
print('Ind_1', ind_1)
print('Ind_2', ind_2)

print()
print(total_total_computation_time)
print(total_computation_time_no_consequences)
print('{:.1f}% ({:.1f}h out of {:.1f}) are on simulations with consequences'.format((total_total_computation_time-total_computation_time_no_consequences)/total_total_computation_time*100,
                                                                         total_total_computation_time-total_computation_time_no_consequences,
                                                                         total_total_computation_time))


print()
print(total_cases)
print(total_cases_no_consequences)
print('{:.1f}% of cases ({} out of {}) have consequences'.format((total_cases-total_cases_no_consequences)/total_cases*100,
                                                                      total_cases-total_cases_no_consequences,
                                                                      total_cases))

print()
# Unsecure
print('false_negatives', false_negatives)
print('true_positives', true_positives)
# Secure
print('false_positives', false_positives)
print('true_negatives', true_negatives)

for false_negative in false_negatives_list:
    pass #print(false_negative)

for false_positive in false_positives_list:
    pass #print(false_positive)

print('True risk', total_risk_true)
print('Screened risk', total_risk_screening)
print('Missing share (%)', (total_risk_true - total_risk_screening) / total_risk_true * 100)
print('Speed-up {:.2f}'.format(total_computation_time_true / total_computation_time_screening))


worst_contingency_ids = [contingency.get('id') for contingency in sorted(root, key = lambda item:item.get('cost'), reverse=True)]
for i, contingency_id in enumerate(worst_contingency_ids):
    if contingency_id not in false_negatives_per_contingency.keys():
        continue  # No false negatives for current contingency

    print("Rank {}, {}, misses: {}/{}, max shedding: {}".format(i+1, contingency_id, false_negatives_per_contingency[contingency_id],
                                                                positives_per_contingency[contingency_id], false_negatives_max_consequences_per_contingency[contingency_id]))

print()
print('Scenarios where protection-related uncertainties assumed important', total_protection_cases)
print('Scenarios where protection-related uncertainties assumed important, and non-zero consequences', total_protection_cases_with_consequences)
print(total_protection_cases_with_consequences_protection_impact)
print(total_protection_cases_with_consequences_cascading_path)

print()
for contingency_id in share_protection_failure_potential:
    if share_protection_failure_potential[contingency_id] != 0:
        print(contingency_id, share_protection_failure_potential[contingency_id] * 100, share_unsecure[contingency_id])
print(freq_protection_failure_potential)  # Only save first 3 trips, so might miss some cases, but assume full blackout below, so compensates + stable scenarios should not have more than 3 trips
print('Max cost protection failure', freq_protection_failure_potential * 0.01 * 500)  # Assume failure proba of protection of 0.01 and max consequences 500 + that contingency was initialy secure (cannot increase consequences by 500 if was already 500)
print('Cost', root.get('total_cost'))
print(total_freq)
