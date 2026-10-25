import sumolib
from ee_paths import EE
net = sumolib.net.readNet(EE("donmills.net.xml"))

lon, lat = -79.3434482925549, 43.7371733475081     # Don Mills & Lawrence E
x, y = net.convertLonLat2XY(lon, lat)

tls_nodes = [n for n in net.getNodes() if "traffic_light" in n.getType()]
def dist(n):
    nx, ny = n.getCoord(); return ((nx-x)**2 + (ny-y)**2) ** 0.5
target = min(tls_nodes, key=dist)

print("Target node:", target.getID(), "| distance from coords: %.1f m" % dist(target))
print("  incoming:", len(target.getIncoming()), "| outgoing:", len(target.getOutgoing()))

edges = sorted({e.getID() for e in target.getIncoming()} | {e.getID() for e in target.getOutgoing()})
print("  arm edges:", len(edges))
for eid in edges: print("   ", eid)

with open(EE("keep_edges.txt"),"w") as f:
    f.write("\n".join(edges))
print("Wrote keep_edges.txt")
