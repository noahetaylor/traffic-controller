"""Demand sweep: scale the 08:00 (AM) turning-movement profile by a range of
factors to get a dense set of saturation (Y) points, instead of relying only on
the 3 real-hour profiles (Y = 0.509, 0.633, 0.739).

Holding the AM turn-movement *proportions* fixed and scaling overall volume
means only saturation varies between sweep points -- demand mix does not -- so
this is cleaner than comparing across different real hours. Scale 1.0
reproduces the already-measured 08:00 result (Y=0.739, fixed 20.18s,
actuated 21.97s, RL 28.57s) as a sanity check, so it is skipped by default.
Scales above ~1.35 push Y past 1.0 (oversaturation), which is a separate
named gap in the project.

    python demand_sweep.py                  # run every scale not yet logged
    python demand_sweep.py 0.95              # run just one scale
    python demand_sweep.py 0.90 1000 500     # scale, steps, eval_freq -- smoke test

Appends one row per completed scale to outputs/demand_sweep_results.csv, so a
killed/interrupted run loses nothing already finished -- rerun with no args to
pick up where it left off.
"""

import sys, csv, json
from pathlib import Path
import xml.etree.ElementTree as ET
import sumo_rl
from stable_baselines3 import DQN
from stable_baselines3.common.callbacks import EvalCallback, BaseCallback
from stable_baselines3.common.monitor import Monitor
from ee_paths import EE
import scenario_lib as S


class ResumeCheckpoint(BaseCallback):
    """Saves the model + a step counter at regular intervals so a killed run
    can resume training instead of restarting from step 0.

    self.num_timesteps is the MODEL's cumulative counter (SB3 sets it from
    model.num_timesteps), which already includes prior steps because training
    is resumed with reset_num_timesteps=False -- do not add start_steps again.
    """
    def __init__(self, save_path, progress_path, freq):
        super().__init__()
        self.save_path = save_path
        self.progress_path = progress_path
        self.freq = freq
        self._last = 0

    def _on_step(self):
        if self.num_timesteps - self._last >= self.freq:
            self._last = self.num_timesteps
            self.model.save(self.save_path)
            Path(self.progress_path).write_text(
                json.dumps({"done_steps": self.num_timesteps}))
        return True

BASE_HOUR = 8
SCALES = [0.50, 0.65, 0.80, 0.95, 1.15, 1.30]
RESULTS_CSV = EE("demand_sweep_results.csv")
STEPS = 50_000
EVAL_FREQ = 10_000


def scale_demand(base, factor):
    return {k: max(0, round(v * factor)) for k, v in base.items()}


def write_scaled_routes(tag, demand):
    routes = ET.Element("routes")
    total = 0
    for leg, (entry, turns) in S.GEO.items():
        for m, exit_edge in turns.items():
            vol = demand[f"{leg.upper()}{m.upper()}"]
            total += vol
            if vol <= 0:
                continue
            rid = f"{leg}_{m}"
            ET.SubElement(routes, "route", {"id": rid, "edges": f"{entry} {exit_edge}"})
            ET.SubElement(routes, "flow", {
                "id": f"f_{rid}", "route": rid, "begin": "0", "end": "3600",
                "vehsPerHour": str(vol), "departLane": "best", "departSpeed": "max"})
    path = EE(f"demand_sw{tag}.rou.xml")
    ET.ElementTree(routes).write(path, encoding="UTF-8", xml_declaration=True)
    return path, total


def already_done(scale):
    if not Path(RESULTS_CSV).exists():
        return False
    with open(RESULTS_CSV) as f:
        for row in csv.DictReader(f):
            if abs(float(row["scale"]) - scale) < 1e-6:
                return True
    return False


