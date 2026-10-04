"""Simulation core: drones, zones, the tick loop, the scripted disaster and commander commands."""
from agents import Coordinator, Drone
from planning import BASE_POS, a_star_route, boustrophedon_path, route_is_clear
from scenario import Scenario

LOW_BATTERY = 20
DWELL_TICKS = 2       # ticks a scanner hovers over a zone to scan it
LOG_LINES = 15        # how many log lines go out in each state message


class Simulation:
    def __init__(self):
        self.scen = Scenario()
        self.zones = self.scen.get_initial_state()
        self.zmap = {z["id"]: z for z in self.zones}
        self.drones = [
            Drone("S1", "scanner", *BASE_POS),
            Drone("S2", "scanner", *BASE_POS),
            Drone("U1", "supplier", *BASE_POS),
            Drone("U2", "supplier", *BASE_POS),
        ]
        self.coord = Coordinator()
        self.tick = 0
        self.comms = "normal"
        self.blackout_until = 0
        self.held_commands = []
        self.log = []
        self.sweep_done = False
        full = boustrophedon_path(self.zones)
        cut = round(len(full) * 0.6)
        # S1 sweeps the first rows, S2 sweeps the rest starting from the far end
        self.assignments = {"S1": full[:cut], "S2": list(reversed(full[cut:]))}

    # ---------- small helpers ----------
    def reset(self):
        self.__init__()

    def drone(self, drone_id):
        return next(d for d in self.drones if d.id == drone_id)

    def _log(self, msg):
        self.log.append(f"Tick {self.tick}: {msg}")

    def _pos(self, d):
        return (d.lat, d.lng)

    def _zpos(self, zid):
        z = self.zmap[zid]
        return (z["lat"], z["lng"])

    def _blocked_ids(self):
        return [z["id"] for z in self.zones if z["status"] == "blocked"]

    # ---------- tick loop ----------
    def update(self):
        self.tick += 1
        self._scenario_events()
        self._update_comms()
        blocked = self._blocked_ids()
        for d in self.drones:
            self._check_battery(d, blocked)
            if d.status == "returning":
                if d.move():
                    d.status = "grounded"
                    self._log(f"{d.id} landed at base")
            elif d.status == "grounded":
                continue
            elif d.type == "scanner":
                self._scanner_step(d, blocked)
            else:
                self._supplier_step(d, blocked)
        if not self.sweep_done and all(z["status"] != "unscanned" for z in self.zones):
            self.sweep_done = True
            self._log("Sweep complete: every reachable zone has been scanned")

    # ---------- scripted disaster ----------
    def _scenario_events(self):
        sc = self.scen
        if self.tick == sc.block_tick:
            self._block_zone(sc.block_zone_id)
        if self.tick == sc.battery_tick:
            d = self.drone(sc.battery_drone)
            d.battery = 15.0
            self._log(f"{d.id} battery critical (15%)")
        if self.tick == sc.blackout_tick:
            self._start_blackout("scripted")

    def _block_zone(self, zid):
        self.zmap[zid]["status"] = "blocked"
        self._log(f"{zid} became BLOCKED")
        blocked = self._blocked_ids()
        bpos = [self._zpos(b) for b in blocked]
        for d in self.drones:
            if d.type == "scanner" and zid in self.assignments[d.id]:
                self.assignments[d.id].remove(zid)
                self._log(f"{d.id} dropped {zid} from its sweep")
            if d.status == "grounded" or not d.waypoints:
                continue
            if d.target == zid:
                d.waypoints, d.target, d.status = [], None, "idle"
                self._log(f"{d.id} aborted its trip to {zid} (blocked)")
                continue
            if route_is_clear(self._pos(d), d.waypoints, bpos):
                continue
            new = a_star_route(self._pos(d), d.waypoints[-1], blocked, self.zones)
            if new:
                d.waypoints = new
                self._log(f"{d.id} rerouted, {zid} blocked")
            elif d.status == "returning":
                d.waypoints = [BASE_POS]
            else:
                d.waypoints, d.target, d.status = [], None, "idle"
                self._log(f"{d.id} found no safe route, holding position")

    def _start_blackout(self, reason):
        was_down = self.comms == "blackout"
        self.blackout_until = max(self.blackout_until, self.tick + self.scen.blackout_len)
        self.comms = "blackout"
        if not was_down:
            self._log(f"COMMS BLACKOUT started ({reason}); drones continue on last orders")

    def _update_comms(self):
        if self.comms == "blackout" and self.tick >= self.blackout_until:
            self.comms = "normal"
            self._log("COMMS restored")
            held, self.held_commands = self.held_commands, []
            for cmd in held:
                self._apply_command(cmd)

    # ---------- agents ----------
    def _check_battery(self, d, blocked):
        if d.battery >= LOW_BATTERY or d.status in ("returning", "grounded"):
            return
        d.status, d.dwell, d.target = "returning", 0, None
        d.waypoints = a_star_route(self._pos(d), "BASE", blocked, self.zones) or [BASE_POS]
        self._log(f"{d.id} low battery ({int(d.battery)}%), returning to base")
        if d.type == "scanner":
            self._hand_over_sweep(d)

    def _hand_over_sweep(self, d):
        remaining = [z for z in self.assignments[d.id] if self.zmap[z]["status"] == "unscanned"]
        others = [o for o in self.drones
                  if o.type == "scanner" and o is not d and o.status not in ("returning", "grounded")]
        if not remaining or not others:
            return
        taker = min(others, key=lambda o: sum(
            self.zmap[z]["status"] == "unscanned" for z in self.assignments[o.id]))
        for z in remaining:
            if z not in self.assignments[taker.id]:
                self.assignments[taker.id].append(z)
        self.assignments[d.id] = []
        self._log(f"{taker.id} takes over {', '.join(remaining)} from {d.id}")

    def _next_zone(self, d):
        return next((z for z in self.assignments[d.id] if self.zmap[z]["status"] == "unscanned"), None)

    def _scanner_step(self, d, blocked):
        if d.dwell > 0:                               # hovering over a zone
            d.dwell -= 1
            if d.dwell == 0:
                self._finish_scan(d)
            return
        if not d.waypoints:                           # sense + decide: pick the next zone
            zid = self._next_zone(d)
            if zid is None:
                d.status, d.target = "idle", None
                return
            route = a_star_route(self._pos(d), zid, blocked, self.zones)
            if route is None:
                self.assignments[d.id].remove(zid)
                self._log(f"{d.id} cannot reach {zid}, skipping it")
                return
            d.target, d.status, d.waypoints = zid, "scanning", route
        if d.move():                                  # act
            d.dwell = DWELL_TICKS

    def _finish_scan(self, d):
        zid = d.target
        z = self.zmap[zid]
        z["status"] = "scanned"
        self._log(f"{d.id} scanned {zid}")
        if zid in self.scen.survivor_zones:
            z["status"] = "survivor_found"
            sup = self.coord.pick_supplier(self.drones, self._zpos(zid))
            msg = self.coord.propose(self.tick, sup.id, "deliver", zid, "Survivor found")
            self._log(msg + (" (queued during blackout)" if self.comms == "blackout" else ""))
        d.target = None

    def _supplier_step(self, d, blocked):
        if not d.waypoints:
            if not d.deliveries:
                d.status = "idle"
                return
            zid = d.deliveries.pop(0)
            route = a_star_route(self._pos(d), zid, blocked, self.zones)
            if route is None:
                self._log(f"{d.id} cannot reach {zid}, delivery cancelled")
                d.status = "idle"
                return
            d.target, d.status, d.waypoints = zid, "delivering", route
        if d.move():
            self.zmap[d.target]["status"] = "scanned"
            self._log(f"{d.id} delivered aid to {d.target}")
            d.target, d.status = None, "idle"

    # ---------- commander commands ----------
    def handle_command(self, cmd):
        try:
            ctype = cmd.get("type")
            if ctype in ("approve", "override") and self.comms == "blackout":
                if not any(h.get("type") == ctype and h.get("id") == cmd.get("id")
                           for h in self.held_commands):
                    self.held_commands.append(cmd)
                    self._log(f"{ctype} {cmd.get('id')} held until comms are restored")
                return
            self._apply_command(cmd)
        except Exception as e:  # never let a bad message crash the loop
            self._log(f"Command error: {e}")

    def _apply_command(self, cmd):
        ctype = cmd.get("type")
        if ctype == "approve":
            p = next((x for x in self.coord.pending if x["id"] == cmd.get("id")), None)
            if not p:
                return
            z, d = self.zmap.get(p["target_zone"]), next(
                (x for x in self.drones if x.id == p["drone_id"]), None)
            if not z or not d:
                return
            if z["status"] == "blocked":
                self._log(f"{p['id']} target {z['id']} is blocked; override it to another zone")
                return
            d.deliveries.append(z["id"])
            self.coord.pending.remove(p)
            self._log(f"Proposal {p['id']} APPROVED")
        elif ctype == "override":
            p = next((x for x in self.coord.pending if x["id"] == cmd.get("id")), None)
            z = self.zmap.get(cmd.get("target_zone"))
            if not p or not z:
                return
            if z["status"] == "blocked":
                self._log(f"Override of {p['id']} rejected: {z['id']} is blocked")
                return
            p["target_zone"] = z["id"]
            self._log(f"Proposal {p['id']} OVERRIDDEN to {z['id']}")
            self._apply_command({"type": "approve", "id": p["id"]})
        elif ctype == "trigger" and cmd.get("event") == "blackout":
            self._start_blackout("manual trigger")

    # ---------- state for the dashboard (the data contract) ----------
    def get_state(self):
        return {
            "tick": self.tick,
            "comms": self.comms,
            "drones": [
                {"id": d.id, "type": d.type, "lat": round(d.lat, 5), "lng": round(d.lng, 5),
                 "battery": int(d.battery), "status": d.status, "target": d.target}
                for d in self.drones
            ],
            "zones": [
                {"id": z["id"], "lat": z["lat"], "lng": z["lng"],
                 "status": z["status"], "priority": z["priority"]}
                for z in self.zones
            ],
            "pending": [dict(p) for p in self.coord.pending],
            "log": self.log[-LOG_LINES:],
        }
