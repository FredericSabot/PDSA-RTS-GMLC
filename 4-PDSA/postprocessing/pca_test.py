from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import pickle
import matplotlib.pyplot as plt
import numpy as np
from coverage import OperatingPoint

NETWORK_NAME = 'RTS'

with open(f'operating_points_{NETWORK_NAME}.pickle', 'rb') as f:
    operating_points = pickle.load(f)

X = np.array([(op.flatten()) for op in operating_points])
print(X.shape)
X = StandardScaler().fit_transform(X)

from sklearn.linear_model import LinearRegression
model = LinearRegression().fit(X[:, [0,1,2]], X)
r2 = model.score(X[:, [0,1,2]], X)
print(f"Variance explained (R² across all features) = {r2:.3f}")
# 0.482 when all features (P/Q of generators/lines) are considered (higher than first 3 features from PCA, but probably different metric)
# 0.538 when the only features are the generators active power setpoints

# pca = PCA(n_components=0.95)  # keep 95% variance
pca = PCA(n_components=50)  # keep 50 first components
Xp = pca.fit_transform(X)
explained = np.cumsum(pca.explained_variance_ratio_)
print(Xp.shape)

plt.figure(figsize=(7, 4))
plt.plot(np.arange(1, len(explained) + 1), explained, marker='o')
plt.xlabel("Number of Principal Components (k)")
plt.ylabel("Cumulative Explained Variance")
plt.title("Explained Variance vs. Number of Components")
plt.grid(True)
plt.axhline(0.90, color='r', linestyle='--', label='90% variance')
plt.axhline(0.95, color='r', linestyle='--', label='95% variance')
plt.legend()
plt.tight_layout()
plt.show()
