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
