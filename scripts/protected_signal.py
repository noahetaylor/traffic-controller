import pandas as pd, subprocess, xml.etree.ElementTree as ET
import sumolib
from ee_paths import EE

net = sumolib.net.readNet(EE("donmills_final.net.xml"))
tls = net.getTrafficLights()[0]; tlid = tls.getID()

# classify every controlled link by movement, straight from the net connections
move_of = {("N_in","E_out"):"NL",("N_in","S_out"):"NT",("N_in","W_out"):"NR",
           ("S_in","W_out"):"SL",("S_in","N_out"):"ST",("S_in","E_out"):"SR",
           ("E_in","S_out"):"EL",("E_in","W_out"):"ET",("E_in","N_out"):"ER",
           ("W_in","N_out"):"WL",("W_in","E_out"):"WT",("W_in","S_out"):"WR"}
conns = tls.getConnections()
nlinks = max(li for _,_,li in conns) + 1          # count links directly
link_move = {}
for fromLane,toLane,li in conns:
    link_move[li] = move_of.get((fromLane.getEdge().getID(), toLane.getEdge().getID()), "??")
unmapped = [li for li in range(nlinks) if link_move.get(li,"??")=="??"]
print("links:", nlinks, "| unmapped:", unmapped or "none")

groups = {"NS_T":{"NT","NR","ST","SR"}, "NS_L":{"NL","SL"},
          "EW_T":{"ET","ER","WT","WR"}, "EW_L":{"EL","WL"}}
order = ["NS_T","NS_L","EW_T","EW_L"]

def gstate(active):
    return "".join("G" if link_move.get(li,"??") in active else "r" for li in range(nlinks))
def ystate(g):
    return "".join("y" if c=="G" else "r" for c in g)

df=pd.read_csv(EE("don_mills_lawrence_raw.csv")); df["start_time"]=pd.to_datetime(df["start_time"])
df=df[df["start_time"].dt.hour==8]; modes=["cars","truck","bus"]
def mv(a,m): return int(df[[f"{a}_appr_{md}_{m}" for md in modes]].to_numpy().sum())
dem={"NS_T":mv("n","t")+mv("n","r")+mv("s","t")+mv("s","r"), "NS_L":mv("n","l")+mv("s","l"),
     "EW_T":mv("e","t")+mv("e","r")+mv("w","t")+mv("w","r"), "EW_L":mv("e","l")+mv("w","l")}

def build(cycle):
    L=4*3; budget=cycle-L; tot=sum(dem.values())
    mins={"NS_T":12,"NS_L":7,"EW_T":12,"EW_L":7}
    g={k:max(mins[k],round(budget*dem[k]/tot)) for k in order}
    g["NS_T"]+=cycle-(sum(g.values())+L)
    add=ET.Element("additional")
    p=ET.SubElement(add,"tlLogic",{"id":tlid,"type":"static","programID":"prot","offset":"0"})
    for k in order:
        gs=gstate(groups[k])
        ET.SubElement(p,"phase",{"duration":str(int(g[k])),"state":gs})
        ET.SubElement(p,"phase",{"duration":"3","state":ystate(gs)})
    w=ET.SubElement(add,"WAUT",{"id":"w","refTime":"0","startProg":"prot"})
    ET.SubElement(w,"wautSwitch",{"time":"0","to":"prot"})
    ET.SubElement(add,"wautJunction",{"wautID":"w","junctionID":tlid})
    ET.ElementTree(add).write(EE("ctrl_prot.add.xml"),encoding="UTF-8",xml_declaration=True)
    return g

def run():
    subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),"-a",EE("ctrl_prot.add.xml"),
        "--end","3600","--tripinfo-output",EE("t.xml"),"--no-step-log","true","--no-warnings","true"],check=True)
    tr=ET.parse(EE("t.xml")).findall("tripinfo")
    w=[float(x.get("waitingTime")) for x in tr]
    wl=[float(x.get("waitingTime")) for x in tr if x.get("id").split(".")[0]=="f_w_l"]
    return (sum(w)/len(w) if w else 0), len(w), (sum(wl)/len(wl) if wl else 0), len(wl)

print("\nphase greens (demand-split):", build(100))
print("\nCycle  avgWait  completed   w_l_wait  w_l_done")
for C in (90,100,110,120):
    build(C); aw,n,wlw,wln = run()
    print(f"{C:4d}s   {aw:6.2f}s   {n:5d}      {wlw:6.1f}s   {wln}")
