"""Drones and the Coordinator agent."""
from planning import get_distance
SPEED = 0.0006
DRAIN = 0.1

class Drone:
    def __init__(self, id, type, lat, lng):
        self.id = id; self.type = type; self.lat = lat; self.lng = lng
        self.battery = 100.0; self.status = "idle"; self.target = None
        self.waypoints = []; self.dwell = 0; self.deliveries = []

    def move(self):
        if not self.waypoints: return True
        tlat, tlng = self.waypoints[0]
        dist = get_distance((self.lat, self.lng), (tlat, tlng))
        self.battery -= DRAIN
        if dist <= SPEED:
            self.lat, self.lng = tlat, tlng
            self.waypoints.pop(0)
            return not self.waypoints
        self.lat += (tlat - self.lat) / dist * SPEED
        self.lng += (tlng - self.lng) / dist * SPEED
        return False

class Coordinator:
    """Proposes actions and waits for the commander. Never acts on its own."""
    def __init__(self):
        self.pending = []; self._counter = 0

    def pick_supplier(self, drones, zone_pos):
        suppliers = [d for d in drones if d.type == "supplier" and d.status != "grounded"]
        reserved = {p["drone_id"] for p in self.pending}
        free = [d for d in suppliers if d.status == "idle" and not d.deliveries and d.id not in reserved]
        pool = free or suppliers
        if not pool: return None          # FIX: no crash when every supplier is grounded
        return min(pool, key=lambda d: get_distance((d.lat, d.lng), zone_pos))

    def propose(self, tick, drone_id, action, target_zone, reason):
        self._counter += 1
        pid = f"P{self._counter}"
        self.pending.append({"id": pid, "drone_id": drone_id, "action": action,
                             "target_zone": target_zone, "reason": reason})
        return f"Proposal {pid} created for {drone_id} -> {target_zone}"
