import xml.etree.ElementTree as etree
from collections import defaultdict
import pypowsybl as pp

NETWORK_NAME = 'RTS'

analysis_root = etree.parse('../AnalysisOutput.xml').getroot()

# Regroup contingencies by hidden failure instead of by base contingency
contingencies_per_failure = defaultdict(list[etree.Element])
for contingency in analysis_root:
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
            frequency_failure += float(contingency.get('frequency'))
            risk_failure += float(contingency.get('risk'))
            cost_failure += float(contingency.get('cost'))
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

tree = etree.ElementTree(root)
etree.indent(tree, space="\t")  # Pretty-print
tree.write('HiddenFailureAnalysis.xml', xml_declaration=True, encoding='UTF-8')