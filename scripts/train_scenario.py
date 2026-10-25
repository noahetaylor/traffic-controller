"""Train and evaluate a DQN for one hour's demand, against matched baselines.

    python train_scenario.py 13
    python train_scenario.py 17

Run build_scenario.py <hour> first -- this expects demand_{hh}.rou.xml and the
two ctrl_pp_*_{hh}.add.xml programs to exist.

Design notes carried over from the AM run:
  * EvalCallback with n_eval_episodes=4, NOT 1. Selecting on a single episode
    picks whichever snapshot drew a lucky realization; the AM agent's selection
    metric was -288.61 +/- 115.54 early on, so with n=1 the callback is choosing
    close to at random. Raising it to 4 removed all seed collapses (0/5, was 3/8).
  * The reported policy is always the BEST snapshot, never the last weights.
  * Baselines are re-evaluated here rather than hardcoded, so a stale number
    cannot leak into the comparison.
"""

import sys, statistics, numpy as np, xml.etree.ElementTree as ET
import sumo_rl
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import EvalCallback, BaseCallback
from stable_baselines3.common.monitor import Monitor
from ee_paths import EE
import scenario_lib as S

hour = int(sys.argv[1]) if len(sys.argv) > 1 else 13
hh = f"{hour:02d}"
STEPS = 50_000
# Optional 2nd arg: evaluation interval. DQN peaks early and then degrades badly
# here, so a coarse interval can miss the good snapshot entirely -- the 17:00 run
# sampled only 5 points and kept one that a midday-trained agent beats on 17:00
# demand (19.39 s vs 9.89 s). Finer sampling costs evaluation time, not training.
EVAL_FREQ = int(sys.argv[2]) if len(sys.argv) > 2 else 10_000
SUFFIX = "" if EVAL_FREQ == 10_000 else f"_e{EVAL_FREQ//1000}k"
BEST_DIR = EE(f"best_pp_{hh}{SUFFIX}")

ROU = EE(f"demand_{hh}.rou.xml")
FIX = EE(f"ctrl_pp_fixed_{hh}.add.xml")
ACT = EE(f"ctrl_pp_act_{hh}.add.xml")

demand = S.hour_demand(hour)
total = sum(demand.values())
print(f"===== SCENARIO {hh}:00 — {total} veh/hr =====", flush=True)

def make_env(**extra):
    return sumo_rl.SumoEnvironment(
        net_file=S.NET, route_file=ROU, single_agent=True, use_gui=False,
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

evalcb = EvalCallback(Monitor(make_env()), best_model_save_path=BEST_DIR,
                      eval_freq=EVAL_FREQ, n_eval_episodes=4,
                      deterministic=True, verbose=1)
model = DQN("MlpPolicy", Monitor(make_env()),
            learning_rate=1e-3, buffer_size=100_000, learning_starts=2_000,
            batch_size=64, gamma=0.99, exploration_fraction=0.4,
            exploration_final_eps=0.03, train_freq=1,
            target_update_interval=1_000, verbose=1, seed=42)

rewards = EpisodeReward()
print(f"Training {STEPS} steps on {hh}:00 demand...", flush=True)
model.learn(total_timesteps=STEPS, callback=[evalcb, rewards])
model.save(EE(f"dqn_pp_{hh}_last"))
np.save(EE(f"dqn_pp_{hh}_rewards.npy"), np.array(rewards.ep))
print(f"Trained. {len(rewards.ep)} episodes logged.", flush=True)

# ---------------- evaluate BEST snapshot over seeds ----------------
best = DQN.load(EE(f"best_pp_{hh}{SUFFIX}/best_model"))

def eval_rl(seed):
    trip = EE(f"sc_rl{hh}_s{seed}.xml")
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
        raise RuntimeError(f"seed {seed}: episode ended at {end}s -- not a valid result")
    return S.avg_wait(trip)

print(f"\nEvaluating over seeds {S.SEEDS} (baselines re-run fresh)...\n", flush=True)
rl_runs = [eval_rl(s) for s in S.SEEDS]
fix_runs = [S.run_sumo(ROU, FIX, s, f"fix{hh}") for s in S.SEEDS]
act_runs = [S.run_sumo(ROU, ACT, s, f"act{hh}") for s in S.SEEDS]

rl_m, rl_sd, rl_n = S.summarise(rl_runs)
f_m, f_sd, f_n = S.summarise(fix_runs)
a_m, a_sd, a_n = S.summarise(act_runs)

print("=" * 72)
print(f"{hh}:00 THREE-WAY ({total} veh/hr, protected-permissive, 5 seeds)")
print("=" * 72)
print(f"  {'controller':<24} {'mean':>8} {'sd':>7} {'mean n':>8}")
print(f"  {'fixed-time (Webster)':<24} {f_m:7.2f}s {f_sd:6.2f}s {f_n:8.0f}")
print(f"  {'actuated (tuned)':<24} {a_m:7.2f}s {a_sd:6.2f}s {a_n:8.0f}")
print(f"  {'RL (DQN, best snapshot)':<24} {rl_m:7.2f}s {rl_sd:6.2f}s {rl_n:8.0f}")
print(f"\n  actuated vs fixed : {100*(a_m-f_m)/f_m:+.1f}%")
print(f"  RL vs fixed       : {100*(rl_m-f_m)/f_m:+.1f}%")
print(f"  RL vs actuated    : {100*(rl_m-a_m)/a_m:+.1f}%")
collapses = sum(1 for w, _ in rl_runs if w > 2 * min(w2 for w2, _ in rl_runs))
print(f"\n  RL seed range {min(w for w,_ in rl_runs):.1f}-{max(w for w,_ in rl_runs):.1f}s, "
      f"collapsed seeds {collapses}/{len(rl_runs)}")
print(f"\n  AM reference (08:00, 4879 veh/hr, Y=0.739, both baselines swept):")
print(f"    fixed 20.18s | actuated 21.97s | RL 28.57s  -> RL +41.6% vs fixed (loses)")
