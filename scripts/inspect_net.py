import sumolib
from ee_paths import EE
net = sumolib.net.readNet(EE("donmills.net.xml"))
tls_ids = [t.getID() for t in net.getTrafficLights()]
print("Total edges:", len(net.getEdges()), "| TLS nodes:", tls_ids)
main = max(net.getNodes(), key=lambda n: len(n.getIncoming()))
print("Busiest node:", main.getID(), "| type:", main.getType())
print("  incoming edges:", len(main.getIncoming()), "| outgoing edges:", len(main.getOutgoing()))
print("  signalized:", main.getID() in tls_ids)
