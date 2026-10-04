"""Drones and the Coordinator agent."""
from planning import get_distance

SPEED = 0.0006   # degrees per tick
DRAIN = 0.1      # battery % lost per tick spent flying


class Drone:
    def __init__(self, id, type, lat, lng):
        self.id = id
        self.type = type            # "scanner" or "supplier"
        self.lat = lat
        self.lng = lng
        self.battery = 100.0
        self.status = "idle"
        self.target = None          # zone id the drone is working on
        self.waypoints = []         # remaining (lat, lng) points on its route
        self.dwell = 0              # ticks left scanning at the current zone
        self.deliveries = []        # approved zone ids a supplier still has to serve

    def move(self):
        """Fly one tick along the route. True when the route is finished."""
        if not self.waypoints:
            return True
        tlat, tlng = self.waypoints[0]
        dist = get_distance((self.lat, self.lng), (tlat, tlng))
        self.battery -= DRAIN
        if dist <= SPEED:                      # arrive exactly, never overshoot
            self.lat, self.lng = tlat, tlng
            self.waypoints.pop(0)
            return not self.waypoints
        self.lat += (tlat - self.lat) / dist * SPEED
        self.lng += (tlng - self.lng) / dist * SPEED
        return False


class Coordinator:
    """Proposes actions and waits for the commander. Never acts on its own."""

    def __init__(self):
        self.pending = []
        self._counter = 0

    def pick_supplier(self, drones, zone_pos):
        """Nearest idle supplier that has no open proposal; falls back to nearest overall."""
        suppliers = [d for d in drones if d.type == "supplier" and d.status != "grounded"]
        reserved = {p["drone_id"] for p in self.pending}
        free = [d for d in suppliers
                if d.status == "idle" and not d.deliveries and d.id not in reserved]
        pool = free or suppliers
        return min(pool, key=lambda d: get_distance((d.lat, d.lng), zone_pos))

    def propose(self, tick, drone_id, action, target_zone, reason):
        self._counter += 1
        pid = f"P{self._counter}"
        self.pending.append({"id": pid, "drone_id": drone_id, "action": action,
                             "target_zone": target_zone, "reason": reason})
        return f"Proposal {pid} created for {drone_id} -> {target_zone}"
