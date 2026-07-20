# source ~/"Analysis Labs"/"Dev Tools"/Communicators/communicators-venv/bin/activate
# python3 backoff_equation_plot.py
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

# Parameters
mu = 0.0
sigma = 2.0
k = 1.0

# Create x in the finite interval [-k, +k]
x = np.linspace(-k, k, 2000)

# The capped normal
y = 2*(norm.cdf(np.tan(((np.pi / (2 * k)) * x)), loc=mu, scale=sigma) - 0.5)
# y = norm.pdf(np.tan(((np.pi / (2 * k)) * x)), loc=mu, scale=sigma)

# Plot
plt.figure(figsize=(10, 6))
plt.plot(x, y, color='red', linewidth=2.5)
plt.title(f'Capped Normal Bell: normal_cdf(tan(θ)) | θ ∈ [-{k}, +{k}]')
plt.xlabel(f'θ (radians) — finite domain from -{k} to +{k}')
plt.ylabel('Density')
plt.grid(True, alpha=0.3)

# Vertical lines at the boundaries
plt.axvline(-k, color='gray', linestyle='--', alpha=0.5)
plt.axvline(k, color='gray', linestyle='--', alpha=0.5)

# Optional annotations
plt.text(-k + 0.1, 0.05, f'→ 0 as θ → -{k}', rotation=90, fontsize=10)
plt.text(k - 0.4, 0.05, f'→ 0 as θ → +{k}', rotation=90, fontsize=10)

# Save the plot as plot1.png (in the current working directory)
plt.savefig('plot1.png', dpi=300, bbox_inches='tight')

# Optional: also show the plot on screen
plt.show()

print("Plot saved successfully as 'plot1.png'")
