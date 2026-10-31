# RL Traffic Signal Control: Don Mills Rd / Lawrence Ave E, Toronto

A DQN signal controller compared against tuned fixed-time (Webster) and actuated
baselines at one real four-way intersection, using SUMO microsimulation and
Toronto turning-movement counts.

## Setup

1. Install [SUMO 1.26.0](https://eclipse.dev/sumo/) and make sure `sumo` is on PATH.
2. Python 3.13, then `pip install -r requirements.txt`.

## Running

All scripts live in `scripts/` and resolve files through `ee_paths.EE()`, so they
can be run from any directory.

```
python scripts/build_scenario.py 13      # demand + Webster timing + baseline sweeps for 13:00
python scripts/train_scenario.py 13      # train DQN, pick best snapshot, evaluate over 5 seeds
python scripts/cross_evaluate.py         # every controller on every hour
python scripts/demand_sweep.py           # scale the 08:00 demand to sweep saturation
```

`scenario_lib.py` holds the shared build / train / evaluate logic.

## Layout

| Folder | Contents |
|---|---|
| `scripts/` | All code |
| `networks/` | `.net.xml` and matching `.rou.xml` demand files |
| `signals/` | Fixed-time and actuated signal programs (`.add.xml`) |
| `data/` | Raw 15-minute turning-movement counts |
| `models/` | Trained DQN policies and best-snapshot checkpoints |
| `figures/` | Learning curves |
| `outputs/` | Result tables (raw simulation output is not committed) |

## Data

Turning-movement counts: City of Toronto Open Data, *Traffic Volumes -
Multimodal Intersection Turning Movement Counts*, contains information licensed
under the Open Government Licence - Toronto.

## Results

Mean vehicle waiting time (s), mean ± sd over 5 SUMO seeds. All three controllers
run the same protected-permissive signal structure; both baselines are tuned
(fixed-time: Webster splits plus a cycle-length sweep; actuated: minDur / maxDur /
detector-gap sweep); RL is the best training snapshot.

| Hour | Demand (veh/hr) | Saturation Y | Fixed-time | Actuated | RL (DQN) | RL vs fixed |
|---|---|---|---|---|---|---|
| 13:00 | 3,307 | 0.509 | 12.67 ± 0.11 | 11.91 ± 0.29 | 7.32 ± 0.20 | −42.3% |
| 17:00 | 4,434 | 0.633 | 13.85 ± 0.13 | 15.61 ± 0.78 | 13.96 ± 0.12 | +0.8% |
| 08:00 | 4,879 | 0.739 | 20.18 ± 0.38 | 21.97 ± 0.27 | 28.57 ± 0.96 | +41.6% |

At this intersection, RL wins at midday, ties at the evening peak and loses at
the morning peak.
`outputs/demand_sweep_results.csv` holds the scaled-demand sweep.

## Development history

The project was developed locally without version control and committed here in
October 2026, so the git history starts at the finished state. The main stages:

| When (2026) | Stage |
|---|---|
| Apr–May | Chose City of Toronto turning-movement counts as the data source |
| Jul 24 | Built the SUMO + sumo-rl + Stable-Baselines3 toolchain end to end |
| Jul 25 | Site selection: 6,373 signalized intersections filtered to 351, Don Mills / Lawrence chosen; first DQN on toy demand (actuated beat it) |
| Jul 26–27 | First runs on real demand showed a ~30% RL win, later retracted |
| Aug 14 | Found the root cause: sumo-rl always runs the network's built-in signal program, so the baselines had been running a different one. Rebuilt every controller on one shared protected-permissive program |
| Aug 16 | Tuned both baselines properly (Webster + cycle sweep, actuated parameter sweep) |
| Aug 17 | Matched 08:00 / 17:00 comparison: the advantage tracks saturation, not traffic direction |
| Aug 18 | Repeated training run at 08:00: training variance grows with saturation |
| Oct | Scaled-demand sweep (`demand_sweep.py`) |
