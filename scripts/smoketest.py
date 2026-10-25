import sumo_rl
from pathlib import Path
from ee_paths import EE, SUMO_RL_REPO

base = SUMO_RL_REPO
net = next(base.rglob("single-intersection.net.xml"))
route = (next(base.rglob("single-intersection.rou.xml"), None)
         or next(base.rglob("single-intersection*.rou.xml")))
print("Using net:  ", net)
print("Using route:", route)

env = sumo_rl.SumoEnvironment(
    net_file=str(net),
    route_file=str(route),
    use_gui=True,
    num_seconds=1000,
    single_agent=True,
)

obs, info = env.reset()
done = False
while not done:
    action = env.action_space.sample()   # random phase choice
    obs, reward, terminated, truncated, info = env.step(action)
    done = terminated or truncated

env.close()
print("Smoke test complete - the RL loop runs.")
