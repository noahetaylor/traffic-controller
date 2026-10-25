import pandas as pd, numpy as np, subprocess, os, xml.etree.ElementTree as ET
import sumolib, sumo_rl
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import EvalCallback
from stable_baselines3.common.monitor import Monitor
from ee_paths import EE

HOUR = 13
hh=f"{HOUR:02d}"; NET=EE("donmills_final.net.xml"); ROU=EE(f"demand_{hh}.rou.xml")

df=pd.read_csv(EE("don_mills_lawrence_raw.csv")); df["start_time"]=pd.to_datetime(df["start_time"])
df=df[df["start_time"].dt.hour==HOUR]; modes=["cars","truck","bus"]
def mv(a,m): return int(df[[f"{a}_appr_{md}_{m}" for md in modes]].to_numpy().sum())
geo={"n":("N_in",{"l":"E_out","t":"S_out","r":"W_out"}),"s":("S_in",{"l":"W_out","t":"N_out","r":"E_out"}),
     "e":("E_in",{"l":"S_out","t":"W_out","r":"N_out"}),"w":("W_in",{"l":"N_out","t":"E_out","r":"S_out"})}
routes=ET.Element("routes"); tot=0
for leg,(ine,outs) in geo.items():
    for m,oute in outs.items():
        c=mv(leg,m); tot+=c
        if c>0:
            ET.SubElement(routes,"route",{"id":f"{leg}_{m}","edges":f"{ine} {oute}"})
            ET.SubElement(routes,"flow",{"id":f"f_{leg}_{m}","route":f"{leg}_{m}","begin":"0","end":"3600",
                "vehsPerHour":str(c),"departLane":"best","departSpeed":"max"})
ET.ElementTree(routes).write(ROU,encoding="UTF-8",xml_declaration=True)
print(f"HOUR {hh}:00 demand={tot} veh/hr")

def avg_wait(f):
    tr=ET.parse(f).findall("tripinfo"); w=[float(x.get("waitingTime")) for x in tr]
    return (sum(w)/len(w) if w else 0.0,len(w))

# baselines already written by the earlier run (fixed_13/act_13). Recompute cleanly:
def run(addf,out):
    subprocess.run(["sumo","-n",NET,"-r",ROU,"-a",addf,"--end","3600","--tripinfo-output",out,
        "--no-step-log","true","--no-warnings","true"],check=True); return avg_wait(out)
fa,fn=run(EE(f"fixed_{hh}.add.xml"),EE(f"fixed_{hh}.xml"))
aa,an=run(EE(f"act_{hh}.add.xml"),EE(f"act_{hh}.xml"))

def make_env():
    return Monitor(sumo_rl.SumoEnvironment(net_file=NET,route_file=ROU,single_agent=True,use_gui=False,
        num_seconds=3600,delta_time=5,yellow_time=3,min_green=5,max_green=40,reward_fn="diff-waiting-time"))

train_env=make_env(); eval_env=make_env()
# EvalCallback snapshots the BEST policy by evaluation reward, saving to ./best_{hh}/best_model.zip
evalcb=EvalCallback(eval_env, best_model_save_path=EE(f"best_{hh}"),
    eval_freq=3600, n_eval_episodes=1, deterministic=True, verbose=1)
model=DQN("MlpPolicy",train_env,learning_rate=1e-3,buffer_size=100000,learning_starts=2000,
    batch_size=64,gamma=0.99,exploration_fraction=0.4,exploration_final_eps=0.03,
    train_freq=1,target_update_interval=1000,verbose=0,seed=42)
model.learn(total_timesteps=40000,callback=evalcb)

# load the BEST snapshot, not the last weights
best=DQN.load(EE(f"best_{hh}/best_model"))
ev=sumo_rl.SumoEnvironment(net_file=NET,route_file=ROU,single_agent=True,use_gui=False,
    num_seconds=3600,delta_time=5,yellow_time=3,min_green=5,max_green=40,reward_fn="diff-waiting-time",
    additional_sumo_cmd=f'--tripinfo-output {EE(fEE("rl_{hh}.xml"))}')
obs,_=ev.reset(); done=False
while not done:
    a,_=best.predict(obs,deterministic=True); obs,r,term,trunc,_=ev.step(int(a)); done=term or trunc
ev.close()
ra,rn=avg_wait(EE(f"rl_{hh}.xml"))

print(f"\n===== {hh}:00 THREE-WAY (demand {tot} veh/hr) — BEST policy =====")
print(f"Fixed-time : {fa:6.2f} s  (n={fn})")
print(f"Actuated   : {aa:6.2f} s  (n={an})   {100*(aa-fa)/fa:+.1f}% vs fixed")
print(f"RL (DQN)   : {ra:6.2f} s  (n={rn})   {100*(ra-fa)/fa:+.1f}% vs fixed / {100*(ra-aa)/aa:+.1f}% vs act")
