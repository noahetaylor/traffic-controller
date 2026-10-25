import subprocess, xml.etree.ElementTree as ET
from collections import Counter
import sumolib
from ee_paths import EE

# Build an ACTUATED version of the 4-phase protected program (min/max per phase)
net=sumolib.net.readNet(EE("donmills_final.net.xml")); tls=net.getTrafficLights()[0]; tlid=tls.getID()
base=ET.parse(EE("ctrl_prot.add.xml")).getroot()
prog=base.find("tlLogic")
add=ET.Element("additional")
p=ET.SubElement(add,"tlLogic",{"id":tlid,"type":"actuated","programID":"actp","offset":"0"})
for ph in prog.findall("phase"):
    st=ph.get("state"); d=int(ph.get("duration"))
    g=any(c in "Gg" for c in st); y=any(c in "yY" for c in st)
    a={"duration":str(d),"state":st}
    if g and not y: a.update({"minDur":"5","maxDur":str(d+30)})
    ET.SubElement(p,"phase",a)
w=ET.SubElement(add,"WAUT",{"id":"w","refTime":"0","startProg":"actp"})
ET.SubElement(w,"wautSwitch",{"time":"0","to":"actp"})
ET.SubElement(add,"wautJunction",{"wautID":"w","junctionID":tlid})
ET.ElementTree(add).write(EE("ctrl_actp.add.xml"),encoding="UTF-8",xml_declaration=True)

def run(addf):
    subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),"-a",addf,
        "--end","3600","--tripinfo-output",EE("t.xml"),"--no-step-log","true","--no-warnings","true"],check=True)
    tr=ET.parse(EE("t.xml")).findall("tripinfo")
    w=[float(x.get("waitingTime")) for x in tr]
    by=Counter(); ct=Counter()
    for x in tr:
        k=x.get("id").split(".")[0].replace("f_",""); by[k]+=float(x.get("waitingTime")); ct[k]+=1
    worst=sorted(((by[k]/ct[k],k,ct[k]) for k in ct),reverse=True)[:4]
    return (sum(w)/len(w) if w else 0), len(w), worst

aw,n,worst=run(EE("ctrl_actp.add.xml"))
print(f"Actuated 4-phase:  avgWait {aw:.2f}s   completed {n}/4879")
print("Worst movements (wait, move, count):")
for wv,k,c in worst: print(f"   {k}: {wv:.1f}s over {c}")
