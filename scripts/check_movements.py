import sumolib
from ee_paths import EE
net = sumolib.net.readNet(EE("donmills_laned.net.xml"))
node = net.getNode(net.getTrafficLights()[0].getID())

# For each incoming approach, what movements (to which outgoing edge) are possible, and from which lanes?
dir_of = {"N_out":"to N","S_out":"to S","E_out":"to E","W_out":"to W"}
print("=== Movements available per approach ===")
for e in node.getIncoming():
    outs = {}
    for lane in e.getLanes():
        for conn in lane.getOutgoing():
            outedge = conn.getToLane().getEdge().getID()
            outs.setdefault(outedge, set()).add(lane.getIndex())
    print(f"\n{e.getID()} ({e.getLaneNumber()} lanes):")
    for oe, lanes in sorted(outs.items()):
        print(f"    -> {oe:6s} from lane(s) {sorted(lanes)}")

# Sanity: every approach should reach the 3 non-U-turn destinations
print("\n=== Reachability check (each approach should reach 3 others) ===")
outedges = {"N_in":{"E_out","S_out","W_out"}, "S_in":{"E_out","N_out","W_out"},
            "E_in":{"N_out","S_out","W_out"}, "W_in":{"N_out","S_out","E_out"}}
for e in node.getIncoming():
    reach = set()
    for lane in e.getLanes():
        for conn in lane.getOutgoing():
            reach.add(conn.getToLane().getEdge().getID())
    want = outedges.get(e.getID(), set())
    missing = want - reach
    print(f"  {e.getID()}: reaches {sorted(reach)}  {'OK' if not missing else 'MISSING '+str(sorted(missing))}")
