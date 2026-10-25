"""Shared machinery for building and evaluating a one-hour scenario.

Everything here was validated on the AM peak (08:00) in Session 5:
    fixed-time 23.60 s sd 0.29 | actuated 23.81 s sd 0.32 | DQN 28.57 s sd 0.96

Conventions that matter and must not drift between scenarios:
  * Phase STATES always come from the net's built-in programID "0"
    (protected-permissive). sumo-rl reads getAllProgramLogics(id)[0] and ignores
    add-file programs, so this is the only structure the RL agent can drive --
    the baselines are aligned to it so the comparison is apples-to-apples.
  * Only the durations are tuned per hour (Webster for fixed, swept for actuated).
  * Every number is a mean +/- sd over multiple SUMO seeds. A single run is not
    a result: the Session-3 model looked like 37.69 s on a lucky seed and was
    really bimodal (~32-39 s on 5/8 seeds, ~103-112 s on 3/8).
  * A truncated episode is discarded, never reported (one once produced a bogus
    14.76 s / n=259).
"""

import subprocess, statistics, itertools, xml.etree.ElementTree as ET
import pandas as pd
from ee_paths import EE

NET = EE("donmills_final.net.xml")
SEEDS = [1, 2, 3, 4, 5]
MODES = ["cars", "truck", "bus"]
DIRMAP = {"l": "L", "s": "T", "r": "R"}      # SUMO calls through 's'; counts call it 't'

# approach -> (entry edge, {turn: exit edge})
GEO = {"n": ("N_in", {"l": "E_out", "t": "S_out", "r": "W_out"}),
       "s": ("S_in", {"l": "W_out", "t": "N_out", "r": "E_out"}),
       "e": ("E_in", {"l": "S_out", "t": "W_out", "r": "N_out"}),
       "w": ("W_in", {"l": "N_out", "t": "E_out", "r": "S_out"})}


# ---------------------------------------------------------------- net structure
def net_parts():
    root = ET.parse(NET).getroot()
    tl0 = root.find("tlLogic")
    link = {int(c.get("linkIndex")): (c.get("from"), c.get("dir"), int(c.get("fromLane")))
            for c in root.findall("connection") if c.get("tl") is not None}
    greens = [p.get("state") for p in tl0.findall("phase")
              if not any(c in "yY" for c in p.get("state"))]
    through_lanes = {}
    for _, (fe, d, _fl) in link.items():
        if d == "s":
            through_lanes[fe[0]] = through_lanes.get(fe[0], 0) + 1
    return tl0.get("id"), link, greens, through_lanes


def served(state, link):
    """Movements getting a major green ('G') in this phase, e.g. {'NT','SR'}."""
    out = set()
    for i, ch in enumerate(state):
        if ch == "G" and i in link:
            fe, d, _fl = link[i]
            out.add(f"{fe[0]}{DIRMAP[d]}")
    return out


def lane_groups(state, link):
    """HCM-style lane groups for the phase: [(leg, movements, lanes), ...].

    Movements must be pooled when they SHARE a lane and kept separate when they
    do not, so capacity is neither under- nor over-stated. Both cases occur here:

      * S_in_0 serves right AND through -> at 17:00 that approach discharges
        ST 969 + SR 335 through the same 3 lanes (ratio 0.241, not 0.179).
      * E_in_0 is right-turn ONLY, while through uses lanes 1-2 -> pooling them
        would pretend through traffic has 3 lanes when it has 2 (0.187 vs 0.268).

    Treating lanes and movements as nodes and taking connected components gets
    both right without special-casing.
    """
    entries = []
    for i, ch in enumerate(state):
        if ch == "G" and i in link:
            fe, d, fl = link[i]
            entries.append((fe[0], fl, f"{fe[0]}{DIRMAP[d]}"))

    groups = []
    for leg in sorted({e[0] for e in entries}):
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        items = [e for e in entries if e[0] == leg]
        for _, fl, mv in items:
            union(("lane", fl), ("mv", mv))

        comps = {}
        for _, fl, mv in items:
            movements, lanes = comps.setdefault(find(("lane", fl)), (set(), set()))
            movements.add(mv)
            lanes.add(fl)
        for movements, lanes in comps.values():
            groups.append((leg, movements, lanes))
    return groups


