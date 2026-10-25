import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ee_paths import EE

ep = np.load(EE("dqn_am_rewards.npy"))
k = 5
ma = np.convolve(ep, np.ones(k)/k, "valid")

FLOOR = -400   # y-axis cap for readability
clipped = np.clip(ep, FLOOR, None)

plt.figure(figsize=(7,4))
plt.plot(clipped, alpha=0.35, label="episode reward (clipped)")
plt.plot(range(k-1, len(ep)), np.clip(ma, FLOOR, None), linewidth=2, label=f"{k}-episode moving avg")

# honestly annotate any episodes that fall below the floor
out = np.where(ep < FLOOR)[0]
for i in out:
    plt.annotate(f"actual {ep[i]:.0f}", xy=(i, FLOOR), xytext=(i-22, FLOOR+70),
                 fontsize=8, color="crimson",
                 arrowprops=dict(arrowstyle="->", color="crimson"))
plt.ylim(FLOOR, 20)
plt.xlabel("Training episode")
plt.ylabel("Total reward per episode\n(higher = less waiting)")
plt.title("DQN learning curve (y-axis clipped) — Don Mills & Lawrence, AM peak")
plt.legend(loc="lower right"); plt.grid(alpha=0.3); plt.tight_layout()
plt.savefig(EE("dqn_am_learning_curve_clipped.png"), dpi=140)
print(f"Saved dqn_am_learning_curve_clipped.png  |  clipped {len(out)} outlier(s): "
      + ", ".join(f"ep{i}={ep[i]:.0f}" for i in out))
