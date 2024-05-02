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


distances = [5, 10, 20, 50, 100]
N_samples = 200

operating_points = list(range(nb_operating_points))
sampled_operating_points = operating_points.copy()
random.shuffle(sampled_operating_points)

""" for distance in distances:
    samples = sampled_operating_points[:N_samples]
    coverage = 0
    count = 0
    for operating_point in operating_points:
        print(count, end='\r')
        count += 1
        # found = False
        for sample in samples:
            if distance_matrix[sample][operating_point] < distance:
                # found = True
                coverage += 1
                break
    coverage /= len(operating_points)
    print("Distance:", distance, ', coverage:', coverage)
print('MC coverage:', 1 - 1/N_samples) """

# Note: coverage might be a bit better if lumped generators that are on the same bus and with the same fuel/type

# N_samples = 100
# Distance: 0 , coverage: 0.011684  # Manually computed N_samples/8559
# Distance: 5 , coverage: 0.011800443977100129
# Distance: 10 , coverage: 0.011917280056081317
# Distance: 20 , coverage: 0.01331931300385559
# Distance: 50 , coverage: 0.043463021381002456
# Distance: 100 , coverage: 0.41032830938193715
# MC coverage: 0.99

# N_samples = 200
# Distance: 0 , coverage: 0.023367  # Manually computed N_samples/8559

# MC coverage: 0.995
# Distance: 5 , coverage: 0.023367215796237878
# Distance: 10 , coverage: 0.023600887954200258
# Distance: 20 , coverage: 0.025470265217899288
# Distance: 50 , coverage: 0.08061689449702068
# Distance: 100 , coverage: 0.5500642598434397

# Distance: 5 , coverage: 0.011683607898118939


""" for distance in distances:
    leaders = []
    cluster_sizes = []

    count = 0
    for i in range(nb_operating_points):
        print(count, end='\r')
        count += 1
        found = False
        for j in leaders:
            if distance_matrix[i][j] < distance:
                found = True
                cluster_sizes[leaders.index(j)] += 1
                break
        if not found:
            leaders.append(i)
            cluster_sizes.append(1)

    largest_clusters = cluster_sizes.copy()
    largest_clusters.sort(reverse=True)
    print('Distance:', distance, ', samples:', N_samples, ', equiv samples:', sum(largest_clusters[:N_samples]),
        ', coverage:', sum(largest_clusters[:N_samples])/len(operating_points), ', coverage2:', N_samples/len(leaders)) """

# Distance: 5 , samples: 200 , equiv samples: 203 , coverage: 0.023717724033181446 , coverage2: 0.02337540906965872
# Distance: 10 , samples: 200 , equiv samples: 240 , coverage: 0.028040658955485454 , coverage2: 0.023476933912431035
# Distance: 20 , samples: 200 , equiv samples: 434 , coverage: 0.0507068582778362 , coverage2: 0.024175027196905598
# Distance: 50 , samples: 200 , equiv samples: 1545 , coverage: 0.18051174202593762 , coverage2: 0.036436509382401165
# Distance: 100 , samples: 200 , equiv samples: 6095 , coverage: 0.7121159013903493 , coverage2: 0.20100502512562815

for distance in distances:
    clustering = AgglomerativeClustering(linkage='complete', metric='precomputed', distance_threshold=distance, n_clusters=None)
    clustering.fit(distance_matrix)
    print(clustering.n_clusters_)