# ---------------------------------------------------------------- demand
def hour_demand(hour):
    """Per-movement volumes for one clock hour, from the raw turning counts."""
    df = pd.read_csv(EE("don_mills_lawrence_raw.csv"))
    df["start_time"] = pd.to_datetime(df["start_time"])
    sub = df[df["start_time"].dt.hour == hour]
    if len(sub) < 4:
        raise ValueError(f"hour {hour}: only {len(sub)} 15-min bins, need 4")

    def mv(leg, m):
        return int(sub[[f"{leg}_appr_{md}_{m}" for md in MODES]].to_numpy().sum())

    return {f"{leg.upper()}{m.upper()}": mv(leg, m) for leg in "nsew" for m in "ltr"}


def write_routes(hour, demand):
    """Write demand_{hh}.rou.xml, one flow per turning movement."""
    hh = f"{hour:02d}"
    routes = ET.Element("routes")
    total = 0
    for leg, (entry, turns) in GEO.items():
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
    path = EE(f"demand_{hh}.rou.xml")
    ET.ElementTree(routes).write(path, encoding="UTF-8", xml_declaration=True)
    return path, total


# ---------------------------------------------------------------- signal programs
def webster(demand, greens, link, through_lanes, sat=1800.0, mins=(10, 6, 10, 6)):
    """Green splits for program 0's phases, from this hour's demand.

    The critical flow ratio for a phase is the worst LANE GROUP it serves (see
    lane_groups), not the worst individual movement.
    """
    def flow_ratio(state):
        y = 0.0
        for _leg, movements, lanes in lane_groups(state, link):
            vol = sum(demand.get(mv, 0) for mv in movements)
            y = max(y, vol / (sat * max(len(lanes), 1)))
        return y

    ys = [flow_ratio(st) for st in greens]
    Y = sum(ys)
    L = 3 * len(greens)                                  # yellow per phase
    C = int(min(120, max(60, (1.5 * L + 5) / max(0.15, 1 - Y))))
    return ys, Y, C, splits_for_cycle(ys, C, L, mins)


def splits_for_cycle(ys, C, L, mins=(10, 6, 10, 6)):
    """Proportional green splits for a given cycle length, respecting minimums."""
    budget = C - L
    Y = sum(ys)
    g = [max(mins[k], round(budget * ys[k] / Y)) for k in range(len(ys))]

    slack = budget - sum(g)
    if slack:
        for k in sorted(range(len(g)), key=lambda k: ys[k], reverse=True):
            take = max(mins[k] - g[k], slack) if slack < 0 else slack
            g[k] += take
            slack -= take
            if slack == 0:
                break
    assert all(g[k] >= mins[k] for k in range(len(g))), f"green below minimum: {g}"
    assert sum(g) + L == C, f"splits {g} + lost {L} != cycle {C}"
    return g


def sweep_fixed(route, tlid, greens, ys, C_webster, hh, L=12,
                mults=(0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.15, 1.3, 1.5), seeds=(1, 2, 3)):
    """Tune the fixed-time cycle around Webster's value.

    Webster's formula gives a principled starting cycle, but applying it blindly
    can still leave the baseline under-tuned -- and an under-tuned baseline is
    exactly what made the original 54.24 s figure misleading. Sweeping the cycle
    gives fixed-time the same fair shot the actuated sweep gives actuated.
    """
    tmp = EE(f"ctrl_pp_fixed_tune_{hh}.add.xml")
    best = None
    for mult in mults:
        C = int(min(150, max(40, round(C_webster * mult))))
        try:
            g = splits_for_cycle(ys, C, L)
        except AssertionError:
            continue                       # cycle too short for the minimums
        write_program(tmp, tlid, greens, g, f"fx{hh}")
        runs = [run_sumo(route, tmp, s, f"fixsw_{hh}") for s in seeds]
        m, sd, n = summarise(runs)
        star = ""
        if best is None or m < best[0]:
            best = (m, sd, n, C, g)
            star = "  <-- best"
        print(f"    cycle {C:>4}s ({mult:>4}x) greens {str(g):<20} -> {m:7.2f}s "
              f"sd {sd:5.2f} n {n:.0f}{star}")
    return best


