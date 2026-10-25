import sumolib, math
from ee_paths import EE
net = sumolib.net.readNet(EE("donmills_iso.net.xml"))

tls_id = net.getTrafficLights()[0].getID()
j = net.getNode(tls_id)
jx, jy = j.getCoord()
ARM = 200.0   # metres, uniform arm length

# find the outward heading of each real arm, label by compass direction
dirs = {}
for e in list(j.getIncoming()) + list(j.getOutgoing()):
    other = e.getFromNode() if e.getToNode().getID()==j.getID() else e.getToNode()
    ox, oy = other.getCoord()
    ang = math.degrees(math.atan2(oy-jy, ox-jx))
    lab = min([("E",0),("N",90),("W",180),("W",-180),("S",-90)],
              key=lambda p: abs((ang-p[1]+180)%360-180))[0]
    dirs[lab] = ang
for lab in ("N","S","E","W"):
    dirs.setdefault(lab, {"N":90,"S":-90,"E":0,"W":180}[lab])

nodes, edges = [f'<node id="C" x="{jx:.2f}" y="{jy:.2f}" type="traffic_light"/>'], []
for lab in ("N","S","E","W"):
    a = math.radians(dirs[lab])
    ex, ey = jx+ARM*math.cos(a), jy+ARM*math.sin(a)
    nodes.append(f'<node id="{lab}" x="{ex:.2f}" y="{ey:.2f}" type="priority"/>')
    edges.append(f'<edge id="{lab}_in"  from="{lab}" to="C" numLanes="3" speed="13.9"/>')
    edges.append(f'<edge id="{lab}_out" from="C" to="{lab}" numLanes="3" speed="13.9"/>')

open(EE("dm.nod.xml"),"w").write("<nodes>\n"+"\n".join(nodes)+"\n</nodes>\n")
open(EE("dm.edg.xml"),"w").write("<edges>\n"+"\n".join(edges)+"\n</edges>\n")
print("Arms (deg):", {k:round(v) for k,v in dirs.items()})
print("Wrote dm.nod.xml + dm.edg.xml")
