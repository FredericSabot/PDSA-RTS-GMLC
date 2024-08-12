from __future__ import annotations
import pypowsybl as pp
from natsort import natsorted
import glob
import random
import numpy as np
# from numba import jit
from sklearn.cluster import AgglomerativeClustering

"""
This script demonstrates the curse of dimensionality and shows that the dispatches generated in /2-SCOPF/d-Final-dispatch/
almost all differ from each other by at least 50MW.
"""

class OperatingPoint:
    def __init__(self, network: pp.network.Network):
        gens = network.get_generators().fillna(0)  # fillna replaces NaNs (usually means elements is disconnected) by 0s
        lines = network.get_lines().fillna(0)

        self.gens_p = gens.p.to_numpy()
        self.gens_q = gens.q.to_numpy()
        self.lines_p = lines.p1.to_numpy()
        self.lines_q = lines.q1.to_numpy()

    def close_to(self, other: OperatingPoint, distance):
        """ return max(self.gens.p - other.gens.p) < distance and max(self.gens.q - other.gens.q) < distance and \
               max(self.lines.p1 - other.lines.p1) < distance and max(self.lines.q1 - other.lines.q1) < distance """
        return max(self.gens_p - other.gens_p) < distance and max(self.gens_q - other.gens_q) < distance and \
               max(self.lines_p - other.lines_p) < distance and max(self.lines_q - other.lines_q) < distance

    # @jit(nopython=False, parallel=True)  # Does not seem to help a lot (nor to be parallel), might want to check with nopython=True (or jitclass)
    def distance_to(self, other: OperatingPoint):
        # return max([max(self.gens.p - other.gens.p), max(self.gens.q - other.gens.q), max(self.lines.p1 - other.lines.p1), max(self.lines.q1 - other.lines.q1)])
        max_1 = max(self.gens_p - other.gens_p)
        max_2 = max(self.gens_q - other.gens_q)
        max_3 = max(self.lines_p - other.lines_p)
        max_4 = max(self.lines_q - other.lines_q)
        return max(max_1, max_2, max_3, max_4)

try:
    distance_matrix = np.loadtxt('distance_matrix.csv')
except FileNotFoundError:
    static_files = natsorted(glob.glob('../../2-SCOPF/d-Final-dispatch/year/*.iidm'))
    operating_points = []
    for static_file in static_files:
        print(static_file, end='\r')
        n = pp.network.load(static_file)
        operating_points.append(OperatingPoint(n))
    print()

    nb_operating_points = len(operating_points)
    distance_matrix = np.zeros((nb_operating_points, nb_operating_points))

    for i in range(nb_operating_points):
        print(i, end='\r')
        for j in range(i):
            distance = operating_points[i].distance_to(operating_points[j])
            distance_matrix[i][j] = distance
            distance_matrix[j][i] = distance

    np.savetxt('distance_matrix.csv', distance_matrix)
nb_operating_points = distance_matrix.shape[0]


distances = [5, 10, 20, 50, 100, 200]
N_samples = 200

operating_points = list(range(nb_operating_points))
sampled_operating_points = operating_points.copy()
random.shuffle(sampled_operating_points)

for distance in distances:
    clustering = AgglomerativeClustering(linkage='complete', metric='precomputed', distance_threshold=distance, n_clusters=None)
    clustering.fit(distance_matrix)
    print(clustering.n_clusters_)

# From 8617 samples
# Distance: 5  , clusters: 8612, reduction: 0.06%, points per cluster: 1.0006
# Distance: 10 , clusters: 8580, reduction: 0.43%, points per cluster: 1.004
# Distance: 20 , clusters: 8340, reduction: 3.2% , points per cluster: 1.03
# Distance: 50 , clusters: 5916, reduction: 31%  , points per cluster: 1.46
# Distance: 100, clusters: 2752, reduction: 68%  , points per cluster: 3.13