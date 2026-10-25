import pandas as pd, subprocess, xml.etree.ElementTree as ET
from ee_paths import EE

# STATIC net so the baseline program is genuinely fixed-time
subprocess.run(["netconvert","--node-files",EE("dm.nod.xml"),"--edge-files",EE("dm.edg.xml"),
    "-o",EE("donmills_final.net.xml"),"--tls.guess","--tls.default-type","static",
    "--no-turnarounds"],check=True)

# Webster green split from AM demand
df=pd.read_csv(EE("don_mills_lawrence_raw.csv")); df["start_time"]=pd.to_datetime(df["start_time"])
df=df[df["start_time"].dt.hour==8]; modes=["cars","truck","bus"]
def leg(a): return int(df[[f"{a}_appr_{m}_{mv}" for m in modes for mv in ['l','t','r']]].to_numpy().sum())
ns=leg("n")+leg("s"); ew=leg("e")+leg("w")
SAT=1800.0; y_ns,y_ew=ns/(2*SAT),ew/(2*SAT); L=16.0
C=max(60,min(120,int((1.5*L+5)/(1-(y_ns+y_ew))))); g=C-L
g_ns=max(10,round(g*y_ns/(y_ns+y_ew))); g_ew=max(10,g-g_ns)
print(f"Webster: cycle {C}s, green NS {g_ns}s / EW {g_ew}s")

root=ET.parse(EE("donmills_final.net.xml")).getroot(); tl=root.find("tlLogic")
tlid=tl.get("id"); phases=tl.findall("phase")

def program(prog_id, ptype, actuated):
    p=ET.Element("tlLogic",{"id":tlid,"type":ptype,"programID":prog_id,"offset":"0"})
    for ph in phases:
        st=ph.get("state"); d=float(ph.get("duration"))
        gr=any(c in "Gg" for c in st); ye=any(c in "yY" for c in st)
        if gr and not ye:
            isNS = st.rfind("G") >= len(st)//2
            dur = g_ns if isNS else g_ew
        else:
            dur = d
        a={"duration":str(int(dur)),"state":st}
        if actuated and gr and not ye: a.update({"minDur":"5","maxDur":str(int(dur)+25)})
        ET.SubElement(p,"phase",a)
    return p

def write_add(fname, prog_id, ptype, actuated):
    add=ET.Element("additional")
    add.append(program(prog_id, ptype, actuated))
    w=ET.SubElement(add,"WAUT",{"id":"w","refTime":"0","startProg":prog_id})
    ET.SubElement(w,"wautSwitch",{"time":"0","to":prog_id})
    ET.SubElement(add,"wautJunction",{"wautID":"w","junctionID":tlid})
    ET.ElementTree(add).write(fname,encoding="UTF-8",xml_declaration=True)

write_add(EE("ctrl_fixed.add.xml"),"fixed","static",False)
write_add(EE("ctrl_act.add.xml"),"act","actuated",True)

def run(addf,out):
    subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),"-a",addf,
        "--end","3600","--tripinfo-output",out,"--no-step-log","true","--no-warnings","true"],check=True)
    t=ET.parse(out).findall("tripinfo"); w=[float(x.get('waitingTime')) for x in t]
    return (sum(w)/len(w) if w else 0.0, len(w))

fa,fn=run(EE("ctrl_fixed.add.xml"),EE("am_fixed.xml"))
aa,an=run(EE("ctrl_act.add.xml"),EE("am_act.xml"))
print("\n===== AM PEAK — clean baselines (Webster fixed vs actuated) =====")
print(f"Fixed-time : {fa:6.2f} s  (n={fn})")
print(f"Actuated   : {aa:6.2f} s  (n={an})   {100*(aa-fa)/fa:+.1f}% vs fixed")
