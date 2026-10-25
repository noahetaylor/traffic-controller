"""Give the actuated baseline a fair shot before comparing anything to it.

The first cut used minDur=[10,6,10,6] and maxDur=green+25, which lets the cycle
stretch to ~183 s -- long enough to hurt. An under-tuned baseline would flatter
the RL agent exactly the way the original 54.24 s fixed-time baseline did, so
sweep the gap-out parameters and keep the best.
"""

import subprocess, statistics, itertools, xml.etree.ElementTree as ET
from ee_paths import EE

NET, ROU = EE("donmills_final.net.xml"), EE("am_peak.rou.xml")
SEEDS = [1, 2, 3]

root = ET.parse(NET).getroot()
tl0 = root.find("tlLogic")
tlid = tl0.get("id")
greens = [p.get("state") for p in tl0.findall("phase")
          if not any(c in "yY" for c in p.get("state"))]

# Webster splits computed by build_matched_baselines.py
WEBSTER = [21, 12, 26, 12]

def write_actuated(fname, min_dur, max_mult, det_gap):
    add = ET.Element("additional")
    p = ET.SubElement(add, "tlLogic", {"id": tlid, "type": "actuated",
                                       "programID": "ppact", "offset": "0"})
    ET.SubElement(p, "param", {"key": "detector-gap", "value": str(det_gap)})
    ET.SubElement(p, "param", {"key": "show-detectors", "value": "false"})
    for k, st in enumerate(greens):
        ET.SubElement(p, "phase", {
            "duration": str(WEBSTER[k]),
            "minDur": str(min(min_dur, WEBSTER[k])),
            "maxDur": str(int(WEBSTER[k] * max_mult)),
            "state": st})
        ET.SubElement(p, "phase", {"duration": "3",
                                   "state": "".join("y" if c in "Gg" else "r" for c in st)})
    w = ET.SubElement(add, "WAUT", {"id": "w", "refTime": "0", "startProg": "ppact"})
    ET.SubElement(w, "wautSwitch", {"time": "0", "to": "ppact"})
    ET.SubElement(add, "wautJunction", {"wautID": "w", "junctionID": tlid})
    ET.ElementTree(add).write(fname, encoding="UTF-8", xml_declaration=True)

def run(addfile, seed, tag):
    trip = EE(f"tuneact_{tag}_s{seed}.xml")
    subprocess.run(["sumo", "-n", NET, "-r", ROU, "-a", addfile, "--end", "3600",
                    "--tripinfo-output", trip, "--no-step-log", "true",
                    "--no-warnings", "true", "--seed", str(seed)], check=True)
    tr = ET.parse(trip).findall("tripinfo")
    w = [float(x.get("waitingTime")) for x in tr]
    return sum(w) / len(w), len(w)

print("Actuated parameter sweep (mean waiting time over 3 seeds)\n")
print(f"  {'minDur':>7} {'maxMult':>8} {'detGap':>7} {'mean wait':>10} {'sd':>7} {'mean n':>8}")

best = None
tmp = EE("ctrl_pp_act_tune.add.xml")
for min_dur, max_mult, det_gap in itertools.product([5, 10], [1.25, 1.5, 2.0], [2.0, 3.0]):
    write_actuated(tmp, min_dur, max_mult, det_gap)
    tag = f"{min_dur}_{max_mult}_{det_gap}"
    runs = [run(tmp, s, tag) for s in SEEDS]
    ws = [w for w, _ in runs]
    m, sd = statistics.mean(ws), statistics.stdev(ws)
    n = statistics.mean([n for _, n in runs])
    print(f"  {min_dur:>7} {max_mult:>8} {det_gap:>7} {m:9.2f}s {sd:6.2f}s {n:8.0f}")
    if best is None or m < best[0]:
        best = (m, sd, n, min_dur, max_mult, det_gap)

m, sd, n, min_dur, max_mult, det_gap = best
print(f"\nBEST: minDur={min_dur} maxMult={max_mult} detectorGap={det_gap}"
      f"  ->  {m:.2f}s (sd {sd:.2f}, n {n:.0f})")
write_actuated(EE("ctrl_pp_act.add.xml"), min_dur, max_mult, det_gap)
print(f"Rewrote {EE('ctrl_pp_act.add.xml')} with the best parameters.")
print(f"\nFor reference: fixed-time (Webster) = 23.60s sd 0.29")
