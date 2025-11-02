from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KernelDensity
import pickle
import matplotlib.pyplot as plt
import numpy as np
from coverage import OperatingPoint

NETWORK_NAME = 'RTS'

with open(f'operating_points_{NETWORK_NAME}.pickle', 'rb') as f:
    operating_points = pickle.load(f)

X = np.array([(op.flatten()) for op in operating_points])
# Only keep first 3 features (total wind, total solar, total load)
X3 = X[:, :3]
print(X3.shape)


scaler = StandardScaler().fit(X3)
X3s = scaler.transform(X3)

# Find optimal kde bandwidth though grid search
from sklearn.model_selection import GridSearchCV
bandwidths = np.logspace(-2, 1, 10)
grid = GridSearchCV(
    KernelDensity(kernel='gaussian'),
    {'bandwidth': bandwidths},
    cv=5
)
grid.fit(X3s)
bandwidth = grid.best_estimator_.bandwidth
print("Best bandwidth =", bandwidth)


# Remove points with 0 solar/wind production (temporary, for better visualisation of the rest of the kde only)
feature_names = ["Total wind", "Total solar", "Total load"]
X3 = X3[X3[:, 0] > 0]
X3 = X3[X3[:, 1] > 0]
X3s = scaler.transform(X3)
print(X3.shape)

kde = KernelDensity(kernel='gaussian', bandwidth=bandwidth).fit(X3s)
logp = kde.score_samples(X3s)
p_hat = np.exp(logp)
p_hat = p_hat / p_hat.sum()

X3 = np.asarray(X3)
p_hat = np.asarray(p_hat)

# 2D scatter plot
fig, ax = plt.subplots(figsize=(6, 5))
sc = ax.scatter(X3[:, 0], X3[:, 1], c=p_hat, s=10, cmap="viridis", alpha=0.7)
plt.colorbar(sc, ax=ax, label=r"$\hat p(x)$")
ax.set_xlabel(feature_names[0])
ax.set_ylabel(feature_names[1])
ax.set_title("Estimated PDF (KDE) — 2D slice")
plt.tight_layout()
plt.show()

# 3D scatter plot
fig = plt.figure(figsize=(7, 6))
ax = fig.add_subplot(111, projection='3d')
p_colors = p_hat / np.max(p_hat)  # normalize for color scaling
p_colors = plt.cm.viridis(p_colors)
ax.scatter(X3[:, 0], X3[:, 1], X3[:, 2], c=p_colors, s=10, alpha=0.7)
ax.set_xlabel(feature_names[0])
ax.set_ylabel(feature_names[1])
ax.set_zlabel(feature_names[2])
ax.set_title("Estimated PDF (KDE) — 3D visualization")
plt.tight_layout()
plt.show()


# 3D heatmap with slider for 3rd feature
from matplotlib.widgets import Slider
# Build grid for x–y plane
N = 80
x_lin = np.linspace(X3s[:, 0].min(), X3s[:, 0].max(), N)
y_lin = np.linspace(X3s[:, 1].min(), X3s[:, 1].max(), N)
xx, yy = np.meshgrid(x_lin, y_lin)

# Create figure and slider
fig, ax = plt.subplots(figsize=(6, 5))
plt.subplots_adjust(bottom=0.2)
z_init = X3s[:, 2].mean()

# Evaluate KDE slice at given z
def eval_slice(z_val):
    grid = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z_val)])
    log_dens = kde.score_samples(grid)
    return np.exp(log_dens).reshape(xx.shape)

dens = eval_slice(z_init)
im = ax.imshow(dens, origin='lower', cmap='viridis',
               extent=[X3[:, 0].min(), X3[:, 0].max(), X3[:, 1].min(), X3[:, 1].max()])
ax.set_xlabel(feature_names[0])
ax.set_ylabel(feature_names[1])
ax.set_title(f"KDE slice at mean {feature_names[2]}")

# Slider
ax_slider = plt.axes([0.2, 0.05, 0.6, 0.03])
slider = Slider(ax_slider, f"{feature_names[2]} (scaled)",
                X3s[:, 2].min(), X3s[:, 2].max(), valinit=z_init)

def update(val):
    z_val = slider.val
    dens = eval_slice(z_val)
    im.set_data(dens)
    ax.set_title(f"KDE slice at {feature_names[2]}={scaler.inverse_transform([[0, 0, z_val]])[0,2]:.2f}")
    fig.canvas.draw_idle()

slider.on_changed(update)
plt.show()
