"""Generalization: how well does each controller transfer to an hour it was not tuned for?

The three-way results give fixed-time a bespoke cycle for EACH hour, which no real
intersection gets -- deployments run a handful of time-of-day plans. This asks the
fairer question two ways, without any new training:

  1. RL transfer matrix: evaluate each trained agent on all three demand profiles.
  2. Fixed-plan transfer: run each hour's tuned fixed plan on all three profiles.

The diagonal is the matched (per-hour-tuned) case already reported; the off-diagonal
is what a controller actually does when demand is not what it was tuned for.
"""

import statistics, xml.etree.ElementTree as ET
import sumo_rl
from stable_baselines3 import DQN
from ee_paths import EE
import scenario_lib as S

HOURS = [8, 13, 17]
MODEL_OF = {8: "best_am_pp/best_model", 13: "best_pp_13/best_model", 17: "best_pp_17/best_model"}
LABEL = {8: "08:00 AM", 13: "13:00 mid", 17: "17:00 PM"}
SEEDS = [1, 2, 3, 4, 5]


def rl_on(model, hour, seed):
    hh = f"{hour:02d}"
    trip = EE(f"xe_rl_s{seed}_{hh}.xml")
    env = sumo_rl.SumoEnvironment(
        net_file=S.NET, route_file=EE(f"demand_{hh}.rou.xml"), single_agent=True,
        use_gui=False, num_seconds=3600, delta_time=5, yellow_time=3,
        min_green=5, max_green=40, reward_fn="diff-waiting-time", sumo_seed=seed,
        additional_sumo_cmd=f"--tripinfo-output {trip} --no-warnings true")
    obs, _ = env.reset()
    done = False
    while not done:
        a, _ = model.predict(obs, deterministic=True)
        obs, r, term, trunc, _ = env.step(int(a))
        done = term or trunc
    end = env.sim_step
    env.close()
    if end < 3500:
        raise RuntimeError(f"episode ended early at {end}s")
    return S.avg_wait(trip)


print("Loading trained agents...", flush=True)
models = {h: DQN.load(EE(MODEL_OF[h])) for h in HOURS}

print("\n" + "=" * 78)
print("RL TRANSFER MATRIX — mean waiting time (s) over 5 seeds")
print("  rows = agent trained on, columns = demand evaluated on")
print("=" * 78)
rl = {}
for trained in HOURS:
    for tested in HOURS:
        runs = [rl_on(models[trained], tested, s) for s in SEEDS]
        rl[(trained, tested)] = S.summarise(runs)
        print(f"  agent {LABEL[trained]:<10} on {LABEL[tested]:<10} "
              f"{rl[(trained, tested)][0]:7.2f}s sd {rl[(trained,tested)][1]:5.2f}", flush=True)

print("\n" + "=" * 78)
print("FIXED-PLAN TRANSFER — mean waiting time (s) over 5 seeds")
print("  rows = plan tuned for, columns = demand evaluated on")
print("=" * 78)
fx = {}
for tuned in HOURS:
    plan = EE(f"ctrl_pp_fixed_{tuned:02d}.add.xml")
    for tested in HOURS:
        route = EE(f"demand_{tested:02d}.rou.xml")
        runs = [S.run_sumo(route, plan, s, f"xef_{tuned}_{tested}") for s in SEEDS]
        fx[(tuned, tested)] = S.summarise(runs)
        print(f"  plan  {LABEL[tuned]:<10} on {LABEL[tested]:<10} "
              f"{fx[(tuned, tested)][0]:7.2f}s sd {fx[(tuned,tested)][1]:5.2f}", flush=True)

# ---------------- summary tables ----------------
def matrix(title, data):
    print("\n" + title)
    print(f"  {'':<12}" + "".join(f"{LABEL[t]:>13}" for t in HOURS))
    for r in HOURS:
        print(f"  {LABEL[r]:<12}" + "".join(f"{data[(r,t)][0]:12.2f}s" for t in HOURS))

print("\n" + "=" * 78)
print("SUMMARY")
print("=" * 78)
matrix("RL agent (row) evaluated on demand (column):", rl)
matrix("Fixed plan (row) evaluated on demand (column):", fx)

print("\n  Best single all-day choice (worst-case and average across the three hours):")
for name, data in [("RL agent", rl), ("fixed plan", fx)]:
    for r in HOURS:
        vals = [data[(r, t)][0] for t in HOURS]
        print(f"    {name:<11} tuned for {LABEL[r]:<10} "
              f"avg {statistics.mean(vals):6.2f}s   worst {max(vals):6.2f}s")

print("\n  Matched (diagonal) reference — each controller on its own hour:")
for h in HOURS:
    print(f"    {LABEL[h]:<10} RL {rl[(h,h)][0]:6.2f}s   fixed {fx[(h,h)][0]:6.2f}s")
