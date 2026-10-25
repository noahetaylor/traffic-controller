import sumolib, subprocess, xml.etree.ElementTree as ET
from collections import Counter

net = sumolib.net.readNet(EE("donmills_final.net.xml"))
node = net.getNode(net.getTrafficLights()[0].getID())

# 1) internal lane geometry — look for very short internal lanes (pile-up risk)
print("=== Internal (junction) lanes ===")
internal = [l for e in net.getEdges(withInternal=True) for l in e.getLanes()
            if l.getEdge().isSpecial()]
short = []
for l in sorted(internal, key=lambda l: l.getLength()):
    tag = ""
    if l.getLength() < 8: tag = "  <-- SHORT"; short.append(l.getID())
    if l.getLength() < 20:
        print(f"  {l.getID():18s} len={l.getLength():5.1f}m{tag}")
print(f"Short internal lanes (<8m): {len(short)}")

# 2) count emergency-braking + collisions with the trained-signal fixed run,
#    and measure how many vehicles are affected
subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),
    "-a",EE("ctrl_prot.add.xml"),"--end","3600","--collision-output",EE("coll.xml"),
    "--emergencydecel.warn-threshold","1.0","--error-log",EE("errlog.txt"),
    "--tripinfo-output",EE("t.xml"),"--no-step-log","true"],check=False)

import os
from ee_paths import EE
brakes = collisions = 0
if os.path.exists(EE("errlog.txt")):
    for line in open(EE("errlog.txt"), encoding="utf-8", errors="ignore"):
        if "emergency braking" in line: brakes += 1
        if "collision" in line.lower(): collisions += 1
print(f"\nEmergency-braking events: {brakes}")
print(f"Collisions: {collisions}")

# which movements are braking? parse lane ids from the log
lanes = Counter()
if os.path.exists(EE("errlog.txt")):
    for line in open(EE("errlog.txt"), encoding="utf-8", errors="ignore"):
        if "emergency braking" in line and "lane '" in line:
            lanes[line.split("lane '")[1].split("'")[0]] += 1
print("Braking by lane (top 6):")
for ln,c in lanes.most_common(6): print(f"   {ln}: {c}")
