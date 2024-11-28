from lxml import etree

"""
Based on the results of the PDSA (../AnalysisOutput.xml), this scripts counts the number of
simulations that lead to numerical convergence issues.
"""

XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
file = '../AnalysisOutput.xml'
root = etree.parse(file, XMLparser).getroot()

cases = 0
unsecure_cases = 0
convergence_cases = 0
for contingency in root:
    for static_id in contingency:
            if static_id.tag != 'StaticId':
                 continue
            for job in static_id:
                if 'DELAYED' in contingency.get('id'):
                    cases += 1
            if float(static_id.get('mean_load_shed')) > 0:
                unsecure_cases += 1
            if float(static_id.get('mean_load_shed')) > 100:
                convergence_cases += 1

print(cases, unsecure_cases, convergence_cases)
