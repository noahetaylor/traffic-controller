import pandas as pd, numpy as np, subprocess, os, xml.etree.ElementTree as ET
import sumolib, sumo_rl
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import BaseCallback
from ee_paths import EE

HOUR = 13                      # <-- 13 = midday. Change to 17 for PM later.
hh = f"{HOUR:02d}"
NET = EE("donmills_final.net.xml")
ROU = EE(f"demand_{hh}.rou.xml")

# ---------- 1. demand for this hour ----------
df = pd.read_csv(EE("don_mills_lawrence_raw.csv")); df["start_time"]=pd.to_datetime(df["start_time"])
df = df[df["start_time"].dt.hour == HOUR]; modes=["cars","truck","bus"]
def mv(a,m): return int(df[[f"{a}_appr_{md}_{m}" for md in modes]].to_numpy().sum())
geo = {"n":("N_in",{"l":"E_out","t":"S_out","r":"W_out"}),
       "s":("S_in",{"l":"W_out","t":"N_out","r":"E_out"}),
       "e":("E_in",{"l":"S_out","t":"W_out","r":"N_out"}),
       "w":("W_in",{"l":"N_out","t":"E_out","r":"S_out"})}
routes=ET.Element("routes"); tot=0
for leg,(ine,outs) in geo.items():
    for m,oute in outs.items():
        c=mv(leg,m); tot+=c
        if c<=0: continue
        rid=f"{leg}_{m}"
        ET.SubElement(routes,"route",{"id":rid,"edges":f"{ine} {oute}"})
        ET.SubElement(routes,"flow",{"id":f"f_{rid}","route":rid,"begin":"0","end":"3600",
                                     "vehsPerHour":str(c),"departLane":"best","departSpeed":"max"})
ET.ElementTree(routes).write(ROU,encoding="UTF-8",xml_declaration=True)
print(f"HOUR {hh}:00  demand = {tot} veh/hr  ->  {ROU}")

# ---------- 2. classify signal links, build 4-phase groups ----------
net=sumolib.net.readNet(NET); tls=net.getTrafficLights()[0]; tlid=tls.getID()
move_of={("N_in","E_out"):"NL",("N_in","S_out"):"NT",("N_in","W_out"):"NR",
         ("S_in","W_out"):"SL",("S_in","N_out"):"ST",("S_in","E_out"):"SR",
         ("E_in","S_out"):"EL",("E_in","W_out"):"ET",("E_in","N_out"):"ER",
         ("W_in","N_out"):"WL",("W_in","E_out"):"WT",("W_in","S_out"):"WR"}
conns=tls.getConnections(); nlinks=max(li for _,_,li in conns)+1
link_move={}
for fromLane,toLane,li in conns:
    link_move[li]=move_of.get((fromLane.getEdge().getID(),toLane.getEdge().getID()),"??")
groups={"NS_T":{"NT","NR","ST","SR"},"NS_L":{"NL","SL"},"EW_T":{"ET","ER","WT","WR"},"EW_L":{"EL","WL"}}
order=["NS_T","NS_L","EW_T","EW_L"]
gstate=lambda act:"".join("G" if link_move.get(i,"?") in act else "r" for i in range(nlinks))
ystate=lambda g:"".join("y" if ch=="G" else "r" for ch in g)

# ---------- 3. Webster timing from this hour's demand ----------
n_tr,s_tr,e_tr,w_tr = mv("n","t")+mv("n","r"),mv("s","t")+mv("s","r"),mv("e","t")+mv("e","r"),mv("w","t")+mv("w","r")
SAT=1800.0
y={"NS_T":max(n_tr,s_tr)/(3*SAT),"NS_L":max(mv("n","l"),mv("s","l"))/SAT,
   "EW_T":max(e_tr,w_tr)/(3*SAT),"EW_L":max(mv("e","l"),mv("w","l"))/SAT}
Y=sum(y.values()); L=16
C=int(np.clip((1.5*L+5)/max(0.15,1-Y),60,120)); budget=C-L
mins={"NS_T":10,"NS_L":6,"EW_T":10,"EW_L":6}
g={k:max(mins[k],round(budget*y[k]/sum(y.values()))) for k in order}
g["NS_T"]+=C-(sum(g.values())+L)
print(f"Webster: Y={Y:.2f} cycle={C}s greens={g}")

def write_prog(fname,prog_id,ptype,actuated):
    add=ET.Element("additional")
    p=ET.SubElement(add,"tlLogic",{"id":tlid,"type":ptype,"programID":prog_id,"offset":"0"})
    for k in order:
        gs=gstate(groups[k])
        a={"duration":str(int(g[k])),"state":gs}
        if actuated: a.update({"minDur":str(mins[k]),"maxDur":str(int(g[k])+25)})
        ET.SubElement(p,"phase",a)
        ET.SubElement(p,"phase",{"duration":"3","state":ystate(gs)})
    w=ET.SubElement(add,"WAUT",{"id":"w","refTime":"0","startProg":prog_id})
    ET.SubElement(w,"wautSwitch",{"time":"0","to":prog_id})
    ET.SubElement(add,"wautJunction",{"wautID":"w","junctionID":tlid})
    ET.ElementTree(add).write(fname,encoding="UTF-8",xml_declaration=True)
