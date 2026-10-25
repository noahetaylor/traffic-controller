"""Build one hour's demand + matched fixed-time and actuated baselines.

    python build_scenario.py 13        # midday
    python build_scenario.py 17        # PM peak
    python build_scenario.py 8         # AM -- should reproduce 23.60 / 23.81

Writes demand_{hh}.rou.xml, ctrl_pp_fixed_{hh}.add.xml, ctrl_pp_act_{hh}.add.xml
and prints both baselines as mean +/- sd over 5 seeds.
"""

import sys
from ee_paths import EE
import scenario_lib as S

hour = int(sys.argv[1]) if len(sys.argv) > 1 else 8
hh = f"{hour:02d}"

tlid, link, greens, through_lanes = S.net_parts()
demand = S.hour_demand(hour)
route, total = S.write_routes(hour, demand)

nb, sb = sum(demand[f"S{m}"] for m in "LTR"), sum(demand[f"N{m}"] for m in "LTR")
print("=" * 72)
print(f"SCENARIO {hh}:00 — {total} veh/hr")
print("=" * 72)
print(f"  northbound {nb}  southbound {sb}   NB/SB = {nb/max(sb,1):.2f}")
print(f"  demand: {demand}")
print(f"  wrote {route}")

ys, Y, C, g = S.webster(demand, greens, link, through_lanes)
print(f"\n  Webster: Y={Y:.3f}  cycle={C}s  greens={g}")
print(f"  phase flow ratios: " + "  ".join(f"{y:.3f}" for y in ys))
for st, y, d in zip(greens, ys, g):
    print(f"    {st}  y={y:.3f}  green={d}s   serves {' '.join(sorted(S.served(st, link)))}")

print(f"\n  Tuning the fixed-time cycle around Webster's {C}s:")
fm, fsd, fn, C_best, g_best = S.sweep_fixed(route, tlid, greens, ys, C, hh)
print(f"  BEST fixed: cycle {C_best}s greens {g_best}")
g = g_best
FIX = S.write_program(EE(f"ctrl_pp_fixed_{hh}.add.xml"), tlid, greens, g, f"fx{hh}")
print(f"  wrote {FIX}")

print(f"\n  Tuning actuated (so the baseline is not handicapped):")
m, sd, n, min_dur, max_mult, det_gap = S.sweep_actuated(route, tlid, greens, g, hh)
mins = tuple(min(min_dur, int(d)) for d in g)
ACT = S.write_program(EE(f"ctrl_pp_act_{hh}.add.xml"), tlid, greens, g, f"ac{hh}",
                      actuated=True, mins=mins, max_mult=max_mult, det_gap=det_gap)
print(f"  BEST actuated: minDur={min_dur} maxMult={max_mult} detGap={det_gap}")
print(f"  wrote {ACT}")

print(f"\n  Evaluating both baselines over seeds {S.SEEDS}:\n")
results = {}
for label, addf, tag in [("fixed-time (Webster)", FIX, f"fix{hh}"),
                         ("actuated (tuned)", ACT, f"act{hh}")]:
    runs = [S.run_sumo(route, addf, s, tag) for s in S.SEEDS]
    results[label] = S.summarise(runs)
    print(f"    {label:<24} " + "  ".join(f"{w:6.2f}s" for w, _ in runs))

print("\n" + "=" * 72)
print(f"{hh}:00 BASELINES ({total} veh/hr)")
print("=" * 72)
print(f"  {'controller':<24} {'mean':>8} {'sd':>7} {'mean n':>8}")
for label, (m_, sd_, n_) in results.items():
    print(f"  {label:<24} {m_:7.2f}s {sd_:6.2f}s {n_:8.0f}")

f_m = results["fixed-time (Webster)"][0]
a_m = results["actuated (tuned)"][0]
print(f"\n  actuated vs fixed: {100*(a_m-f_m)/f_m:+.1f}%")
print(f"  (AM peak reference: fixed 23.60s, actuated 23.81s, +0.9% -- tied at Y=0.724)")
print(f"\n  Next: python train_scenario.py {hour}")
