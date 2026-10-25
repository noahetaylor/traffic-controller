"""Definitive matched re-run of every AM controller on the CURRENT net + demand.

Motivation: the three published AM numbers were produced by three different
scripts at three different times, and an audit shows they did not all drive the
same signal program. Left-turn treatment (permissive 'g' vs protected-only 'G')
changes fixed-time delay by up to 24% on its own, so a mixed comparison is not
apples-to-apples.

Every configuration below uses the same net, same demand file, same 3600 s
window, same waitingTime metric. The only thing that varies is the controller
and its signal program.
"""

import subprocess, xml.etree.ElementTree as ET
from ee_paths import EE

NET, ROU = EE("donmills_final.net.xml"), EE("am_peak.rou.xml")

lefts = [int(c.get("linkIndex")) for c in ET.parse(NET).getroot().findall("connection")
         if c.get("tl") is not None and c.get("dir") == "l"]

def left_kind(tl):
    for ph in tl.findall("phase"):
        st = ph.get("state")
        if any(c in "yY" for c in st):
            continue
        if any(st[i] == "g" for i in lefts):
            return "permissive"
    return "protected"

def stats(trip):
    tr = ET.parse(trip).findall("tripinfo")
    w = [float(x.get("waitingTime")) for x in tr]
    tl_ = [float(x.get("timeLoss")) for x in tr]
    return sum(w)/len(w), sum(tl_)/len(tl_), len(w)

def run_sumo(tag, addfile):
    trip = EE(f"mx_{tag}.xml")
    cmd = ["sumo", "-n", NET, "-r", ROU, "--end", "3600", "--tripinfo-output", trip,
           "--no-step-log", "true", "--no-warnings", "true"]
    if addfile:
        cmd += ["-a", addfile]
    subprocess.run(cmd, check=True)
    return stats(trip)

CONFIGS = [
    # tag,          add-file,                  controller label
    ("fix_perm",  EE("ctrl_fixed.add.xml"), "fixed-time",  "Webster, permissive lefts"),
    ("fix_prot",  EE("ctrl_prot.add.xml"),  "fixed-time",  "Webster, PROTECTED lefts"),
    ("fix_net0",  None,                     "fixed-time",  "net built-in program 0"),
    ("act_perm",  EE("ctrl_act.add.xml"),   "actuated",    "Webster, permissive lefts"),
    ("act_prot",  EE("ctrl_actp.add.xml"),  "actuated",    "4-phase, PROTECTED lefts"),
]

rows = []
print("Running fixed-time and actuated configurations...\n")
for tag, addf, ctrl, desc in CONFIGS:
    kind = "permissive" if addf is None else left_kind(ET.parse(addf).getroot().find("tlLogic"))
    if addf is None:
        kind = left_kind(ET.parse(NET).getroot().find("tlLogic"))
    w, tl_, n = run_sumo(tag, addf)
    rows.append((ctrl, desc, kind, w, tl_, n))
    print(f"  {ctrl:<11} {desc:<28} {kind:<11} {w:7.2f}s  n={n}")

# ---- RL: evaluate the saved AM model. sumo-rl is given no additional-file, so
#      it drives the net's built-in program 0 -- the permissive one. ----
print("\nEvaluating trained DQN (dqn_donmills_am)...")
import sumo_rl
from stable_baselines3 import DQN

trip_rl = EE("mx_rl_net0.xml")
env = sumo_rl.SumoEnvironment(net_file=NET, route_file=ROU, single_agent=True, use_gui=False,
                              num_seconds=3600, delta_time=5, yellow_time=3,
                              min_green=5, max_green=40, reward_fn="diff-waiting-time",
                              additional_sumo_cmd=f"--tripinfo-output {trip_rl} --no-warnings true")
model = DQN.load(EE("dqn_donmills_am"))
obs, _ = env.reset()
done = False
while not done:
    a, _ = model.predict(obs, deterministic=True)
    obs, r, term, trunc, _ = env.step(int(a))
    done = term or trunc
env.close()
w, tl_, n = stats(trip_rl)
rows.append(("RL (DQN)", "net program 0 (what it trained on)", "permissive", w, tl_, n))
print(f"  {'RL (DQN)':<11} {'net program 0':<28} {'permissive':<11} {w:7.2f}s  n={n}")

# ---------------- report ----------------
print("\n" + "=" * 82)
print("AM PEAK — ALL CONTROLLERS, SAME NET / DEMAND / WINDOW / METRIC")
print("=" * 82)
print(f"{'controller':<12} {'program':<30} {'lefts':<11} {'wait':>8} {'timeLoss':>9} {'n':>6}")
for ctrl, desc, kind, w, tl_, n in rows:
    print(f"{ctrl:<12} {desc:<30} {kind:<11} {w:7.2f}s {tl_:8.2f}s {n:6d}")

rl = [r for r in rows if r[0].startswith("RL")][0]
def get(tag_desc):
    return [r for r in rows if r[1] == tag_desc][0]

print("\n" + "=" * 82)
print("LIKE-FOR-LIKE: every controller on the PERMISSIVE structure the RL agent uses")
print("=" * 82)
fp = get("net built-in program 0")
ap = get("Webster, permissive lefts")     # actuated permissive (first match is fixed; fix below)
ap = [r for r in rows if r[0] == "actuated" and r[2] == "permissive"][0]
print(f"  fixed-time (net prog 0) : {fp[3]:7.2f}s")
print(f"  actuated  (permissive)  : {ap[3]:7.2f}s")
print(f"  RL (DQN)                : {rl[3]:7.2f}s")
print(f"\n  RL vs fixed    : {100*(rl[3]-fp[3])/fp[3]:+.1f}%")
print(f"  RL vs actuated : {100*(rl[3]-ap[3])/ap[3]:+.1f}%")

print("\n" + "=" * 82)
print("WHAT THE PUBLISHED HEADLINE COMPARED")
print("=" * 82)
fpub = get("Webster, permissive lefts")
apub = get("4-phase, PROTECTED lefts")
print(f"  published fixed-time 54.24s  <- reproduced here as {fpub[3]:.2f}s ({fpub[2]} lefts)")
print(f"  published actuated   53.45s  <- reproduced here as {apub[3]:.2f}s ({apub[2]} lefts)")
print(f"  published RL         37.69s  <- reproduced here as {rl[3]:.2f}s ({rl[2]} lefts)")
print("\n  The two baselines did not use the same left-turn treatment as each other,")
print("  and the actuated baseline was handicapped relative to the RL agent.")
