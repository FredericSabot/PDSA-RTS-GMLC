import xml.etree.ElementTree as etree
from collections import defaultdict
import pypowsybl as pp

NETWORK_NAME = 'RTS'

analysis_root = etree.parse('../AnalysisOutput.xml').getroot()

# Regroup contingencies by hidden failure instead of by base contingency
base_contingencies = defaultdict(etree.Element)
contingencies_per_failure = defaultdict(list[etree.Element])
for contingency in analysis_root:
    base_contingencies[contingency.get('id')] = contingency
    for sub_contingency in contingency.iter('Contingency'):
        id_parts = sub_contingency.get('id').split('~')
        failures = id_parts[1:]  # Empty, so skipped if contingency does not include hidden failures
        for failure in failures:
            contingencies_per_failure[failure].append(sub_contingency)

network = pp.network.load(f'../../{NETWORK_NAME}-Data/{NETWORK_NAME}.iidm')
lines = network.get_lines()
gens = network.get_generators()
vl = network.get_voltage_levels()

root = etree.Element('HiddenFailureAnalysis')
for failure_type in ['Distance', 'Generator']:
    frequency_failure_type = 0
    risk_failure_type = 0
    cost_failure_type = 0
    failure_type_element = etree.SubElement(root, 'FailureType')
    failure_type_element.set('Type', failure_type)
    for failure in contingencies_per_failure.keys():
        if 'Distance' in failure:
            failure_type_ = 'Distance'
            element_id = failure.split('_side')[0]
            side = failure.split('_side')[1][0]
            voltage_level = vl.at[lines.at[element_id, f'voltage_level{side}_id'], 'nominal_v']
        else:
            failure_type_ = 'Generator'
            element_id = failure
            voltage_level = vl.at[gens.at[element_id, f'voltage_level_id'], 'nominal_v']
        if failure_type_ != failure_type:
            continue

        frequency_failure = 0
        risk_failure = 0
        cost_failure = 0
        failure_element = etree.SubElement(failure_type_element, 'Failure')
        for contingency in contingencies_per_failure[failure]:
            contingency_id = contingency.get('id')
            base_contingency_id = contingency_id.split('~')[0]
            base_contingency = base_contingencies[base_contingency_id]
            base_risk = float(base_contingency.get('risk'))
            base_cost = float(base_contingency.get('cost'))
            frequency = float(contingency.get('frequency'))
            frequency_failure += frequency

            # Increase of risk caused by increase of load shedding in scenario with hidden failure compared to base case
            added_risk = frequency * float(contingency.get('mean_load_shed')) - float(base_contingency.get('mean_load_shed'))
            contingency.set('added_risk', str(added_risk))

            mean_consequences = float(contingency.get('cost')) / frequency
            mean_consequences_base = float(base_contingency.get('cost')) / float(base_contingency.get('frequency'))
            added_cost = frequency * (mean_consequences - mean_consequences_base)
            contingency.set('added_cost', str(added_cost))

            risk_failure += max(0, added_risk)  # Assume hidden failures always lead to a higher risk
            cost_failure += max(0, added_cost)
            failure_element.append(contingency)

        failure_element.set('id', failure)
        failure_element.set('frequency', str(frequency_failure))
        failure_element.set('risk', str(risk_failure))
        failure_element.set('cost', str(cost_failure))
        failure_element.set('vl', str(voltage_level))
        frequency_failure_type += frequency_failure
        risk_failure_type += risk_failure
        cost_failure_type += cost_failure
    failure_type_element.set('frequency', str(frequency_failure_type))
    failure_type_element.set('risk', str(risk_failure_type))
    failure_type_element.set('cost', str(cost_failure_type))
    if frequency_failure_type > 10:
        print(f'Warning: type "{failure_type}" has hidden failure(s) that occur more than 10 times a year, check credibility (note: even if not implemented here, some generators might have a higher hidden failure rate than the global average (commissioning, inverters vs. synchronous machnes, etc.))')

tree = etree.ElementTree(root)
etree.indent(tree, space="\t")  # Pretty-print
tree.write('HiddenFailureAnalysis.xml', xml_declaration=True, encoding='UTF-8')