def append_result(row):
    exists = Path(RESULTS_CSV).exists()
    with open(RESULTS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


def run_one(scale, steps=STEPS, eval_freq=EVAL_FREQ):
    tag = f"{int(round(scale * 100)):03d}"
    print("=" * 72, flush=True)
    print(f"SCALE {scale} (tag sw{tag}), steps={steps}", flush=True)
    print("=" * 72, flush=True)

    route = EE(f"demand_sw{tag}.rou.xml")
    FIX = EE(f"ctrl_pp_fixed_sw{tag}.add.xml")
    ACT = EE(f"ctrl_pp_act_sw{tag}.add.xml")
    tuning_cache = EE(f"sw{tag}_tuning.json")

    if all(Path(p).exists() for p in (route, FIX, ACT, tuning_cache)):
        info = json.loads(Path(tuning_cache).read_text())
        total, Y, f_m, f_sd, a_m, a_sd, C_best = (
            info["total"], info["Y"], info["f_m"], info["f_sd"],
            info["a_m"], info["a_sd"], info["C_best"])
        print(f"  [cached tuning] total {total} veh/hr, Y={Y:.3f}, "
              f"fixed {f_m:.2f}+-{f_sd:.2f}  actuated {a_m:.2f}+-{a_sd:.2f}", flush=True)
    else:
        base_demand = S.hour_demand(BASE_HOUR)
        demand = scale_demand(base_demand, scale)
        route, total = write_scaled_routes(tag, demand)

        tlid, link, greens, through_lanes = S.net_parts()
        ys, Y, C, g = S.webster(demand, greens, link, through_lanes)
        print(f"  total {total} veh/hr, Y={Y:.3f}, Webster cycle={C}s", flush=True)

        print("  tuning fixed-time...", flush=True)
        fm, fsd, fn, C_best, g_best = S.sweep_fixed(
            route, tlid, greens, ys, C, f"sw{tag}",
            mults=(0.7, 0.85, 1.0, 1.15, 1.3), seeds=(1, 2))
        g = g_best
        S.write_program(EE(f"ctrl_pp_fixed_sw{tag}.add.xml"), tlid, greens, g, f"fxsw{tag}")

        print("  tuning actuated...", flush=True)
        m, sd, n, min_dur, max_mult, det_gap = S.sweep_actuated(
            route, tlid, greens, g, f"sw{tag}",
            min_durs=(5, 10), max_mults=(1.25, 1.5), det_gaps=(2.0, 3.0), seeds=(1, 2))
        mins = tuple(min(min_dur, int(d)) for d in g)
        S.write_program(EE(f"ctrl_pp_act_sw{tag}.add.xml"), tlid, greens, g, f"acsw{tag}",
                        actuated=True, mins=mins, max_mult=max_mult, det_gap=det_gap)

        fix_runs = [S.run_sumo(route, FIX, s, f"fixsw{tag}") for s in S.SEEDS]
        act_runs = [S.run_sumo(route, ACT, s, f"actsw{tag}") for s in S.SEEDS]
        f_m, f_sd, f_n = S.summarise(fix_runs)
        a_m, a_sd, a_n = S.summarise(act_runs)
        print(f"  fixed {f_m:.2f}+-{f_sd:.2f}  actuated {a_m:.2f}+-{a_sd:.2f}", flush=True)

        Path(tuning_cache).write_text(json.dumps({
            "total": total, "Y": Y, "C_best": C_best,
            "f_m": f_m, "f_sd": f_sd, "a_m": a_m, "a_sd": a_sd}))

    def make_env(**extra):
        return sumo_rl.SumoEnvironment(
            net_file=S.NET, route_file=route, single_agent=True, use_gui=False,
            num_seconds=3600, delta_time=5, yellow_time=3, min_green=5, max_green=40,
            reward_fn="diff-waiting-time", **extra)

    best_dir = EE(f"best_sw{tag}")
    ckpt_path = EE(f"dqn_sw{tag}_ckpt")
    progress_path = EE(f"sw{tag}_progress.json")

    done_steps = 0
    model = None
    if Path(progress_path).exists() and Path(ckpt_path + ".zip").exists():
        done_steps = json.loads(Path(progress_path).read_text())["done_steps"]
        if done_steps < steps:
            print(f"  resuming training from {done_steps}/{steps} steps", flush=True)
            model = DQN.load(ckpt_path, env=Monitor(make_env()))

    remaining = steps - done_steps
    if remaining > 0:
        if model is None:
            model = DQN("MlpPolicy", Monitor(make_env()),
                        learning_rate=1e-3, buffer_size=100_000, learning_starts=2_000,
                        batch_size=64, gamma=0.99, exploration_fraction=0.4,
                        exploration_final_eps=0.03, train_freq=1,
                        target_update_interval=1_000, verbose=0, seed=42)
        evalcb = EvalCallback(Monitor(make_env()), best_model_save_path=best_dir,
                              eval_freq=eval_freq, n_eval_episodes=4,
                              deterministic=True, verbose=0)
        resumecb = ResumeCheckpoint(ckpt_path, progress_path, eval_freq)
        print(f"  training DQN {remaining} more steps (of {steps} total)...", flush=True)
        model.learn(total_timesteps=remaining, reset_num_timesteps=False,
                   callback=[evalcb, resumecb])
        model.save(ckpt_path)
        Path(progress_path).write_text(json.dumps({"done_steps": steps}))

    best = DQN.load(EE(f"best_sw{tag}/best_model"))

    def eval_rl(seed):
        trip = EE(f"sc_rlsw{tag}_s{seed}.xml")
        env = make_env(sumo_seed=seed,
                       additional_sumo_cmd=f"--tripinfo-output {trip} --no-warnings true")
        obs, _ = env.reset()
        done = False
        while not done:
            a, _ = best.predict(obs, deterministic=True)
            obs, r, term, trunc, _ = env.step(int(a))
            done = term or trunc
        end = env.sim_step
        env.close()
        if end < 3500:
            raise RuntimeError(f"scale {scale} seed {seed}: ended at {end}s -- not a valid result")
        return S.avg_wait(trip)

    rl_runs = [eval_rl(s) for s in S.SEEDS]
    rl_m, rl_sd, rl_n = S.summarise(rl_runs)
    collapses = sum(1 for w, _ in rl_runs if w > 2 * min(w2 for w2, _ in rl_runs))

    print(f"  RL {rl_m:.2f}+-{rl_sd:.2f}  collapses {collapses}/5", flush=True)
    print(f"  RL vs fixed: {100 * (rl_m - f_m) / f_m:+.1f}%", flush=True)

    append_result({
        "scale": scale, "demand_veh_hr": total, "saturation_Y": round(Y, 4),
        "fixed_mean": round(f_m, 2), "fixed_sd": round(f_sd, 2),
        "actuated_mean": round(a_m, 2), "actuated_sd": round(a_sd, 2),
        "rl_mean": round(rl_m, 2), "rl_sd": round(rl_sd, 2),
        "rl_collapses": collapses,
        "rl_vs_fixed_pct": round(100 * (rl_m - f_m) / f_m, 1),
        "rl_vs_act_pct": round(100 * (rl_m - a_m) / a_m, 1),
        "fixed_cycle_s": C_best,
    })


def retrain_verify(scale, train_seed, steps=STEPS, eval_freq=EVAL_FREQ):
    """Retrain RL only (reusing an already-tuned scale's route/baselines) with a
    different training seed, to check whether a surprising result was a real
    effect or a one-off training collapse. Logs to a separate CSV so it never
    mixes with the official sweep.
    """
    tag = f"{int(round(scale * 100)):03d}"
    route = EE(f"demand_sw{tag}.rou.xml")
    FIX = EE(f"ctrl_pp_fixed_sw{tag}.add.xml")
    ACT = EE(f"ctrl_pp_act_sw{tag}.add.xml")
    print(f"VERIFY scale {scale} (tag sw{tag}) with train_seed={train_seed}", flush=True)

    def make_env(**extra):
        return sumo_rl.SumoEnvironment(
            net_file=S.NET, route_file=route, single_agent=True, use_gui=False,
            num_seconds=3600, delta_time=5, yellow_time=3, min_green=5, max_green=40,
            reward_fn="diff-waiting-time", **extra)

    best_dir = EE(f"best_sw{tag}_vs{train_seed}")
    evalcb = EvalCallback(Monitor(make_env()), best_model_save_path=best_dir,
                          eval_freq=eval_freq, n_eval_episodes=4,
                          deterministic=True, verbose=0)
    model = DQN("MlpPolicy", Monitor(make_env()),
                learning_rate=1e-3, buffer_size=100_000, learning_starts=2_000,
                batch_size=64, gamma=0.99, exploration_fraction=0.4,
                exploration_final_eps=0.03, train_freq=1,
                target_update_interval=1_000, verbose=0, seed=train_seed)
    print(f"  training DQN {steps} steps (seed {train_seed})...", flush=True)
    model.learn(total_timesteps=steps, callback=evalcb)

    best = DQN.load(EE(f"best_sw{tag}_vs{train_seed}/best_model"))

    def eval_rl(seed):
        trip = EE(f"sc_rlsw{tag}vs{train_seed}_s{seed}.xml")
        env = make_env(sumo_seed=seed,
                       additional_sumo_cmd=f"--tripinfo-output {trip} --no-warnings true")
        obs, _ = env.reset()
        done = False
        while not done:
            a, _ = best.predict(obs, deterministic=True)
            obs, r, term, trunc, _ = env.step(int(a))
            done = term or trunc
        end = env.sim_step
        env.close()
        if end < 3500:
            raise RuntimeError(f"verify scale {scale} seed {seed}: ended at {end}s")
        return S.avg_wait(trip)

    rl_runs = [eval_rl(s) for s in S.SEEDS]
    rl_m, rl_sd, rl_n = S.summarise(rl_runs)
    print(f"  VERIFY RESULT scale={scale} train_seed={train_seed}: RL {rl_m:.2f}+-{rl_sd:.2f}", flush=True)

    verify_csv = EE("demand_sweep_verify.csv")
    row = {"scale": scale, "train_seed": train_seed, "rl_mean": round(rl_m, 2), "rl_sd": round(rl_sd, 2)}
    exists = Path(verify_csv).exists()
    with open(verify_csv, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists:
            w.writeheader()
        w.writerow(row)


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] == "--verify":
        scale = float(args[1])
        train_seed = int(args[2])
        steps = int(args[3]) if len(args) > 3 else STEPS
        eval_freq = int(args[4]) if len(args) > 4 else EVAL_FREQ
        retrain_verify(scale, train_seed, steps=steps, eval_freq=eval_freq)
        sys.exit(0)

    targets = SCALES
    steps, eval_freq = STEPS, EVAL_FREQ
    if args:
        targets = [float(args[0])]
        if len(args) > 1:
            steps = int(args[1])
        if len(args) > 2:
            eval_freq = int(args[2])

    for scale in targets:
        if already_done(scale):
            print(f"scale {scale} already in {RESULTS_CSV}, skipping")
            continue
        run_one(scale, steps=steps, eval_freq=eval_freq)

    print("\nDone. Results in", RESULTS_CSV)
