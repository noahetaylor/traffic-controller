import numpy as np, xml.etree.ElementTree as ET, subprocess, os
import sumo_rl
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import BaseCallback
from ee_paths import EE

NET=EE("donmills_final.net.xml"); ROU=EE("am_peak.rou.xml")

# ---- reward/episode logging so we can plot the learning curve ----
class RewardLogger(BaseCallback):
    def __init__(self): super().__init__(); self.ep=[]; self.cur=0
    def _on_step(self):
        self.cur+=float(self.locals["rewards"][0])
        if self.locals["dones"][0]:
            self.ep.append(self.cur); self.cur=0
        return True

env = sumo_rl.SumoEnvironment(
    net_file=NET, route_file=ROU,
    single_agent=True, use_gui=False,
    num_seconds=3600,
    delta_time=5,            # agent makes a decision every 5 sim-seconds
    yellow_time=3,
    min_green=5, max_green=40,
    reward_fn="diff-waiting-time",
)

model = DQN("MlpPolicy", env,
            learning_rate=1e-3, buffer_size=100000,
            learning_starts=2000, batch_size=64, gamma=0.99,
            exploration_fraction=0.4, exploration_final_eps=0.03,
            train_freq=1, target_update_interval=1000,
            verbose=1, seed=42)

cb = RewardLogger()
model.learn(total_timesteps=80000, callback=cb)
model.save(EE("dqn_donmills_am"))
np.save(EE("dqn_am_rewards.npy"), np.array(cb.ep))
print(f"Saved model (dqn_donmills_am.zip) and {len(cb.ep)} episode rewards.")

# ---- evaluate the trained agent, writing its own tripinfo ----
eval_env = sumo_rl.SumoEnvironment(
    net_file=NET, route_file=ROU, single_agent=True, use_gui=False,
    num_seconds=3600, delta_time=5, yellow_time=3, min_green=5, max_green=40,
    reward_fn="diff-waiting-time",
    additional_sumo_cmd=f'--tripinfo-output {EE("rl_am.xml")}')
obs,_=eval_env.reset(); done=False
while not done:
    a,_=model.predict(obs, deterministic=True)
    obs,r,term,trunc,_=eval_env.step(int(a)); done=term or trunc
eval_env.close()

tr=ET.parse(EE("rl_am.xml")).findall("tripinfo")
w=[float(x.get("waitingTime")) for x in tr]
print("\n===== AM PEAK — three-way result =====")
print(f"Fixed-time : 54.24 s   (n=4560)")
print(f"Actuated   : 53.45 s   (n=4745)")
print(f"RL (DQN)   : {sum(w)/len(w):6.2f} s   (n={len(w)})")

# ---- plot the learning curve ----
try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    ep=np.load(EE("dqn_am_rewards.npy"))
    plt.figure(figsize=(7,4))
    plt.plot(ep, alpha=0.4, label="episode reward")
    if len(ep)>=5:
        k=5; plt.plot(range(k-1,len(ep)), np.convolve(ep,np.ones(k)/k,"valid"), label=f"{k}-ep moving avg")
    plt.xlabel("training episode"); plt.ylabel("total reward (higher = less waiting)")
    plt.title("DQN learning curve — Don Mills & Lawrence, AM peak")
    plt.legend(); plt.tight_layout(); plt.savefig(EE("dqn_am_learning_curve.png"), dpi=140)
    print("Saved dqn_am_learning_curve.png")
except Exception as e:
    print("Plot skipped:", e)