def write_program(path, tlid, greens, durations, prog_id, actuated=False,
                  mins=(10, 6, 10, 6), max_mult=1.25, det_gap=2.0):
    add = ET.Element("additional")
    p = ET.SubElement(add, "tlLogic",
                      {"id": tlid, "type": "actuated" if actuated else "static",
                       "programID": prog_id, "offset": "0"})
    if actuated:
        ET.SubElement(p, "param", {"key": "detector-gap", "value": str(det_gap)})
        ET.SubElement(p, "param", {"key": "show-detectors", "value": "false"})
    for k, st in enumerate(greens):
        attrs = {"duration": str(int(durations[k])), "state": st}
        if actuated:
            attrs.update({"minDur": str(min(mins[k], int(durations[k]))),
                          "maxDur": str(int(durations[k] * max_mult))})
        ET.SubElement(p, "phase", attrs)
        ET.SubElement(p, "phase", {"duration": "3",
                                   "state": "".join("y" if c in "Gg" else "r" for c in st)})
    w = ET.SubElement(add, "WAUT", {"id": "w", "refTime": "0", "startProg": prog_id})
    ET.SubElement(w, "wautSwitch", {"time": "0", "to": prog_id})
    ET.SubElement(add, "wautJunction", {"wautID": "w", "junctionID": tlid})
    ET.ElementTree(add).write(path, encoding="UTF-8", xml_declaration=True)
    return path


# ---------------------------------------------------------------- evaluation
def avg_wait(trip):
    tr = ET.parse(trip).findall("tripinfo")
    w = [float(x.get("waitingTime")) for x in tr]
    return sum(w) / len(w), len(w)


def run_sumo(route, addfile, seed, tag):
    trip = EE(f"sc_{tag}_s{seed}.xml")
    cmd = ["sumo", "-n", NET, "-r", route, "--end", "3600", "--tripinfo-output", trip,
           "--no-step-log", "true", "--no-warnings", "true", "--seed", str(seed)]
    if addfile:
        cmd += ["-a", addfile]
    subprocess.run(cmd, check=True)
    return avg_wait(trip)


def summarise(runs):
    ws = [w for w, _ in runs]
    return (statistics.mean(ws),
            statistics.stdev(ws) if len(ws) > 1 else 0.0,
            statistics.mean([n for _, n in runs]))


def sweep_actuated(route, tlid, greens, durations, hh,
                   min_durs=(5, 10), max_mults=(1.25, 1.5, 2.0), det_gaps=(2.0, 3.0),
                   seeds=(1, 2, 3)):
    """Tune the actuated baseline so it is not accidentally handicapped."""
    tmp = EE(f"ctrl_pp_act_tune_{hh}.add.xml")
    best = None
    for min_dur, max_mult, det_gap in itertools.product(min_durs, max_mults, det_gaps):
        mins = tuple(min(min_dur, int(d)) for d in durations)
        write_program(tmp, tlid, greens, durations, f"ac{hh}", actuated=True,
                      mins=mins, max_mult=max_mult, det_gap=det_gap)
        runs = [run_sumo(route, tmp, s, f"actsw_{hh}") for s in seeds]
        m, sd, n = summarise(runs)
        print(f"    minDur={min_dur:<3} maxMult={max_mult:<5} detGap={det_gap:<4} "
              f"-> {m:7.2f}s sd {sd:5.2f} n {n:.0f}")
        if best is None or m < best[0]:
            best = (m, sd, n, min_dur, max_mult, det_gap)
    return best
