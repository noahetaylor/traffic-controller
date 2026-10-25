"""Retrain the AM DQN, selecting for robustness across demand realizations.

What changed vs train_rl_am.py
------------------------------
The original agent was NOT overfitted to one arrival pattern -- sumo-rl's sumo_seed
defaults to "random", so training already saw ~111 randomly seeded realizations.
Its failure mode is different: it is fine on ~5/8 evaluation seeds and collapses to
~105 s on the other ~3/8. The plausible mechanism is that full gridlock is rare in
training, so on an unlucky realization the agent is outside anything it learned and
never recovers.

Two changes target that:
  1. EvalCallback with n_eval_episodes=4 (was 1). Selecting a snapshot on a single
     episode picks whichever policy got a lucky realization; averaging over 4 makes
     the selection itself robustness-aware.
  2. The final reported policy is the BEST snapshot, evaluated over multiple seeds,
     never the last weights.

Baselines to beat (protected-permissive, mean of 5 seeds):
    fixed-time 23.60 s (Webster, build_matched_baselines.py)
    actuated   23.81 s (swept by tune_actuated_pp.py; the first untuned cut was
                        31.61 s, which would have flattered the RL agent)
"""

import numpy as np, statistics, xml.etree.ElementTree as ET
import sumo_rl
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import EvalCallback, BaseCallback
from stable_baselines3.common.monitor import Monitor
from ee_paths import EE

NET, ROU = EE("donmills_final.net.xml"), EE("am_peak.rou.xml")
STEPS = 50_000
BEST_DIR = EE("best_am_pp")
EVAL_SEEDS = [1, 2, 3, 4, 5]

def make_env(**extra):
    return sumo_rl.SumoEnvironment(
        net_file=NET, route_file=ROU, single_agent=True, use_gui=False,
        num_seconds=3600, delta_time=5, yellow_time=3, min_green=5, max_green=40,
        reward_fn="diff-waiting-time", **extra)

class EpisodeReward(BaseCallback):
    def __init__(self):
        super().__init__(); self.ep = []; self.cur = 0.0
    def _on_step(self):
        self.cur += float(self.locals["rewards"][0])
        if self.locals["dones"][0]:
            self.ep.append(self.cur); self.cur = 0.0
        return True

train_env = Monitor(make_env())
eval_env = Monitor(make_env())

# n_eval_episodes=4: select the snapshot that is good across realizations,
# not the one that got a single lucky episode.
evalcb = EvalCallback(eval_env, best_model_save_path=BEST_DIR,
                      eval_freq=10_000, n_eval_episodes=4,
                      deterministic=True, verbose=1)

model = DQN("MlpPolicy", train_env,
            learning_rate=1e-3, buffer_size=100_000, learning_starts=2_000,
            batch_size=64, gamma=0.99, exploration_fraction=0.4,
            exploration_final_eps=0.03, train_freq=1,
            target_update_interval=1_000, verbose=1, seed=42)

rewards = EpisodeReward()
print(f"Training {STEPS} steps (seed-randomised episodes, eval over 4 episodes)...")
model.learn(total_timesteps=STEPS, callback=[evalcb, rewards])
model.save(EE("dqn_am_pp_last"))
np.save(EE("dqn_am_pp_rewards.npy"), np.array(rewards.ep))
print(f"\nTrained. {len(rewards.ep)} episodes logged.")

# ---------------- evaluate the BEST snapshot over seeds ----------------
best = DQN.load(EE("best_am_pp/best_model"))

def evaluate(seed):
    trip = EE(f"ampp_rl_s{seed}.xml")
    env = make_env(sumo_seed=seed,
                   additional_sumo_cmd=f"--tripinfo-output {trip} --no-warnings true")
    obs, _ = env.reset()
    done = False
    while not done:
        a, _ = best.predict(obs, deterministic=True)
        obs, r, term, trunc, _ = env.step(int(a))
        done = term or trunc
    end = env.sim_step
    env.close()
    if end < 3500:
        raise RuntimeError(f"seed {seed}: episode ended early at {end}s -- not a valid result")
    tr = ET.parse(trip).findall("tripinfo")
    w = [float(x.get("waitingTime")) for x in tr]
    return sum(w) / len(w), len(w)

print(f"\nEvaluating BEST snapshot over seeds {EVAL_SEEDS}:\n")
runs = []
for s in EVAL_SEEDS:
    w, n = evaluate(s)
    runs.append(w)
    print(f"  seed {s}:  {w:7.2f}s   n={n}")

FIXED_BASELINE, ACTUATED_BASELINE = 23.60, 23.81
m, sd = statistics.mean(runs), statistics.stdev(runs)
print("\n" + "=" * 66)
print("AM PEAK — retrained DQN vs matched baselines (protected-permissive)")
print("=" * 66)
print(f"  fixed-time (Webster) : {FIXED_BASELINE:5.2f}s  sd 0.29")
print(f"  actuated (tuned)     : {ACTUATED_BASELINE:5.2f}s  sd 0.32")
print(f"  RL (retrained, best) : {m:5.2f}s  sd {sd:.2f}")
print(f"\n  RL vs fixed-time : {100*(m-FIXED_BASELINE)/FIXED_BASELINE:+.1f}%")
print(f"  RL vs actuated   : {100*(m-ACTUATED_BASELINE)/ACTUATED_BASELINE:+.1f}%")
collapses = [w for w in runs if w > 2 * min(runs)]
print(f"\n  collapsed seeds: {len(collapses)}/{len(runs)} "
      f"(previous model: 3/8)  range {min(runs):.1f}-{max(runs):.1f}s")
