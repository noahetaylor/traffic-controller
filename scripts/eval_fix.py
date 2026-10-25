import numpy as np, os, glob, xml.etree.ElementTree as ET, subprocess
import sumo_rl
from stable_baselines3 import DQN
from ee_paths import EE

HOUR=13; hh=f"{HOUR:02d}"; NET=EE("donmills_final.net.xml"); ROU=EE(f"demand_{hh}.rou.xml")

def avg_wait(f):
    tr=ET.parse(f).findall("tripinfo"); w=[float(x.get("waitingTime")) for x in tr]
    return (sum(w)/len(w) if w else 0.0, len(w))

# baselines (already-built add-files from earlier)
def run(addf,out):
    subprocess.run(["sumo","-n",NET,"-r",ROU,"-a",addf,"--end","3600","--tripinfo-output",out,
        "--no-step-log","true","--no-warnings","true"],check=True); return avg_wait(out)
fa,fn=run(EE(f"fixed_{hh}.add.xml"),EE(f"fixed_{hh}.xml"))
aa,an=run(EE(f"act_{hh}.add.xml"),EE(f"act_{hh}.xml"))

# load the BEST model saved by EvalCallback last run
best=DQN.load(EE(f"best_{hh}/best_model"))

# ---- KEY: evaluate through the SAME sumo-rl env, and read waiting time from
#      the env's own tripinfo (out_csv/tripinfo), matching training exactly ----
env=sumo_rl.SumoEnvironment(net_file=NET,route_file=ROU,single_agent=True,use_gui=False,
    num_seconds=3600,delta_time=5,yellow_time=3,min_green=5,max_green=40,
    reward_fn="diff-waiting-time",
    additional_sumo_cmd=f'--tripinfo-output {EE(fEE("rl_{hh}_v2.xml"))} --no-warnings true')
obs,info=env.reset()
done=False; total_r=0.0; steps=0
while not done:
    a,_=best.predict(obs,deterministic=True)
    obs,r,term,trunc,info=env.step(int(a))
    total_r+=r; steps+=1; done=term or trunc
env.close()
ra,rn=avg_wait(EE(f"rl_{hh}_v2.xml"))
print(f"RL eval: cumulative reward={total_r:.1f} over {steps} steps")

print(f"\n===== {hh}:00 THREE-WAY (demand {fn+ (0)} ...) =====")
print(f"Fixed-time : {fa:6.2f} s  (n={fn})")
print(f"Actuated   : {aa:6.2f} s  (n={an})   {100*(aa-fa)/fa:+.1f}% vs fixed")
print(f"RL (DQN)   : {ra:6.2f} s  (n={rn})   {100*(ra-fa)/fa:+.1f}% vs fixed / {100*(ra-aa)/aa:+.1f}% vs act")

# sanity: reward near 0 should mean LOW waiting. If reward~0 but wait is huge, mapping is broken.
print(f"\nSanity: eval reward {total_r:.1f} (near 0 = good). RL wait {ra:.1f}s. "
      f"{'CONSISTENT' if (total_r>-30 and ra<aa*1.5) else 'STILL INCONSISTENT — mapping bug'}")
