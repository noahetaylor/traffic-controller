import xml.etree.ElementTree as ET, subprocess
from ee_paths import EE

# show the fixed-time program SUMO is using
root = ET.parse(EE("donmills_laned.net.xml")).getroot()
for tl in root.findall("tlLogic"):
    print(f"Fixed program '{tl.get('programID')}' type={tl.get('type')}  cycle:")
    cyc=0
    for ph in tl.findall("phase"):
        d=int(float(ph.get("duration"))); cyc+=d
        print(f"   {d:3d}s  {ph.get('state')}")
    print(f"   total cycle = {cyc}s")

# rerun fixed-time with full statistics to see teleports / backlog
print("\n--- SUMO run stats (fixed-time) ---")
subprocess.run(["sumo","-n",EE("donmills_laned.net.xml"),"-r",EE("am_peak.rou.xml"),"--end","3600",
    "--duration-log.statistics","true","--tripinfo-output",EE("am_fixed2.xml"),
    "--no-step-log","true"],check=True)