write_prog(EE(f"fixed_{hh}.add.xml"),"fx","static",False)
write_prog(EE(f"act_{hh}.add.xml"),"ac","actuated",True)

def avg_wait(f):
    tr=ET.parse(f).findall("tripinfo"); w=[float(x.get("waitingTime")) for x in tr]
    return (sum(w)/len(w) if w else 0.0, len(w))
def run(addf,out):
    subprocess.run(["sumo","-n",NET,"-r",ROU,"-a",addf,"--end","3600",
        "--tripinfo-output",out,"--no-step-log","true","--no-warnings","true"],check=True)
    return avg_wait(out)
fa,fn=run(EE(f"fixed_{hh}.add.xml"),EE(f"fixed_{hh}.xml"))
aa,an=run(EE(f"act_{hh}.add.xml"),EE(f"act_{hh}.xml"))

# ---------- 4. train RL on this hour ----------
class RL(BaseCallback):
    def __init__(s): super().__init__(); s.ep=[]; s.c=0
    def _on_step(s):
        s.c+=float(s.locals["rewards"][0])
        if s.locals["dones"][0]: s.ep.append(s.c); s.c=0
        return True
env=sumo_rl.SumoEnvironment(net_file=NET,route_file=ROU,single_agent=True,use_gui=False,
    num_seconds=3600,delta_time=5,yellow_time=3,min_green=5,max_green=40,reward_fn="diff-waiting-time")
model=DQN("MlpPolicy",env,learning_rate=1e-3,buffer_size=100000,learning_starts=2000,
    batch_size=64,gamma=0.99,exploration_fraction=0.4,exploration_final_eps=0.03,
    train_freq=1,target_update_interval=1000,verbose=1,seed=42)
cb=RL(); model.learn(total_timesteps=40000,callback=cb)
model.save(EE(f"dqn_donmills_{hh}")); np.save(EE(f"dqn_{hh}_rewards.npy"),np.array(cb.ep))

ev=sumo_rl.SumoEnvironment(net_file=NET,route_file=ROU,single_agent=True,use_gui=False,
    num_seconds=3600,delta_time=5,yellow_time=3,min_green=5,max_green=40,reward_fn="diff-waiting-time",
    additional_sumo_cmd=f'--tripinfo-output {EE(fEE("rl_{hh}.xml"))}')
obs,_=ev.reset(); done=False
while not done:
    a,_=model.predict(obs,deterministic=True); obs,r,term,trunc,_=ev.step(int(a)); done=term or trunc
ev.close()
ra,rn=avg_wait(EE(f"rl_{hh}.xml"))

# ---------- 5. report + log ----------
print(f"\n===== {hh}:00 THREE-WAY (demand {tot} veh/hr) =====")
print(f"Fixed-time : {fa:6.2f} s  (n={fn})")
print(f"Actuated   : {aa:6.2f} s  (n={an})   {100*(aa-fa)/fa:+.1f}% vs fixed")
print(f"RL (DQN)   : {ra:6.2f} s  (n={rn})   {100*(ra-fa)/fa:+.1f}% vs fixed / {100*(ra-aa)/aa:+.1f}% vs act")

row=f"{hh},{tot},{fa:.2f},{aa:.2f},{ra:.2f},{100*(ra-fa)/fa:.1f},{100*(ra-aa)/aa:.1f}\n"
head="hour,demand,fixed,actuated,rl,rl_vs_fixed_pct,rl_vs_act_pct\n"
if not os.path.exists(EE("scenario_results.csv")): open(EE("scenario_results.csv"),"w").write(head)
open(EE("scenario_results.csv"),"a").write(row)
print("Appended to scenario_results.csv")

try:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    ep=np.array(cb.ep); k=5
    plt.figure(figsize=(7,4)); plt.plot(ep,alpha=0.35,label="episode reward")
    if len(ep)>=k: plt.plot(range(k-1,len(ep)),np.convolve(ep,np.ones(k)/k,"valid"),lw=2,label="5-ep avg")
    plt.xlabel("episode"); plt.ylabel("reward (higher=less waiting)")
    plt.title(f"DQN learning curve — Don Mills & Lawrence, {hh}:00"); plt.legend(); plt.grid(alpha=.3)
    plt.tight_layout(); plt.savefig(EE(f"dqn_{hh}_learning_curve.png"),dpi=140); print(f"Saved dqn_{hh}_learning_curve.png")
except Exception as e: print("plot skipped:",e)
