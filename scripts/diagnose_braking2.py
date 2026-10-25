import subprocess, os
from collections import Counter

# run with warnings on, capturing stderr where SUMO prints braking/teleport warnings
with open(EE("simerr.txt"),"w",encoding="utf-8") as errf:
    subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),
        "-a",EE("ctrl_prot.add.xml"),"--end","3600","--collision-output",EE("coll.xml"),
        "--tripinfo-output",EE("t.xml"),"--no-step-log","true"],
        stderr=errf, stdout=subprocess.DEVNULL, check=False)

brakes=teleports=collisions=0
lanes=Counter(); vehs=Counter()
for line in open(EE("simerr.txt"),encoding="utf-8",errors="ignore"):
    if "emergency braking" in line:
        brakes+=1
        if "lane '" in line: lanes[line.split("lane '")[1].split("'")[0]]+=1
        if "Vehicle '" in line: vehs[line.split("Vehicle '")[1].split("'")[0].split('.')[0]]+=1
    if "teleport" in line.lower(): teleports+=1
    if "collision" in line.lower(): collisions+=1

# total vehicles for context
import xml.etree.ElementTree as ET
from ee_paths import EE
n=len(ET.parse(EE("t.xml")).findall("tripinfo"))
print(f"Vehicles completed: {n}")
print(f"Emergency-braking events: {brakes}   ({100*brakes/n:.1f}% of vehicles)")
print(f"Teleports: {teleports}   Collisions: {collisions}")
print("\nBraking by lane (top 6):")
for ln,c in lanes.most_common(6): print(f"   {ln}: {c}")
print("\nBraking by movement (top 6):")
for v,c in vehs.most_common(6): print(f"   {v}: {c}")

# check collision file
if os.path.exists(EE("coll.xml")):
    c=ET.parse(EE("coll.xml")).getroot().findall("collision")
    print(f"\nLogged collisions in coll.xml: {len(c)}")
