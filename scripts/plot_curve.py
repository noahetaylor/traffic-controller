import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ee_paths import EE

ep = np.load(EE("dqn_am_rewards.npy"))
print(f"Loaded {len(ep)} episodes.  first={ep[0]:.1f}  last={ep[-1]:.1f}  best={ep.max():.1f}")

plt.figure(figsize=(7,4))
plt.plot(ep, alpha=0.35, label="episode reward")
if len(ep) >= 5:
    k = 5
    ma = np.convolve(ep, np.ones(k)/k, "valid")
    plt.plot(range(k-1, len(ep)), ma, linewidth=2, label=f"{k}-episode moving avg")
plt.xlabel("Training episode")
plt.ylabel("Total reward per episode\n(higher = less waiting)")
plt.title("DQN learning curve — Don Mills & Lawrence, AM peak")
plt.legend(); plt.grid(alpha=0.3); plt.tight_layout()
plt.savefig(EE("dqn_am_learning_curve.png"), dpi=140)
print("Saved dqn_am_learning_curve.png")
