"""The world: ticks, scripted events, scanner/supplier behaviour and commander commands."""
from agents import Coordinator, Drone
from planning import BASE_POS, a_star_route, boustrophedon_path, get_distance, route_is_clear
from scenario import Scenario

SCAN_DWELL = 2      # ticks a scanner hovers over a zone
DELIVER_DWELL = 2   # ticks a supplier spends dropping aid


class Simulation:
    def __init__(self):
        self.reset()

    def reset(self):
        self.sc = Scenario()
        self.zones = self.sc.get_initial_state()
        self.zmap = {z["id"]: z for z in self.zones}
        self.tick = 0
        self.comms = "normal"
        self.blackout_until = 0
        self.log = []
        self.complete = False
        self.coord = Coordinator()
        # Lawnmower: 7 scanners, each owns a 2-column strip and sweeps it row by row, alternating direction
        cols = sorted({z["lng"] for z in self.zones}); rows = sorted({z["lat"] for z in self.zones})
        by = {(z["lat"], z["lng"]): z["id"] for z in self.zones}
        per = len(cols) // 7
        self.queues, self.drones = {}, []
        for i in range(7):
            sc = cols[i * per:(i + 1) * per]
            self.queues[f"S{i+1}"] = [by[(lat, lng)] for r, lat in enumerate(rows) for lng in (sc if r % 2 == 0 else sc[::-1])]
            self.drones.append(Drone(f"S{i+1}", "scanner", BASE_POS[0], sc[0]))
        self.drones += [Drone("U1", "supplier", *BASE_POS), Drone("U2", "supplier", *BASE_POS)]
        self.say("Mission started: 7 scanners (lawnmower strips) and 2 suppliers")

    # ---------- helpers ----------
    def drone(self, did):
        return next(d for d in self.drones if d.id == did)

    def say(self, msg):
        self.log.append(f"Tick {self.tick}: {msg}")

    def _blocked(self):
        return [z["id"] for z in self.zones if z["status"] == "blocked"]

    def _pos(self, zid):
        z = self.zmap[zid]
        return (z["lat"], z["lng"])

    # ---------- main loop ----------
    def update(self):
        self.tick += 1
        sc = self.sc
        if self.tick == sc.block_tick:
            self._block(sc.block_zone_id)
        if self.tick == sc.battery_tick:
            self._low_battery(sc.battery_drone)
        if self.tick == sc.blackout_tick:
            self._start_blackout()
        if self.comms == "blackout" and self.tick >= self.blackout_until:
            self.comms = "normal"
            self.say("COMMS restored - executing queued commands")
            for p in list(self.coord.pending):
                if p.get("queued"):
                    self._execute(p)
        for d in self.drones:
            (self._step_scanner if d.type == "scanner" else self._step_supplier)(d)
        if not self.complete and all(z["status"] != "unscanned" for z in self.zones):
            self.complete = True
            self.say(f"Sweep complete - {len(self._blocked())} zone(s) blocked and skipped")

    # ---------- scripted events ----------
    def _start_blackout(self):
        if self.comms == "blackout":
            return
        self.comms = "blackout"
        self.blackout_until = self.tick + self.sc.blackout_len
        self.say("COMMS blackout - commands will be queued, drones continue autonomously")

    def _block(self, zid):
        self.zmap[zid]["status"] = "blocked"
        self.say(f"ALERT: {zid} became BLOCKED")
        bpos = [self._pos(b) for b in self._blocked()]
        for d in self.drones:
            if not d.target or d.status not in ("scanning", "delivering"):
                continue
            if d.target == zid:
                self.say(f"{d.id} rerouted, {zid} blocked")
                d.dwell = 0
                if d.type == "scanner":
                    self._assign_next(d)
                else:
                    self._send_home(d)
            elif not route_is_clear((d.lat, d.lng), d.waypoints, bpos):
                route = a_star_route((d.lat, d.lng), d.target, self._blocked(), self.zones)
                if route:
                    d.waypoints = route
                    self.say(f"{d.id} rerouted, {zid} blocked")

    def _low_battery(self, did):
        d = self.drone(did)
        d.battery = 15.0
        self.say(f"{d.id} low battery (15%) - returning to base")
        remaining = [z for z in ([d.target] if d.target else []) + self.queues[d.id]
                     if self.zmap[z]["status"] == "unscanned"]
        self.queues[d.id] = []
        others = [s for s in self.drones if s.type == "scanner" and s is not d
                  and s.status not in ("grounded", "returning")]
        other = min(others, key=lambda s: get_distance((s.lat, s.lng), (d.lat, d.lng)), default=None)
        if other and remaining:
            self.queues[other.id] += remaining
            if other.status == "done":
                other.status = "idle"
            self.say(f"{other.id} takes over {', '.join(remaining)} from {d.id}")
        d.dwell = 0
        self._send_home(d, final="grounded")

    # ---------- commander ----------
    def handle_command(self, cmd):
        if not isinstance(cmd, dict):
            return
        t = cmd.get("type")
        if t in ("approve", "override"):
            p = next((p for p in self.coord.pending if p["id"] == cmd.get("id")), None)
            if not p:
                return
            if t == "override":
                if cmd.get("target_zone") not in self.zmap:
                    return
                p["target_zone"] = cmd["target_zone"]
                p["overridden"] = True
            if self.comms == "blackout":
                if not p.get("queued"):
                    p["queued"] = True
                    self.say(f"{p['id']} approved -> {p['target_zone']} (queued during blackout)")
                return
            self._execute(p)
        elif t == "trigger" and cmd.get("event") == "blackout":
            self._start_blackout()

    def _execute(self, p):
        self.coord.pending.remove(p)
        self.drone(p["drone_id"]).deliveries.append(p["target_zone"])
        if p.get("overridden"):
            self.say(f"Commander: {p['id']} OVERRIDDEN to {p['target_zone']} ({p['drone_id']})")
        else:
            self.say(f"Commander approved {p['id']}: {p['drone_id']} -> {p['target_zone']}")

    # ---------- scanners ----------
    def _assign_next(self, d):
        q, blocked = self.queues[d.id], self._blocked()
        while True:
            q[:] = [z for z in q if self.zmap[z]["status"] == "unscanned"]
            if not q:
                d.target, d.waypoints, d.status = None, [], "done"
                return False
            zid = q.pop(0)          # strict lawnmower order
            route = a_star_route((d.lat, d.lng), zid, blocked, self.zones)
            if route:
                d.target, d.waypoints, d.dwell, d.status = zid, route, 0, "scanning"
                return True
            self.say(f"{d.id} cannot reach {zid}, skipping")

    def _step_scanner(self, d):
        if d.status in ("grounded", "done"):
            return
        if d.status == "returning":
            if d.move():
                d.lat, d.lng = BASE_POS
                d.status = d.final_status if hasattr(d, "final_status") else "grounded"
                self.say(f"{d.id} landed at base ({d.status})")
            return
        if d.status == "idle" and not self._assign_next(d):
            return
        if d.dwell > 0:
            d.dwell -= 1
            if d.dwell == 0:
                self._finish_scan(d)
        elif d.move():
            d.dwell = SCAN_DWELL

    def _finish_scan(self, d):
        zid, z = d.target, self.zmap[d.target]
        if zid in self.sc.survivor_zones:
            z["status"] = "survivor_found"
            self.say(f"{d.id} scanned {zid}: SURVIVOR detected")
            sup = self.coord.pick_supplier(self.drones, self._pos(zid))
            if sup:
                self.say(self.coord.propose(self.tick, sup.id, "deliver", zid, f"Survivor found in {zid}"))
            else:
                self.say(f"No supplier available for {zid}")
        else:
            z["status"] = "scanned"
            self.say(f"{d.id} scanned {zid}")
        d.target = None
        d.status = "idle"
        self._assign_next(d)

    # ---------- suppliers ----------
    def _send_home(self, d, final="idle"):
        d.waypoints = a_star_route((d.lat, d.lng), "BASE", self._blocked(), self.zones) or [BASE_POS]
        d.target, d.status = None, "returning"
        d.final_status = final

    def _start_delivery(self, d):
        while d.deliveries:
            zid = d.deliveries.pop(0)
            route = a_star_route((d.lat, d.lng), zid, self._blocked(), self.zones)
            if route:
                d.target, d.waypoints, d.dwell, d.status = zid, route, 0, "delivering"
                return
            self.say(f"{d.id} cannot reach {zid} (blocked)")

    def _step_supplier(self, d):
        if d.status == "idle" and d.deliveries:
            self._start_delivery(d)
        if d.status == "delivering":
            if d.dwell > 0:
                d.dwell -= 1
                if d.dwell == 0:
                    self.zmap[d.target]["aided"] = True
                    self.say(f"{d.id} delivered aid to {d.target}")
                    d.target, d.status = None, "idle"
                    self._start_delivery(d)
                    if d.status != "delivering":
                        self._send_home(d)
            elif d.move():
                d.dwell = DELIVER_DWELL
        elif d.status == "returning" and d.move():
            d.lat, d.lng = BASE_POS
            d.status = "idle"

    # ---------- output ----------
    def get_state(self):
        return {
            "tick": self.tick, "comms": self.comms,
            "base": {"lat": BASE_POS[0], "lng": BASE_POS[1]},
            "drones": [{"id": d.id, "type": d.type, "lat": round(d.lat, 6), "lng": round(d.lng, 6),
                        "battery": round(max(d.battery, 0), 1), "status": d.status, "target": d.target,
                        "route": [list(w) for w in d.waypoints]} for d in self.drones],
            "zones": [dict(z) for z in self.zones],
            "pending": [dict(p) for p in self.coord.pending],
            "log": list(reversed(self.log[-40:])),
        }
