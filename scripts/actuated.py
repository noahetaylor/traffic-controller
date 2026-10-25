import subprocess, xml.etree.ElementTree as ET
from pathlib import Path
from ee_paths import EE, SUMO_RL_REPO

base = SUMO_RL_REPO
net = next(base.rglob("single-intersection.net.xml"))
routes = sorted(net.parent.glob("*.rou.xml"), key=lambda p: ("-gen" in p.name, p.name))
route = routes[0]
print("Net:  ", net)
print("Route:", route)

def avg_wait(f):
    trips = ET.parse(f).findall("tripinfo")
    w = [float(t.get("waitingTime")) for t in trips]
    return (sum(w)/len(w) if w else 0.0), len(w)

# ---- Build an actuated program with a NEW programID, then switch to it ----
root = ET.parse(net).getroot()
tls = root.findall("tlLogic")
if not tls:
    raise SystemExit("No tlLogic found in this net.")

NEWPROG = "act"
add = ET.Element("additional")
for tl in tls:
    new = ET.SubElement(add, "tlLogic", {
        "id": tl.get("id"),
        "type": "actuated",          # gap-based control
        "programID": NEWPROG,        # distinct ID so it does NOT clash with static "0"
        "offset": tl.get("offset", "0"),
    })
    for ph in tl.findall("phase"):
        state = ph.get("state")
        dur = float(ph.get("duration"))
        has_green  = any(c in "Gg" for c in state)
        has_yellow = any(c in "yY" for c in state)
        if has_yellow or not has_green:
            mind = maxd = dur
        else:
            mind = min(5.0, dur)
            maxd = dur + 20.0
        ET.SubElement(new, "phase", {
            "duration": str(int(dur)),
            "minDur": str(int(mind)),
            "maxDur": str(int(maxd)),
            "state": state,
        })
    # activate the new program at t=0 for this traffic light
    ET.SubElement(add, "tlLogic", {}) if False else None

# tell SUMO to switch each TL to the actuated program at time 0
for tl in tls:
    sw = ET.SubElement(add, "WAUT", {"id": f"w_{tl.get('id')}", "refTime": "0", "startProg": NEWPROG})
    ET.SubElement(sw, "wautSwitch", {"time": "0", "to": NEWPROG})
    ET.SubElement(add, "wautJunction", {"wautID": f"w_{tl.get('id')}", "junctionID": tl.get("id")})

ET.ElementTree(add).write(EE("actuated.add.xml"), encoding="UTF-8", xml_declaration=True)
print("Wrote actuated.add.xml")

subprocess.run(["sumo","-n",str(net),"-r",str(route),"--end","3600",
                "--tripinfo-output",EE("fixed_tripinfo.xml"),
                "--no-step-log","true","--no-warnings","true"], check=True)
fix_avg, fix_n = avg_wait(EE("fixed_tripinfo.xml"))

subprocess.run(["sumo","-n",str(net),"-r",str(route),"-a",EE("actuated.add.xml"),"--end","3600",
                "--tripinfo-output",EE("actuated_tripinfo.xml"),
                "--no-step-log","true","--no-warnings","true"], check=True)
act_avg, act_n = avg_wait(EE("actuated_tripinfo.xml"))

rl = 17.70
print("\n===== BASELINES (avg waiting time) =====")
print(f"Fixed-time : {fix_avg:6.2f} s  (n={fix_n})")
print(f"Actuated   : {act_avg:6.2f} s  (n={act_n})   {100*(act_avg-fix_avg)/fix_avg:+.1f}% vs fixed")
print(f"RL (DQN)   : {rl:6.2f} s            {100*(rl-fix_avg)/fix_avg:+.1f}% vs fixed")
