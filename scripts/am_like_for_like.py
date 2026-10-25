"""AM peak: like-for-like three-way, all controllers on the SAME signal structure.

Why this exists
---------------
The published AM headline (RL 37.69 s vs fixed 54.24 s vs actuated 53.45 s, ~-30%)
compared controllers that were NOT driving the same signal program:

  * sumo-rl is constructed as SumoEnvironment(net_file=..., route_file=...) with no
    additional-file, so the RL agent drives the net's BUILT-IN programID "0", which
    has PERMISSIVE left turns ('g' concurrent with the opposing through movement).
  * the published actuated baseline used ctrl_actp.add.xml -- PROTECTED-only lefts.

Left-turn treatment alone is worth up to ~24% of fixed-time delay on this network,
so the published comparison mixes a controller effect with a signal-structure effect.

This script re-runs fixed-time, actuated and the trained DQN with every controller
on the permissive structure the RL agent actually uses, over several SUMO seeds,
so the comparison is apples-to-apples and not a single-run fluke.
"""

import subprocess, statistics, xml.etree.ElementTree as ET
from ee_paths import EE

NET, ROU = EE("donmills_final.net.xml"), EE("am_peak.rou.xml")
SEEDS = [1, 2, 3]

def wait_of(trip):
    tr = ET.parse(trip).findall("tripinfo")
    w = [float(x.get("waitingTime")) for x in tr]
    return sum(w) / len(w), len(w)

def sumo_run(tag, addfile, seed):
    trip = EE(f"lfl_{tag}_s{seed}.xml")
    cmd = ["sumo", "-n", NET, "-r", ROU, "--end", "3600", "--tripinfo-output", trip,
           "--no-step-log", "true", "--no-warnings", "true", "--seed", str(seed)]
    if addfile:
        cmd += ["-a", addfile]
    subprocess.run(cmd, check=True)
    return wait_of(trip)

def rl_run(seed):
    import sumo_rl
    from stable_baselines3 import DQN
    trip = EE(f"lfl_rl_s{seed}.xml")
    env = sumo_rl.SumoEnvironment(
        net_file=NET, route_file=ROU, single_agent=True, use_gui=False,
        num_seconds=3600, delta_time=5, yellow_time=3, min_green=5, max_green=40,
        reward_fn="diff-waiting-time", sumo_seed=seed,
        additional_sumo_cmd=f"--tripinfo-output {trip}")
    model = DQN.load(EE("dqn_donmills_am"))
    obs, _ = env.reset()
    done = False
    while not done:
        a, _ = model.predict(obs, deterministic=True)
        obs, r, term, trunc, _ = env.step(int(a))
        done = term or trunc
    sim_end = env.sim_step
    env.close()
    w, n = wait_of(trip)
    if sim_end < 3500:                       # guard: a truncated episode is not a result
        raise RuntimeError(f"RL episode ended early at {sim_end}s (seed {seed}) -- discard")
    return w, n

print(f"AM peak, {len(SEEDS)} seeds, all controllers on the PERMISSIVE structure\n")

results = {}
for label, tag, addf in [
    ("fixed-time (net program 0)", "fix", None),
    ("actuated (permissive)",      "act", EE("ctrl_act.add.xml")),
]:
    runs = [sumo_run(tag, addf, s) for s in SEEDS]
    results[label] = runs
    print(f"  {label:<28} " + "  ".join(f"{w:6.2f}s(n={n})" for w, n in runs))

runs = [rl_run(s) for s in SEEDS]
results["RL (DQN)"] = runs
print(f"  {'RL (DQN)':<28} " + "  ".join(f"{w:6.2f}s(n={n})" for w, n in runs))

print("\n" + "=" * 72)
print(f"{'controller':<28} {'mean wait':>10} {'sd':>7} {'mean n':>8}")
print("=" * 72)
summary = {}
for label, runs in results.items():
    ws = [w for w, _ in runs]
    ns = [n for _, n in runs]
    m = statistics.mean(ws)
    sd = statistics.stdev(ws) if len(ws) > 1 else 0.0
    summary[label] = m
    print(f"{label:<28} {m:9.2f}s {sd:6.2f}s {statistics.mean(ns):8.0f}")

fx = summary["fixed-time (net program 0)"]
ac = summary["actuated (permissive)"]
rl = summary["RL (DQN)"]
print("\n" + "=" * 72)
print("LIKE-FOR-LIKE RESULT")
print("=" * 72)
print(f"  RL vs fixed-time : {100*(rl-fx)/fx:+.1f}%")
print(f"  RL vs actuated   : {100*(rl-ac)/ac:+.1f}%")
print(f"\n  Published headline was -30.5% vs fixed and -29.5% vs actuated.")
print(f"  Actuated on the same structure {'BEATS' if ac < rl else 'loses to'} the RL agent.")
