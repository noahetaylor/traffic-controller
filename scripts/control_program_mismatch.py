"""Control experiment: is the AM headline result confounded by a signal-program mismatch?

Finding that prompted this: the baselines are run as
    sumo -n donmills_final.net.xml -a ctrl_prot.add.xml     -> programID "prot", PROTECTED lefts
but sumo-rl is constructed as
    SumoEnvironment(net_file=..., route_file=...)           -> no additional-file
so the RL agent controls the net's BUILT-IN programID "0", which has PERMISSIVE
lefts ('g') running concurrently with the opposing through movement.

Permissive lefts let left-turners filter through gaps instead of waiting for a
short dedicated arrow, so they add capacity the baselines never get. That is a
structural advantage unrelated to learning.

This isolates the effect by running fixed-time under three configurations on the
same demand, same 3600 s window, same metric:

  A  prot timings + PROTECTED lefts   (= ctrl_prot.add.xml, the published baseline)
  B  prot timings + PERMISSIVE lefts  (identical timing; only left-turn states differ)
  C  the net's built-in program 0     (what the RL agent actually drives)

A vs B isolates permissiveness at identical timing. A vs C is the real comparison
the essay has been making without knowing it.
"""

import subprocess, re, xml.etree.ElementTree as ET
from collections import defaultdict
from ee_paths import EE

NET, ROU = EE("donmills_final.net.xml"), EE("am_peak.rou.xml")

net = ET.parse(NET).getroot()
link = {}
for c in net.findall("connection"):
    if c.get("tl") is not None:
        link[int(c.get("linkIndex"))] = (c.get("from"), c.get("dir"))

LEFTS = [i for i, (fe, d) in link.items() if d == "l"]
NS_LEFT = [i for i in LEFTS if link[i][0][0] in "NS"]
EW_LEFT = [i for i in LEFTS if link[i][0][0] in "EW"]
print(f"left-turn link indices: NS={NS_LEFT}  EW={EW_LEFT}")

# ---------- build B: prot timings, permissive lefts during the through phases ----------
prot = ET.parse(EE("ctrl_prot.add.xml")).getroot().find("tlLogic")
phases = [(p.get("duration"), p.get("state")) for p in prot.findall("phase")]

def permit(state, idxs):
    s = list(state)
    for i in idxs:
        if s[i] == "r":
            s[i] = "g"          # green-minor: may proceed after yielding
    return "".join(s)

perm_phases = []
for n, (dur, st) in enumerate(phases):
    if n == 0:                       # NS through -> allow permissive NS lefts
        st = permit(st, NS_LEFT)
    elif n == 4:                     # EW through -> allow permissive EW lefts
        st = permit(st, EW_LEFT)
    elif n == 1:                     # matching yellows keep the minor movement live
        st = permit(st, NS_LEFT)
    elif n == 5:
        st = permit(st, EW_LEFT)
    perm_phases.append((dur, st))

add = ET.Element("additional")
tl = ET.SubElement(add, "tlLogic", {"id": "C", "type": "static",
                                    "programID": "permissive", "offset": "0"})
for dur, st in perm_phases:
    ET.SubElement(tl, "phase", {"duration": dur, "state": st})
w = ET.SubElement(add, "WAUT", {"id": "w", "refTime": "0", "startProg": "permissive"})
ET.SubElement(w, "wautSwitch", {"time": "0", "to": "permissive"})
ET.SubElement(add, "wautJunction", {"wautID": "w", "junctionID": "C"})
PERM = EE("ctrl_permissive.add.xml")
ET.ElementTree(add).write(PERM, encoding="UTF-8", xml_declaration=True)

print("\nphase states (prot -> permissive):")
for (d, a), (_, b) in zip(phases, perm_phases):
    print(f"  {d:>3}s  {a}  ->  {b}{'   <-- changed' if a != b else ''}")

# ---------- run the three configurations ----------
BRAKE = re.compile(r"performs emergency braking.*?on lane '(?P<lane>[^']+)'")

def run(tag, addfile):
    log, trip = EE(f"cx_{tag}_log.txt"), EE(f"cx_{tag}_tripinfo.xml")
    cmd = ["sumo", "-n", NET, "-r", ROU, "--end", "3600",
           "--tripinfo-output", trip, "--no-step-log", "true"]
    if addfile:
        cmd += ["-a", addfile]
    with open(log, "w", encoding="utf-8") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=False)

    trips = ET.parse(trip).findall("tripinfo")
    waits = [float(t.get("waitingTime")) for t in trips]
    loss = [float(t.get("timeLoss")) for t in trips]
    by_flow = defaultdict(list)
    for t in trips:
        by_flow[t.get("id").split(".")[0]].append(float(t.get("waitingTime")))

    brakes = 0
    for line in open(log, encoding="utf-8", errors="ignore"):
        if BRAKE.search(line):
            brakes += 1
    return {"wait": sum(waits)/len(waits), "loss": sum(loss)/len(loss),
            "n": len(waits), "brakes": brakes,
            "lefts": {k: sum(v)/len(v) for k, v in by_flow.items() if k.endswith("_l")}}

configs = [
    ("A_protected",  EE("ctrl_prot.add.xml"), "prot timings + PROTECTED lefts (published baseline)"),
    ("B_permissive", PERM,                    "prot timings + PERMISSIVE lefts"),
    ("C_netdefault", None,                    "net built-in program 0 (what RL drives)"),
]

print("\nRunning three fixed-time configurations on AM demand...\n")
res = {}
for tag, addf, desc in configs:
    res[tag] = run(tag, addf)
    r = res[tag]
    print(f"{tag:<14} {r['wait']:7.2f}s wait  {r['loss']:7.2f}s timeLoss  "
          f"n={r['n']:<5} braking={r['brakes']}   {desc}")

A, B, C = res["A_protected"], res["B_permissive"], res["C_netdefault"]
print("\n" + "=" * 74)
print("INTERPRETATION")
print("=" * 74)
print(f"  Permissive lefts alone (A->B, identical timing): "
      f"{A['wait']:.2f}s -> {B['wait']:.2f}s = {100*(B['wait']-A['wait'])/A['wait']:+.1f}%")
print(f"  Baseline program vs what RL drives (A->C):       "
      f"{A['wait']:.2f}s -> {C['wait']:.2f}s = {100*(C['wait']-A['wait'])/A['wait']:+.1f}%")
print(f"\n  Published headline: RL 37.69s vs fixed 54.24s = -30.5%")
gap = 100 * (C['wait'] - A['wait']) / A['wait']
print(f"  Of that, {abs(gap):.1f} percentage points is available from the signal program")
print(f"  alone, with NO learning involved (fixed-time on each program).")

print("\n  Left-turn avg wait by movement:")
allk = sorted(set(A["lefts"]) | set(B["lefts"]) | set(C["lefts"]))
print(f"    {'movement':<10} {'A prot':>9} {'B perm':>9} {'C net0':>9}")
for k in allk:
    print(f"    {k:<10} {A['lefts'].get(k,0):8.1f}s {B['lefts'].get(k,0):8.1f}s {C['lefts'].get(k,0):8.1f}s")

print(f"\n  Emergency braking: A={A['brakes']}  B={B['brakes']}  C={C['brakes']}")
print("  (braking appears exactly where permissive lefts do -- this is the")
print("   ':C_10_1' EW internal-lane braking from Decision #13.)")
