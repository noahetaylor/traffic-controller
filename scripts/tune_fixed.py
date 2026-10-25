import pandas as pd, subprocess, xml.etree.ElementTree as ET
from ee_paths import EE

df=pd.read_csv(EE("don_mills_lawrence_raw.csv")); df["start_time"]=pd.to_datetime(df["start_time"])
df=df[df["start_time"].dt.hour==8]; modes=["cars","truck","bus"]
def leg(a): return int(df[[f"{a}_appr_{m}_{mv}" for m in modes for mv in ['l','t','r']]].to_numpy().sum())
ns=leg("n")+leg("s"); ew=leg("e")+leg("w")
frac_ns=ns/(ns+ew)

root=ET.parse(EE("donmills_final.net.xml")).getroot(); tl=root.find("tlLogic")
tlid=tl.get("id"); phases=tl.findall("phase")

def write_fixed(cycle):
    L=16.0; g=cycle-L
    g_ns=int(max(10,round(g*frac_ns))); g_ew=int(max(10,g-g_ns))
    add=ET.Element("additional")
    p=ET.SubElement(add,"tlLogic",{"id":tlid,"type":"static","programID":"fixed","offset":"0"})
    for ph in phases:
        st=ph.get("state"); d=float(ph.get("duration"))
        gr=any(c in "Gg" for c in st); ye=any(c in "yY" for c in st)
        dur = (g_ns if st.rfind("G")>=len(st)//2 else g_ew) if (gr and not ye) else int(d)
        ET.SubElement(p,"phase",{"duration":str(int(dur)),"state":st})
    w=ET.SubElement(add,"WAUT",{"id":"w","refTime":"0","startProg":"fixed"})
    ET.SubElement(w,"wautSwitch",{"time":"0","to":"fixed"})
    ET.SubElement(add,"wautJunction",{"wautID":"w","junctionID":tlid})
    ET.ElementTree(add).write(EE("ctrl_fixed.add.xml"),encoding="UTF-8",xml_declaration=True)
    return g_ns,g_ew

def run():
    subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),
        "-a",EE("ctrl_fixed.add.xml"),"--end","3600","--tripinfo-output",EE("t.xml"),
        "--no-step-log","true","--no-warnings","true"],check=True)
    t=ET.parse(EE("t.xml")).findall("tripinfo"); w=[float(x.get('waitingTime')) for x in t]
    return (sum(w)/len(w) if w else 0.0, len(w))

print("Cycle  greenNS/EW   avgWait   completed")
best=None
for C in (60,70,80,90,100,110,120):
    gns,gew=write_fixed(C); aw,n=run()
    print(f"{C:4d}s   {gns:3d}/{gew:<3d}     {aw:6.2f}s    {n}")
    if n>=4820 and (best is None or aw<best[1]): best=(C,aw,n)
print("\nBest fixed-time cycle that clears demand:", best)
