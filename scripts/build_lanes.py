import math, sumolib
from ee_paths import EE
net = sumolib.net.readNet(EE("donmills_clean.net.xml"))
j = net.getTrafficLights()[0].getID()
node = net.getNode(j)
jx, jy = node.getCoord()

# outward heading of each arm (from the current clean net)
head = {}
for e in list(node.getIncoming()) + list(node.getOutgoing()):
    o = e.getFromNode() if e.getToNode().getID()==node.getID() else e.getToNode()
    ox, oy = o.getCoord()
    ang = math.degrees(math.atan2(oy-jy, ox-jx))
    lab = min([("E",0),("N",90),("W",180),("W",-180),("S",-90)], key=lambda p: abs((ang-p[1]+180)%360-180))[0]
    head[lab] = ang
for lab in ("N","S","E","W"):
    head.setdefault(lab, {"N":90,"S":-90,"E":0,"W":180}[lab])

# lane plan per approach, from the raw turning split:
#   L% >=10 -> dedicated left lane; S leg R% =20.7 -> dedicated right lane
# lanes listed curb..median won't matter; we set counts + allowed movements via connections
plan = {   # (num_lanes, left_lanes, right_lanes)  through gets the middle lanes
  "N": (4, 1, 0),   # L 16.8% -> 1 left; 2 through; ... keep 4 for turn+through capacity
  "S": (4, 1, 1),   # L 14.3% + R 20.7% -> 1 left, 1 right, 2 through
  "E": (4, 1, 0),   # L 18.6% -> 1 left
  "W": (3, 0, 1),   # L only 7.6% (shared), R 13.4% -> 1 right, 2 through
}
ARM = 200.0; SPEED = 13.9
nodes = [f'<node id="C" x="{jx:.2f}" y="{jy:.2f}" type="traffic_light"/>']
edges = []
for lab in ("N","S","E","W"):
    a = math.radians(head[lab]); ex, ey = jx+ARM*math.cos(a), jy+ARM*math.sin(a)
    nlan = plan[lab][0]
    nodes.append(f'<node id="{lab}" x="{ex:.2f}" y="{ey:.2f}" type="priority"/>')
    edges.append(f'<edge id="{lab}_in"  from="{lab}" to="C" numLanes="{nlan}" speed="{SPEED}"/>')
    edges.append(f'<edge id="{lab}_out" from="C" to="{lab}" numLanes="{max(2,nlan-1)}" speed="{SPEED}"/>')

open(EE("dm.nod.xml"),"w").write("<nodes>\n"+"\n".join(nodes)+"\n</nodes>\n")
open(EE("dm.edg.xml"),"w").write("<edges>\n"+"\n".join(edges)+"\n</edges>\n")
print("Lane plan (approach -> in-lanes):", {k:v[0] for k,v in plan.items()})
print("Wrote dm.nod.xml + dm.edg.xml")
