import subprocess, os, xml.etree.ElementTree as ET
from collections import Counter
import sumo_rl
from stable_baselines3 import DQN
from ee_paths import EE

def count_from(fname):
    b=t=c=0; lanes=Counter()
    if os.path.exists(fname):
        for line in open(fname,encoding="utf-8",errors="ignore"):
            if "emergency braking" in line:
                b+=1
                if "lane '" in line: lanes[line.split("lane '")[1].split("'")[0]]+=1
            if "teleport" in line.lower(): t+=1
            if "collision" in line.lower(): c+=1
    return b,t,c,lanes

# ---- A) FIXED program: capture BOTH stdout and stderr ----
with open(EE("fixed_out.txt"),"w",encoding="utf-8") as f:
    subprocess.run(["sumo","-n",EE("donmills_final.net.xml"),"-r",EE("am_peak.rou.xml"),
        "-a",EE("ctrl_prot.add.xml"),"--end","3600","--tripinfo-output",EE("t.xml"),
        "--no-step-log","true"], stdout=f, stderr=subprocess.STDOUT, check=False)
b,t,c,lanes = count_from(EE("fixed_out.txt"))
print(f"FIXED 4-phase:  braking={b}  teleports={t}  collisions={c}")
for ln,n in lanes.most_common(4): print(f"     {ln}: {n}")

# ---- B) TRAINED RL agent: run it and capture SUMO's warnings ----
env = sumo_rl.SumoEnvironment(net_file=EE("donmills_final.net.xml"), route_file=EE("am_peak.rou.xml"),
        single_agent=True, use_gui=False, num_seconds=3600,
        delta_time=5, yellow_time=3, min_green=5, max_green=40,
        additional_sumo_cmd=f'--error-log {EE("rl_err.txt")} --collision-output {EE("rl_coll.xml")}')
model=DQN.load(EE("dqn_donmills_am"))
obs,_=env.reset(); done=False
while not done:
    a,_=model.predict(obs,deterministic=True)
    obs,r,term,trunc,_=env.step(int(a)); done=term or trunc
env.close()
b2,t2,c2,lanes2 = count_from(EE("rl_err.txt"))
ncoll = len(ET.parse(EE("rl_coll.xml")).getroot().findall("collision")) if os.path.exists(EE("rl_coll.xml")) else 0
print(f"\nTRAINED RL:     braking={b2}  teleports={t2}  collisions(log)={c2}  collisions(file)={ncoll}")
for ln,n in lanes2.most_common(4): print(f"     {ln}: {n}")
