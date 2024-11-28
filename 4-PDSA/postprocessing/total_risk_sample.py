import random
from lxml import etree
import numpy as np
from math import sqrt
import matplotlib.pyplot as plt

"""
Based on the results of the PDSA (../AnalysisOutput.xml), this scripts computes the standard error
of the total risk and shows how it evolves with the number of samples.
"""

MAX_CONSEQUENCES = 500

XMLparser = etree.XMLParser(remove_blank_text=True)  # Necessary for pretty_print to work
file = '../AnalysisOutput.xml'
root = etree.parse(file, XMLparser).getroot()

frequencies = [float(contingency.get('frequency')) for contingency in root]
consequences = []
sum_f = sum(frequencies)

x = []
std_dev = []
coverage = []
total = []

N = int(1.5e5)

contingency_ids = random.choices(population=range(len(root)), weights=frequencies, k=N)

for i, contingency_id in enumerate(contingency_ids):
    contingency = root[contingency_id]

    static_ids = []
    for static_id in contingency:
        if static_id.tag == 'StaticId':
            static_ids.append(static_id)
    static_id = random.choice(range(len(static_ids)))
    consequence = float(static_ids[static_id].get('cost')) / float(contingency.get('frequency'))  # cost actually refers to risk in cost units
    # consequence = float(contingency[static_id].get('mean_load_shed'))
    consequences.append(consequence)

    if (i + 1 ) % 200 == 0:
        x.append(i)
        var = np.var(consequences)
        mean = np.mean(consequences)

        indicator_1 = sum_f * sqrt(var / (i+1))

        # SE of risk from unobserved samples with 99% confidence
        p = 1 - 0.01**(1/(i+1))
        b = max((MAX_CONSEQUENCES-mean)**2, (mean-0)**2)
        indicator_2 = sum_f * sqrt(p*b/(i+1))

        std_dev.append(indicator_1)
        coverage.append(indicator_2)
        total.append(sqrt(indicator_1**2 + indicator_2**2))

        print(i+1, indicator_1, indicator_2, sqrt(indicator_1**2 + indicator_2**2), sep='\t')

print(np.var(consequences))  # 234 (MW**2) for cost, 22%**2 for load_shed

plt.plot(x, std_dev, label='Standard deviation')
plt.plot(x, coverage, label='Coverage')
plt.plot(x, total, label='Total error')

plt.xlabel('Samples')
plt.ylabel('Cost [M€/y]')

total_cost = float(root.get('total_cost'))
print('Total cost', total_cost)
# plt.plot(x, total_cost)
ax = plt.gca()
ax.set_ylim([0, 0.3 * total_cost])
plt.axhline(y=0.04*total_cost, color='r', linestyle='-', label='4% of total cost')

plt.legend()
plt.grid()

plt.show()