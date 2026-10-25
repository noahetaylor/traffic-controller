"""Build fixed-time and actuated baselines on the SAME structure the RL agent drives.

sumo-rl reads getAllProgramLogics(id)[0] -- the net's built-in programID "0" -- and
ignores any additional-file program, so the RL agent always drives program 0's phase
STATES (protected-permissive: dedicated left arrows plus permissive filtering during
the through phase). It supplies its own timing, so program 0's durations never matter
to it.

To make the comparison apples-to-apples we therefore hold the phase STATES fixed at
program 0's, and give the baselines Webster-tuned durations on those same states.
Only the controller varies.

Writes ctrl_pp_fixed.add.xml (static) and ctrl_pp_act.add.xml (actuated), then
evaluates both over several seeds.
"""

import subprocess, statistics, xml.etree.ElementTree as ET
import pandas as pd
from ee_paths import EE

NET, ROU = EE("donmills_final.net.xml"), EE("am_peak.rou.xml")
HOUR, SEEDS = 8, [1, 2, 3, 4, 5]

root = ET.parse(NET).getroot()
tl0 = root.find("tlLogic")
tlid = tl0.get("id")

# green phases of program 0, in order, with the movements each serves
greens = [(i, p.get("state")) for i, p in enumerate(tl0.findall("phase"))
          if not any(c in "yY" for c in p.get("state"))]
link = {int(c.get("linkIndex")): (c.get("from"), c.get("dir"))
        for c in root.findall("connection") if c.get("tl") is not None}

# SUMO calls the through movement 's'; the demand table calls it 't'. Keep one naming.
DIRMAP = {"l": "L", "s": "T", "r": "R"}

def served(state):
    """Movements getting a major green ('G') in this phase, as e.g. {'NT','SR'}."""
    out = set()
    for i, ch in enumerate(state):
        if ch == "G" and i in link:
            fe, d = link[i]
            out.add(f"{fe[0]}{DIRMAP[d]}")
    return out

print(f"Program 0 green phases (states held fixed, durations to be Webster-tuned):")
for i, st in greens:
    print(f"  phase {i}: {st}   serves {' '.join(sorted(served(st)))}")

# ---------- demand for this hour, by movement ----------
df = pd.read_csv(EE("don_mills_lawrence_raw.csv"))
df["start_time"] = pd.to_datetime(df["start_time"])
df = df[df["start_time"].dt.hour == HOUR]
modes = ["cars", "truck", "bus"]

def mv(leg, m):
    return int(df[[f"{leg}_appr_{md}_{m}" for md in modes]].to_numpy().sum())

demand = {f"{leg.upper()}{m.upper()}": mv(leg, m)
          for leg in "nsew" for m in "ltr"}
print(f"\nAM demand by movement: {demand}   total {sum(demand.values())} veh/hr")

# through lanes per approach (from the net), used as the saturation multiplier
lanes_for = {}
for i, (fe, d) in link.items():
    if d == "s":
        lanes_for[fe[0]] = lanes_for.get(fe[0], 0) + 1

SAT = 1800.0
def flow_ratio(state):
    """Critical flow ratio y for the phase: worst approach it serves."""
    y = 0.0
    for movement in served(state):
        leg, m = movement[0], movement[1]
        vol = demand.get(movement, 0)
        cap = SAT * (lanes_for.get(leg, 1) if m in "TR" else 1)
        y = max(y, vol / cap)
    return y

ys = [flow_ratio(st) for _, st in greens]
Y = sum(ys)
L = 4 * 3          # 4 yellow intervals of 3 s
C = int(min(120, max(60, (1.5 * L + 5) / max(0.15, 1 - Y))))
budget = C - L
MINS = [10, 6, 10, 6]
g = [max(MINS[k], round(budget * ys[k] / Y)) for k in range(len(greens))]

# Rounding and the per-phase minimums can leave the splits not summing to the
# budget. Settle the difference on the phase with the largest flow ratio, and
# never let a green fall below its minimum.
slack = budget - sum(g)
if slack:
    order = sorted(range(len(g)), key=lambda k: ys[k], reverse=True)
    for k in order:
        take = max(MINS[k] - g[k], slack) if slack < 0 else slack
        g[k] += take
        slack -= take
        if slack == 0:
            break
assert all(g[k] >= MINS[k] for k in range(len(g))), f"green below minimum: {g}"
assert sum(g) + L == C, f"splits {g} + lost time {L} != cycle {C}"
print(f"\nWebster: Y={Y:.3f}  cycle={C}s  greens={g}  (yellows 4x3s)")
print("  per-phase flow ratios: " + "  ".join(f"{y:.3f}" for y in ys))

def write_program(fname, prog_id, ptype, actuated):
    add = ET.Element("additional")
    p = ET.SubElement(add, "tlLogic",
                      {"id": tlid, "type": ptype, "programID": prog_id, "offset": "0"})
    for k, (idx, st) in enumerate(greens):
        a = {"duration": str(int(g[k])), "state": st}
        if actuated:
            a.update({"minDur": str(MINS[k]), "maxDur": str(int(g[k]) + 25)})
        ET.SubElement(p, "phase", a)
        yellow = "".join("y" if ch in "Gg" else "r" for ch in st)
        ET.SubElement(p, "phase", {"duration": "3", "state": yellow})
    w = ET.SubElement(add, "WAUT", {"id": "w", "refTime": "0", "startProg": prog_id})
    ET.SubElement(w, "wautSwitch", {"time": "0", "to": prog_id})
    ET.SubElement(add, "wautJunction", {"wautID": "w", "junctionID": tlid})
    ET.ElementTree(add).write(fname, encoding="UTF-8", xml_declaration=True)
    return fname

FIX = write_program(EE("ctrl_pp_fixed.add.xml"), "ppfix", "static", False)
ACT = write_program(EE("ctrl_pp_act.add.xml"), "ppact", "actuated", True)
print(f"wrote {FIX}\nwrote {ACT}")

# ---------- evaluate both over seeds ----------
def run(tag, addfile, seed):
    trip = EE(f"pp_{tag}_s{seed}.xml")
    subprocess.run(["sumo", "-n", NET, "-r", ROU, "-a", addfile, "--end", "3600",
                    "--tripinfo-output", trip, "--no-step-log", "true",
                    "--no-warnings", "true", "--seed", str(seed)], check=True)
    tr = ET.parse(trip).findall("tripinfo")
    w = [float(x.get("waitingTime")) for x in tr]
    return sum(w) / len(w), len(w)

print(f"\nEvaluating over seeds {SEEDS}:\n")
out = {}
for tag, addf, label in [("fix", FIX, "fixed-time (Webster, prot-perm)"),
                         ("act", ACT, "actuated (prot-perm)")]:
    runs = [run(tag, addf, s) for s in SEEDS]
    ws = [w for w, _ in runs]
    out[label] = (statistics.mean(ws), statistics.stdev(ws),
                  statistics.mean([n for _, n in runs]))
    print(f"  {label:<32} " + "  ".join(f"{w:6.2f}s" for w in ws))

print("\n" + "=" * 70)
print(f"{'controller':<34} {'mean':>8} {'sd':>7} {'mean n':>8}")
for label, (m, sd, n) in out.items():
    print(f"{label:<34} {m:7.2f}s {sd:6.2f}s {n:8.0f}")
print("\nThese are the baselines the retrained agent will be measured against.")
