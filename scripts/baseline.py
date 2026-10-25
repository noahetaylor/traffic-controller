import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
from ee_paths import EE, SUMO_RL_REPO

base = SUMO_RL_REPO
net = next(base.rglob("single-intersection.net.xml"))
# prefer the hand-authored route over the long generated "-gen" one
routes = sorted(net.parent.glob("*.rou.xml"), key=lambda p: ("-gen" in p.name, p.name))
route = routes[0]
print("Net:  ", net)
print("Route:", route)

trip = EE("baseline_fixed_tripinfo.xml")
subprocess.run([
    "sumo",
    "-n", str(net),
    "-r", str(route),
    "--end", "3600",                       # <-- bound the run to 1 hour
    "--tripinfo-output", trip,
    "--duration-log.statistics", "true",   # SUMO prints its own averages
    "--no-step-log", "true",
    "--no-warnings", "true",
], check=True)

tree = ET.parse(trip)
trips = tree.findall("tripinfo")
waits = [float(t.get("waitingTime")) for t in trips]
avg = sum(waits) / len(waits) if waits else 0.0
print(f"\nVehicles completed: {len(waits)}")
print(f"Average waiting time (fixed-time baseline): {avg:.2f} s")
