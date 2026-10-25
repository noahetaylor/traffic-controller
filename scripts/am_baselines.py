import pandas as pd, subprocess, xml.etree.ElementTree as ET
from ee_paths import EE

# ---- 1. read the AM peak hour (08:00) and get per-movement vehicle counts ----
df = pd.read_csv(EE("don_mills_lawrence_raw.csv"))
df["start_time"] = pd.to_datetime(df["start_time"])
df = df[df["start_time"].dt.hour == 8]
modes = ["cars","truck","bus"]
def mv(appr, m):   # total across modes for one approach+movement over the hour
    return int(df[[f"{appr}_appr_{mode}_{m}" for mode in modes]].to_numpy().sum())

# map: approach leg -> (in_edge, {movement: out_edge})
geo = {
 "n": ("N_in", {"l":"E_out","t":"S_out","r":"W_out"}),   # from north: left->E, thru->S, right->W
 "s": ("S_in", {"l":"W_out","t":"N_out","r":"E_out"}),
 "e": ("E_in", {"l":"S_out","t":"W_out","r":"N_out"}),
 "w": ("W_in", {"l":"N_out","t":"E_out","r":"S_out"}),
}

routes = ET.Element("routes")
for leg,(ine,outs) in geo.items():
    for m,oute in outs.items():
        count = mv(leg,m)
        if count <= 0: continue
        rid = f"{leg}_{m}"
        ET.SubElement(routes,"route",{"id":rid,"edges":f"{ine} {oute}"})
        ET.SubElement(routes,"flow",{
            "id":f"f_{rid}","route":rid,"begin":"0","end":"3600",
            "vehsPerHour":str(count),"departLane":"best","departSpeed":"max"})
ET.ElementTree(routes).write(EE("am_peak.rou.xml"), encoding="UTF-8", xml_declaration=True)
tot = sum(mv(l,m) for l,(i,o) in geo.items() for m in o)
print(f"Wrote am_peak.rou.xml  |  {tot} vehicles/hour total")

# ---- 2. build an actuated program for THIS net (reuse the working WAUT method) ----
root = ET.parse(EE("donmills_laned.net.xml")).getroot()
add = ET.Element("additional")
for tl in root.findall("tlLogic"):
    new = ET.SubElement(add,"tlLogic",{"id":tl.get("id"),"type":"actuated",
              "programID":"act","offset":tl.get("offset","0")})
    for ph in tl.findall("phase"):
        st=ph.get("state"); d=float(ph.get("duration"))
        g=any(c in "Gg" for c in st); y=any(c in "yY" for c in st)
        mn,mx=(d,d) if (y or not g) else (min(5.0,d),d+25.0)
        ET.SubElement(new,"phase",{"duration":str(int(d)),"minDur":str(int(mn)),
                                   "maxDur":str(int(mx)),"state":st})
    sw=ET.SubElement(add,"WAUT",{"id":f"w_{tl.get('id')}","refTime":"0","startProg":"act"})
    ET.SubElement(sw,"wautSwitch",{"time":"0","to":"act"})
    ET.SubElement(add,"wautJunction",{"wautID":f"w_{tl.get('id')}","junctionID":tl.get("id")})
ET.ElementTree(add).write(EE("act_laned.add.xml"), encoding="UTF-8", xml_declaration=True)

# ---- 3. run fixed-time and actuated on the real AM demand ----
def avg_wait(f):
    t=ET.parse(f).findall("tripinfo")
    w=[float(x.get("waitingTime")) for x in t]; return (sum(w)/len(w) if w else 0.0, len(w))

subprocess.run(["sumo","-n",EE("donmills_laned.net.xml"),"-r",EE("am_peak.rou.xml"),"--end","3600",
    "--tripinfo-output",EE("am_fixed.xml"),"--no-step-log","true","--no-warnings","true"],check=True)
fa,fn=avg_wait(EE("am_fixed.xml"))
subprocess.run(["sumo","-n",EE("donmills_laned.net.xml"),"-r",EE("am_peak.rou.xml"),"-a",EE("act_laned.add.xml"),
    "--end","3600","--tripinfo-output",EE("am_act.xml"),"--no-step-log","true","--no-warnings","true"],check=True)
aa,an=avg_wait(EE("am_act.xml"))

print("\n===== AM PEAK — real Don Mills & Lawrence demand =====")
print(f"Fixed-time : {fa:6.2f} s  (n={fn})")
print(f"Actuated   : {aa:6.2f} s  (n={an})   {100*(aa-fa)/fa:+.1f}% vs fixed")
