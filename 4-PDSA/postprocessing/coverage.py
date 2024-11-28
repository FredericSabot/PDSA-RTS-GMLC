from __future__ import annotations
import pypowsybl as pp
from natsort import natsorted
import glob
import random
import numpy as np
# from numba import jit
from sklearn.cluster import AgglomerativeClustering
import matplotlib.pyplot as plt
import os
from lxml import etree
import pickle
import csv

"""
This script demonstrates the curse of dimensionality and shows that the dispatches generated in /2-SCOPF/d-Final-dispatch/
almost all differ from each other by at least 50MW.
"""

NETWORK_NAME = 'RTS'

class OperatingPoint:
    def __init__(self, network: pp.network.Network):
        gens = network.get_generators().fillna(0)  # fillna replaces NaNs (usually means elements is disconnected) by 0s
        lines = network.get_lines().fillna(0)

        self.gens_p = gens.p.to_numpy()
        self.gens_q = gens.q.to_numpy()
        self.lines_p = lines.p1.to_numpy()
        self.lines_q = lines.q1.to_numpy()

    def close_to(self, other: OperatingPoint, distance):
        return self.distance_to(other) < distance


    # @jit(nopython=False, parallel=True)  # Does not seem to help a lot (nor to be parallel), might want to check with nopython=True (or jitclass)
    def distance_to(self, other: OperatingPoint, considered_generator_indexes = None, considered_line_indexes = None):
        # considered_generator_indexes: list of 1's for the index of considered generators, 0's for non-considered ones

        # return max([max(self.gens.p - other.gens.p), max(self.gens.q - other.gens.q), max(self.lines.p1 - other.lines.p1), max(self.lines.q1 - other.lines.q1)])
        if considered_generator_indexes is None:
            max_1 = max(self.gens_p - other.gens_p)
            max_2 = max(self.gens_q - other.gens_q)
        else:
            max_1 = max((self.gens_p - other.gens_p) * np.array(considered_generator_indexes))
            max_2 = max((self.gens_q - other.gens_q) * np.array(considered_generator_indexes))

        if considered_line_indexes is None:
            max_3 = max(self.lines_p - other.lines_p)
            max_4 = max(self.lines_q - other.lines_q)
        else:
            max_3 = max((self.lines_p - other.lines_p) * np.array(considered_line_indexes))
            max_4 = max((self.lines_q - other.lines_q) * np.array(considered_line_indexes))

        return max(max_1, max_2, max_3, max_4)

static_files = natsorted(glob.glob(f'../../2-SCOPF/d-Final-dispatch/year_{NETWORK_NAME}/*.iidm'))
try:
    with open(f'distance_matrix_{NETWORK_NAME}.pickle', 'rb') as f:
        distance_matrix = pickle.load(f)
except FileNotFoundError:
    try:
        with open(f'operating_points_{NETWORK_NAME}.pickle', 'rb') as f:
            operating_points = pickle.load(f)
    except FileNotFoundError:
        operating_points = []
        operating_points: list[OperatingPoint]
        for static_file in static_files:
            print(static_file, end='\r')
            n = pp.network.load(static_file)
            operating_points.append(OperatingPoint(n))
        print()
        with open(f'operating_points_{NETWORK_NAME}.pickle', 'wb') as f:
            pickle.dump(operating_points, f)

    nb_operating_points = len(operating_points)
    distance_matrix = np.zeros((nb_operating_points, nb_operating_points))


    """
    Only consider generators and lines that are in a given zone to compute the distance between operating points.
    For the RTS, generators are identified by the first letter of their gen_id and lines if they contain the letter A, B, or C (zones 1, 2, and 3 respectivelly). This does not work for the Texas network, but zones are significantly larger there, so clustering is unlikely to work well (almost no clustering at all).
    Note: the pickle file should be deleted/renamed if the considered zone is changed
    """
    network = pp.network.load(static_files[0])
    gens = network.get_generators()
    lines = network.get_lines()
    considered_generator_indexes = []
    considered_line_indexes = []
    for gen_id in gens.index:
        if gen_id[0] == '3':
            considered_generator_indexes.append(1)
        else:
            considered_generator_indexes.append(0)
    for line_id in lines.index:
        if 'C' in line_id:
            considered_line_indexes.append(1)
        else:
            considered_line_indexes.append(0)


    for i in range(nb_operating_points):
        print(i, end='\r')
        for j in range(i):
            distance = operating_points[i].distance_to(operating_points[j], considered_generator_indexes, considered_line_indexes)
            distance_matrix[i][j] = distance
            distance_matrix[j][i] = distance

    with open(f'distance_matrix_{NETWORK_NAME}.pickle', 'wb') as f:
        pickle.dump(distance_matrix, f)
nb_operating_points = distance_matrix.shape[0]


distances = [5, 10, 20, 50, 100, 200]

for distance in distances:
    clustering = AgglomerativeClustering(linkage='complete', metric='precomputed', distance_threshold=distance, n_clusters=None)
    clustering.fit(distance_matrix)
    n = clustering.n_clusters_
    print(f'Distance: {distance}, clusters: {clustering.n_clusters_}, reduction: {100 * (1 - n / nb_operating_points)}%, points per cluster: {nb_operating_points / n}')


# From 8617 samples
# Distance: 5  , clusters: 8612, reduction: 0.06%, points per cluster: 1.0006
# Distance: 10 , clusters: 8580, reduction: 0.43%, points per cluster: 1.004
# Distance: 20 , clusters: 8340, reduction: 3.2% , points per cluster: 1.03
# Distance: 50 , clusters: 5916, reduction: 31%  , points per cluster: 1.46
# Distance: 100, clusters: 2752, reduction: 68%  , points per cluster: 3.13
# Distance: 200, clusters: 989,  reduction: 88%  , points per clsuter: 8.71

