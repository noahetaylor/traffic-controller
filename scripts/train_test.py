import sumo_rl
from stable_baselines3 import DQN
from pathlib import Path
import subprocess, xml.etree.ElementTree as ET
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

# Fixed-time baseline on this exact net+route
subprocess.run(["sumo","-n",str(net),"-r",str(route),"--end","3600",
                "--tripinfo-output",EE("cmp_fixed.xml"),
                "--no-step-log","true","--no-warnings","true"], check=True)
fixed_avg, fixed_n = avg_wait(EE("cmp_fixed.xml"))

# Train a DQN agent (headless). Short run just to prove training works.
env = sumo_rl.SumoEnvironment(net_file=str(net), route_file=str(route),
                              single_agent=True, use_gui=False, num_seconds=3600)
model = DQN("MlpPolicy", env, learning_rate=1e-3, buffer_size=50000,
            learning_starts=1000, exploration_fraction=0.3, verbose=1, seed=42)
model.learn(total_timesteps=25000)

# Evaluate the trained agent, writing its own tripinfo
eval_env = sumo_rl.SumoEnvironment(net_file=str(net), route_file=str(route),
            single_agent=True, use_gui=False, num_seconds=3600,
            additional_sumo_cmd=f'--tripinfo-output {EE("cmp_rl.xml")}')
obs, info = eval_env.reset()
done = False
while not done:
    action, _ = model.predict(obs, deterministic=True)
    obs, reward, terminated, truncated, info = eval_env.step(int(action))
    done = terminated or truncated
eval_env.close()
rl_avg, rl_n = avg_wait(EE("cmp_rl.xml"))

print("\n===== RESULT =====")
print(f"Fixed-time : {fixed_avg:6.2f} s  (n={fixed_n})")
print(f"RL (DQN)   : {rl_avg:6.2f} s  (n={rl_n})")
if fixed_avg > 0:
    print(f"Change     : {100*(rl_avg-fixed_avg)/fixed_avg:+.1f}% vs fixed-time")
