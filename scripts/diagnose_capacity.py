import subprocess, xml.etree.ElementTree as ET
from collections import Counter
from ee_paths import EE

# run the best fixed plan (90s) with more diagnostics
subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),
    "-a",EE("ctrl_fixed.add.xml"),"--end","3600","--tripinfo-output",EE("t.xml"),
    "--summary-output",EE("sum.xml"),"--duration-log.statistics","true",
    "--no-step-log","true"],check=False)

# how many of each route (leg_movement) actually completed?
trips=ET.parse(EE("t.xml")).findall("tripinfo")
done=Counter(t.get("id").split(".")[0].replace("f_","") for t in trips)
print("Completed vehicles per movement (leg_move):")
for k in sorted(done): print(f"   {k}: {done[k]}")

# waiting time by movement — which movement is suffering most?
wt=Counter(); ct=Counter()
for t in trips:
    k=t.get("id").split(".")[0].replace("f_","")
    wt[k]+=float(t.get("waitingTime")); ct[k]+=1
print("\nAvg wait by movement:")
for k in sorted(ct): print(f"   {k}: {wt[k]/ct[k]:5.1f}s  over {ct[k]}")

# end-of-sim backlog
s=ET.parse(EE("sum.xml")).findall("step")
if s:
    last=s[-1]
    print(f"\nAt sim end: running={last.get('running')}  halting(queued)={last.get('halting')}")
print("\n(l=left, t=through, r=right; n/s/e/w = entering leg)")