# Zone 1 only
# Distance: 5  , clusters: 8475, reduction: 1.64% , points per cluster: 1.01
# Distance: 10 , clusters: 7853, reduction: 8.86% , points per cluster: 1.09
# Distance: 20 , clusters: 5727, reduction: 33.53%, points per cluster: 1.50
# Distance: 50 , clusters: 2241, reduction: 73.99%, points per cluster: 3.84
# Distance: 100, clusters: 804 , reduction: 90.66%, points per cluster: 10.71
# Distance: 200, clusters: 207 , reduction: 97.59%, points per cluster: 41.62

# Zone 2 only
# Distance: 5  , clusters: 8190, reduction: 4.955320877335501%, points per cluster: 1.0521367521367522
# Distance: 10 , clusters: 6790, reduction: 21.20227457351746%, points per cluster: 1.2690721649484535
# Distance: 20 , clusters: 4336, reduction: 49.68086340953928%, points per cluster: 1.9873154981549817
# Distance: 50 , clusters: 1662, reduction: 80.71254496924684%, points per cluster: 5.184717208182912
# Distance: 100, clusters: 626 , reduction: 92.73529070442149%, points per cluster: 13.76517571884984
# Distance: 200, clusters: 160 , reduction: 98.14320529186492%, points per cluster: 53.85625

# Zone 3 only
# Distance: 5  , clusters: 8596, reduction: 0.24% , points per cluster: 1.002442996742671
# Distance: 10 , clusters: 8495, reduction: 1.41% , points per cluster: 1.0143613890523837
# Distance: 20 , clusters: 7872, reduction: 8.64% , points per cluster: 1.0946392276422765
# Distance: 50 , clusters: 4038, reduction: 53.13%, points per cluster: 2.133977216443784
# Distance: 100, clusters: 1723, reduction: 80.00%, points per cluster: 5.00116076610563
# Distance: 200, clusters: 504 , reduction: 94.15%, points per cluster: 17.09722222222222

distance = 100
clustering = AgglomerativeClustering(linkage='complete', metric='precomputed', distance_threshold=distance, n_clusters=None)
clustering.fit(distance_matrix)

N_samples = 1000
random.seed(42)
sampled_operating_points = list(range(nb_operating_points))
random.shuffle(sampled_operating_points)

sampled_clusters = []
nb_simulations = 0
y_axis = []
for i in range(N_samples):
    index = sampled_operating_points[i]

    cluster = clustering.labels_[index]
    if cluster in sampled_clusters:
        pass
    else:
        sampled_clusters.append(cluster)
        nb_simulations += 1
    y_axis.append(nb_simulations)
x_axis = range(N_samples)

plt.plot(x_axis, x_axis, label='Brute sampling')
plt.plot(x_axis, y_axis, label='Do not repeat cluster')
plt.plot(x_axis, [clustering.n_clusters_] * len(x_axis), label='Full enumerate')
plt.legend()
plt.xlabel('Number of samples')
plt.ylabel('Number of actual simulations')
plt.title('Zone A, max distance = 100MVA, 804 clusters')
# plt.show()




root = etree.parse('../AnalysisOutput.xml').getroot()
f = open('clustering.csv', 'w')
writer = csv.writer(f)
writer.writerow(['Contingency id', 'Share unsecure states', 'Speed up', 'Nb samples', 'Nb sampled clusters', 'Actual cost'] + [f'Estimated costs {i+1}' for i in range(20)])

operating_point_ids = [int(os.path.basename(file).split('.')[-2]) for file in static_files]

for contingency in sorted(root, key = lambda item:item.get('cost'), reverse=True):
    frequency = float(contingency.get('frequency'))
    contingency_id = contingency.get('id')
    share_unsecure_states = contingency.get('share_unsecure')

    estimated_costs = []
    for seed in range(20):
        random.seed(seed)
        static_ids = []
        for static_id in contingency:
            if static_id.tag == 'StaticId':
                static_ids.append(static_id)
        random.shuffle(static_ids)

        cluster_results = {}
        actual_costs = []
        clustered_costs = []
        # nb_actual_simulations = 0
        for static_id in static_ids:
            static_id_ = static_id.get('static_id')
            cost = float(static_id.get('cost'))
            cluster_id = clustering.labels_[operating_point_ids.index(int(static_id_))]
            if cluster_id not in cluster_results:
                cluster_results[cluster_id] = {'costs': [cost], 'static_ids': [static_id_]}
                # nb_actual_simulations += 1
            else:
                cluster_results[cluster_id]['costs'     ].append(cost)
                cluster_results[cluster_id]['static_ids'].append(static_id_)
                # if cluster_results[cluster_id]['costs'][0] != 0:
                #     nb_actual_simulations += 1

            actual_costs.append(cost)
            clustered_costs.append(cluster_results[cluster_id]['costs'][0])

            # If cluster is secure, don't rerun simulation, else do. Not a good idea, because it introduces a severe bias (missed risk if think a cluster is secure)
            # if cluster_results[cluster_id]['costs'][0] == 0:
            #     clustered_costs.append(cluster_results[cluster_id]['costs'][0])
            # else:
            #     clustered_costs.append(cost)

        actual_cost = np.mean(actual_costs)
        estimated_cost = np.mean(clustered_costs)
        estimated_costs.append(estimated_cost)

    speedup = len(static_ids) / len(cluster_results)  # Speed up might vary from run to run, but only consider last one
    # speedup = len(static_ids) / nb_actual_simulations
    writer.writerow([contingency_id, share_unsecure_states, speedup, len(static_ids), len(cluster_results), actual_cost] + estimated_costs)

f.close()
