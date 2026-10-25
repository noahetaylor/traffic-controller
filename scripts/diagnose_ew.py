"""Diagnose the EW internal-lane emergency braking (Tracker Phase 1 / Decision #13).

Runs the fixed 4-phase protected program on AM demand with full warning capture,
then attributes every emergency-braking event to (a) the internal lane it happened
on, (b) the movement that lane serves, and (c) the signal phase that was green at
that moment. The fixed program is deterministic, so the phase is recoverable from
the cycle position -- no TraCI needed.

Also reports shared-lane structure on each approach, since a lane that serves both
a through and a protected-left movement stalls the through traffic behind it
whenever the left arrow is red.
"""

import subprocess, re, xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from ee_paths import EE

NET = EE("donmills_final.net.xml")
ROU = EE("am_peak.rou.xml")
ADD = EE("ctrl_prot.add.xml")
LOG = EE("ew_diag_warnings.txt")
TRIP = EE("ew_diag_tripinfo.xml")

# ---------- 1. network structure: connections, internal lanes, shared lanes ----------
net = ET.parse(NET).getroot()

link_of = {}          # linkIndex -> (fromEdge, toEdge, dir, viaLane, fromLane)
via_of = {}           # internal lane id -> linkIndex
lane_uses = defaultdict(list)   # "W_in_2" -> ["s", "l"]
for c in net.findall("connection"):
    if c.get("tl") is None:
        continue
    li = int(c.get("linkIndex"))
    fe, te, d = c.get("from"), c.get("to"), c.get("dir")
    via, fl = c.get("via"), c.get("fromLane")
    link_of[li] = (fe, te, d, via, fl)
    via_of[via] = li
    lane_uses[f"{fe}_{fl}"].append(d)

DIRNAME = {"s": "through", "l": "left", "r": "right"}
def movement(li):
    fe, te, d, _, _ = link_of[li]
    return f"{fe[0]}{d.upper()}"          # e.g. WT, WL, ES

int_len = {l.get("id"): float(l.get("length"))
           for l in net.iter("lane") if l.get("id", "").startswith(":")}

# ---------- 2. signal program: phase boundaries within one cycle ----------
prog = ET.parse(ADD).getroot().find("tlLogic")
phases = [(int(float(p.get("duration"))), p.get("state")) for p in prog.findall("phase")]
CYCLE = sum(d for d, _ in phases)
bounds, t = [], 0
for i, (d, s) in enumerate(phases):
    bounds.append((t, t + d, i, s))
    t += d

def phase_at(sim_time):
    x = sim_time % CYCLE
    for a, b, i, s in bounds:
        if a <= x < b:
            return i, s
    return len(phases) - 1, phases[-1][1]

def greens(state):
    return sorted({movement(i) for i, ch in enumerate(state) if ch in "Gg"})

print("=" * 70)
print(f"SIGNAL PROGRAM '{prog.get('programID')}' — cycle {CYCLE}s, {len(phases)} phases")
print("=" * 70)
for a, b, i, s in bounds:
    g = greens(s)
    kind = "YELLOW" if "y" in s else "GREEN "
    print(f"  phase {i}  {a:>3}-{b:<3}s  {kind}  {' '.join(g) if g else '(all red)'}")

# conflict check: any two simultaneously-green links that are physical foes
print("\nShared lanes (one lane serving more than one movement):")
shared = {k: v for k, v in lane_uses.items() if len(set(v)) > 1}
if not shared:
    print("  none")
for lane, dirs in sorted(shared.items()):
    print(f"  {lane}: {' + '.join(DIRNAME[d] for d in sorted(set(dirs)))}   <-- through traffic "
          f"queues behind a waiting {'left' if 'l' in dirs else 'right'}-turner")

# ---------- 3. run the sim, capturing every warning ----------
print("\nRunning fixed protected program on AM demand (3600 s)...")
with open(LOG, "w", encoding="utf-8") as f:
    subprocess.run(
        ["sumo", "-n", NET, "-r", ROU, "-a", ADD, "--end", "3600",
         "--tripinfo-output", TRIP, "--no-step-log", "true",
         "--collision.action", "warn", "--collision-output", EE("ew_diag_collisions.xml")],
        stdout=f, stderr=subprocess.STDOUT, check=False)

# ---------- 4. attribute each braking event ----------
BRAKE = re.compile(
    r"Vehicle '(?P<veh>[^']+)' performs (?P<kind>emergency braking|emergency stop)"
    r"[^']*on lane '(?P<lane>[^']+)'.*?decel=(?P<decel>[\d.]+).*?time=(?P<time>[\d.]+)")

by_lane, by_phase, by_flow, sev = Counter(), Counter(), Counter(), []
teleports = collisions = 0
events = []
for line in open(LOG, encoding="utf-8", errors="ignore"):
    if "teleport" in line.lower():
        teleports += 1
    if "collision" in line.lower():
        collisions += 1
    m = BRAKE.search(line)
    if not m:
        continue
    lane, tm = m.group("lane"), float(m.group("time"))
    ph, st = phase_at(tm)
    by_lane[lane] += 1
    by_phase[ph] += 1
    by_flow[m.group("veh").split(".")[0]] += 1
    sev.append(float(m.group("decel")))
    events.append((tm, lane, ph))

n_trips = len(ET.parse(TRIP).findall("tripinfo"))
total = sum(by_lane.values())

print("\n" + "=" * 70)
print("EMERGENCY BRAKING")
print("=" * 70)
print(f"  events: {total}   over {n_trips} completed vehicles "
      f"({100*total/max(n_trips,1):.2f}% of vehicles)")
print(f"  teleports: {teleports}   collision lines: {collisions}")
if sev:
    print(f"  decel: mean {sum(sev)/len(sev):.2f}  max {max(sev):.2f} m/s^2")

print("\n  by lane (top 10):")
for lane, n in by_lane.most_common(10):
    if lane in via_of:
        li = via_of[lane]
        fe, te, d, _, fl = link_of[li]
        tag = f"{movement(li):<3} {fe}_{fl} -> {te}  ({DIRNAME[d]}, internal, {int_len.get(lane,0):.1f} m)"
    else:
        tag = "approach lane" if not lane.startswith(":") else "internal"
    print(f"    {lane:<12} {n:>5}   {tag}")

print("\n  by signal phase during which it occurred:")
for ph, n in sorted(by_phase.items()):
    a, b, _, s = bounds[ph]
    g = greens(s)
    kind = "yellow" if "y" in s else "green"
    print(f"    phase {ph} ({a:>3}-{b:<3}s, {kind:<6} {' '.join(g) if g else 'all-red':<20}) {n:>5}")

print("\n  by originating flow (top 8):")
for fl, n in by_flow.most_common(8):
    print(f"    {fl:<12} {n:>5}")

# ---------- 5. per-movement delay, to link braking back to the metric ----------
waits = defaultdict(list)
for t_ in ET.parse(TRIP).findall("tripinfo"):
    waits[t_.get("id").split(".")[0]].append(float(t_.get("waitingTime")))
print("\n  avg waitingTime by flow (worst 6):")
worst = sorted(((sum(v)/len(v), k, len(v)) for k, v in waits.items()), reverse=True)[:6]
for w, k, n in worst:
    print(f"    {k:<12} {w:>7.1f}s  over {n}")

print(f"\nFull SUMO log: {LOG}")
