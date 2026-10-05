import math
from typing import List, Dict, Any, Optional, Tuple

# --- Geographic Constants (Chennai Coastline) ---
DISASTER_ZONE_POLYGON = [
    [13.35, 80.10], [13.30, 80.28], [13.15, 80.34], [12.95, 80.30],
    [12.78, 80.22], [12.72, 80.08], [12.85, 79.95], [13.05, 79.92],
    [13.25, 79.98], [13.35, 80.10]
]


def calculate_polygon_centroid(polygon: List[List[float]]) -> Tuple[float, float]:
    vertices = polygon[:-1] if polygon[0] == polygon[-1] else polygon
    area_twice = 0.0
    latitude_sum = 0.0
    longitude_sum = 0.0

    for index, (latitude, longitude) in enumerate(vertices):
        next_latitude, next_longitude = vertices[(index + 1) % len(vertices)]
        cross = longitude * next_latitude - next_longitude * latitude
        area_twice += cross
        latitude_sum += (latitude + next_latitude) * cross
        longitude_sum += (longitude + next_longitude) * cross

    if abs(area_twice) < 1e-12:
        raise ValueError("Cannot calculate centroid for a degenerate polygon")

    return latitude_sum / (3.0 * area_twice), longitude_sum / (3.0 * area_twice)


BASE_LAT, BASE_LNG = calculate_polygon_centroid(DISASTER_ZONE_POLYGON)

ZONE_LAT_MIN = min(point[0] for point in DISASTER_ZONE_POLYGON)
ZONE_LAT_MAX = max(point[0] for point in DISASTER_ZONE_POLYGON)
ZONE_LNG_MIN = min(point[1] for point in DISASTER_ZONE_POLYGON)
ZONE_LNG_MAX = max(point[1] for point in DISASTER_ZONE_POLYGON)
SWEEP_ROWS = 7
ARRIVAL_EPS = 0.05
AVOIDANCE_RADIUS = 0.15

WEATHER_PRESETS = {
    "Clear":  {"wind_speed": 5,  "visibility": 10.0, "rain_intensity": 0,  "risk_level": "Low",    "factor": 1.0},
    "Windy":  {"wind_speed": 28, "visibility": 8.0,  "rain_intensity": 10, "risk_level": "Medium", "factor": 1.2},
    "Foggy":  {"wind_speed": 10, "visibility": 1.5,  "rain_intensity": 5,  "risk_level": "Medium", "factor": 1.15},
    "Stormy": {"wind_speed": 45, "visibility": 2.0,  "rain_intensity": 80, "risk_level": "High",   "factor": 1.5}
}

NET_CYCLE = ["5G-Mesh", "4G-LTE", "LoRaWAN"]
SEVERITY_SCORES = {"Critical": 100, "High": 70, "Medium": 40, "Low": 20}


class Drone:
    def __init__(self, drone_id: str, drone_type: str, index: int):
        self.id = drone_id
        self.type = drone_type  # "Scanner" or "Supplier"
        self.index = index
        self.x = BASE_LNG
        self.y = BASE_LAT
        self.z = 0.0
        self.battery = 100.0
        self.status = "Redeploying" if drone_type == "Scanner" else "Idle"
        self.net = NET_CYCLE[index % 3] if drone_type == "Scanner" else "5G-Mesh"
        self.work_pct = 0.0
        self.target: Optional[Dict[str, float]] = None
        self.target_incident_id: Optional[str] = None
        self.assigned_strip_idx = index
        self.strip_min_lng = ZONE_LNG_MIN + index * (ZONE_LNG_MAX - ZONE_LNG_MIN) / 7
        self.strip_max_lng = ZONE_LNG_MIN + (index + 1) * (ZONE_LNG_MAX - ZONE_LNG_MIN) / 7
        self.sweep_dir = 1
        self.scan_tick = 0

        # Baseline drain configuration
        if drone_type == "Scanner":
            self.operating_z = 110.0 + (index * 3.0)
            self.z = self.operating_z
            self.base_drain = 0.90 if drone_id == "SCN-01" else round(0.25 + (index % 3) * 0.08, 2)
        else:
            self.operating_z = 70.0
            self.base_drain = 1.0

    def calculate_telemetry(self, weather_factor: float) -> Dict[str, Any]:
        drain = self.base_drain * weather_factor if self.status in ["Scanning", "Delivering Payload", "Returning to Base"] else 0.05
        vel = 0.0
        if self.status == "Scanning":
            vel = round(12.0 / weather_factor, 1)
        elif self.status == "Returning to Base":
            vel = round(9.0 / weather_factor, 1)
        elif self.status == "Delivering Payload":
            vel = round(8.0 / weather_factor, 1)

        remaining_uptime = round((self.battery / max(drain, 0.01)) * 0.8)
        work_rate = (100.0 / 60.0) / weather_factor
        eta = round(((100.0 - min(self.work_pct, 100.0)) / max(work_rate, 0.01)) * weather_factor * 0.8) if self.work_pct < 100 else 0

        return {
            "id": self.id,
            "type": self.type,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 1),
            "battery": round(self.battery, 1),
            "status": self.status,
            "net": self.net,
            "velocity": vel,
            "work_pct": round(self.work_pct, 1),
            "remaining_uptime_s": max(0, remaining_uptime),
            "eta_s": max(0, eta)
        }


class SimulationEngine:
    def __init__(self):
        self.reset()

    def reset(self):
        self.time_step = 0
        self.weather_preset = "Clear"
        self.obstacles: List[Dict[str, float]] = []
        self.alerts: List[str] = ["[SYSTEM] 7 scanners deployed across disaster zone."]
        
        # Initialize Scanners (SCN-01 to SCN-07) and Suppliers (SUP-01, SUP-02)
        self.drones: Dict[str, Drone] = {
            f"SCN-0{i+1}": Drone(f"SCN-0{i+1}", "Scanner", i) for i in range(7)
        }
        self.drones["SUP-01"] = Drone("SUP-01", "Supplier", 0)
        self.drones["SUP-02"] = Drone("SUP-02", "Supplier", 1)

        self.incidents: List[Dict[str, Any]] = []
        self.last_active_scanners_count = 7

    def log_alert(self, category: str, message: str):
        tag = f"[{category.upper()}]"
        entry = f"T+{self.time_step:03d} {tag} {message}"
        self.alerts.insert(0, entry)
        if len(self.alerts) > 60:
            self.alerts.pop()

    def set_weather(self, preset: str):
        if preset in WEATHER_PRESETS:
            self.weather_preset = preset
            self.log_alert("weather", f"Weather changed to {preset} (Factor: {WEATHER_PRESETS[preset]['factor']})")

    def add_obstacle(self, lat: float, lng: float):
        self.obstacles.append({"lat": round(lat, 4), "lng": round(lng, 4)})
        self.log_alert("ai", f"Dynamic obstacle added at [{lat:.3f}, {lng:.3f}]. Replanning potential fields.")

    def step(self):
        self.time_step += 1
        if self.time_step >= 150:
            self.log_alert("sys", "Mission boundary reached. Resetting simulation loop.")
            self.reset()
            return

        wf = WEATHER_PRESETS[self.weather_preset]["factor"]

        # 1. Trigger Scheduled Incident Detections
        if self.time_step == 15:
            inc1 = {
                "id": "INC-01", "type": "Trapped Civilians", "severity": "High",
                "people_affected": 6, "detected_by": "SCN-01",
                "x": 80.05, "y": 13.20,
                "status": "Detected", "priority_score": 0.0, "assigned_supplier": None
            }
            inc1["priority_score"] = self._compute_priority_score(inc1)
            self.incidents.append(inc1)
            self.log_alert("crit", "SCN-01 detected INC-01 (Trapped Civilians). Severity: High.")

        if self.time_step == 22:
            inc2 = {
                "id": "INC-02", "type": "Medical Emergency", "severity": "Critical",
                "people_affected": 12, "detected_by": "SCN-02",
                "x": 80.25, "y": 12.85,
                "status": "Detected", "priority_score": 0.0, "assigned_supplier": None
            }
            inc2["priority_score"] = self._compute_priority_score(inc2)
            self.incidents.append(inc2)
            self.log_alert("crit", "SCN-02 detected INC-02 (Medical Emergency). Severity: Critical.")

        # 2. AI Incident Prioritization & Dispatch Engine (t = 30)
        if self.time_step == 30:
            self._dispatch_suppliers()

        # 3. Longitudinal Strip Partitioning
        active_scanners = [d for d in self.drones.values() if d.type == "Scanner" and d.status in ["Scanning", "Redeploying"]]
        num_active = len(active_scanners)
        if num_active > 0 and num_active != self.last_active_scanners_count:
            self.log_alert("ai", f"Fleet partition reconfigured: {num_active} active scanners. Reslicing {num_active} longitudinal strips.")
            self.last_active_scanners_count = num_active

        strip_width = (ZONE_LNG_MAX - ZONE_LNG_MIN) / max(num_active, 1)
        for idx, scanner in enumerate(active_scanners):
            scanner.assigned_strip_idx = idx
            scanner.strip_min_lng = ZONE_LNG_MIN + idx * strip_width
            scanner.strip_max_lng = scanner.strip_min_lng + strip_width

        # 4. Update Scanner Mechanics & Trajectories
        for drone in self.drones.values():
            if drone.type == "Scanner":
                self._update_scanner(drone, num_active, wf)
            elif drone.type == "Supplier":
                self._update_supplier(drone, wf)

    def _compute_priority_score(self, inc: Dict[str, Any]) -> float:
        sev_score = SEVERITY_SCORES.get(inc["severity"], 20)
        people_term = min(inc["people_affected"] * 2, 40)
        dist_deg = math.hypot(inc["x"] - BASE_LNG, inc["y"] - BASE_LAT)
        dist_term = max(0.0, 30.0 - (dist_deg * 27.2))
        return round(sev_score + people_term + dist_term, 1)

    def _dispatch_suppliers(self):
        unhandled = [inc for inc in self.incidents if inc["assigned_supplier"] is None]
        unhandled.sort(key=lambda item: item["priority_score"], reverse=True)
        available_suppliers = [d for d in self.drones.values() if d.type == "Supplier" and d.status in ["Idle", "Landed - Idle"]]

        for inc in unhandled:
            if available_suppliers:
                supp = available_suppliers.pop(0)
                supp.status = "Delivering Payload"
                supp.z = supp.operating_z
                supp.target = {"x": inc["x"], "y": inc["y"]}
                supp.target_incident_id = inc["id"]
                inc["assigned_supplier"] = supp.id
                inc["status"] = "Supplier Dispatched"
                self.log_alert("ai", f"Assigned {supp.id} to {inc['id']} (Score: {inc['priority_score']}). En route at 70m.")
            else:
                inc["status"] = "Queued - Awaiting Next Unit"
                self.log_alert("alert", f"Resource saturation: {inc['id']} queued. Awaiting next returning unit.")

    def _update_scanner(self, drone: Drone, active_count: int, wf: float):
        # Battery drain logic
        if drone.status == "Scanning":
            drone.battery = max(0.0, drone.battery - (drone.base_drain * wf))
            drone.work_pct = min(100.0, drone.work_pct + ((100.0 / 60.0) / wf))
            drone.scan_tick += 1

            if drone.battery <= 20.0:
                drone.status = "Returning to Base"
                drone.target = {"x": BASE_LNG, "y": BASE_LAT}
                self.log_alert("sys", f"{drone.id} reached RTL threshold (<=20%). Initiating autonomous base RTB.")
                return

            row_height = (ZONE_LAT_MAX - ZONE_LAT_MIN) / SWEEP_ROWS
            dx = (0.0001 / wf) * getattr(drone, "sweep_dir", 1)
            dx, dy = self._apply_potential_field(drone, dx, 0.0)
            next_x = drone.x + dx

            if next_x >= drone.strip_max_lng or next_x <= drone.strip_min_lng:
                drone.y = max(ZONE_LAT_MIN, drone.y - row_height)
                drone.sweep_dir *= -1
                if drone.y <= ZONE_LAT_MIN:
                    drone.status = "Returning to Base"
                    drone.target = None
                    self.log_alert("sys", f"{drone.id} completed sector sweep. RTB initiated.")
                return

            drone.x += dx
            drone.y += dy

        elif drone.status == "Returning to Base":
            drone.battery = max(0.0, drone.battery - (drone.base_drain * wf * 0.5))
            dx = BASE_LNG - drone.x
            dy = BASE_LAT - drone.y
            dist = math.hypot(dx, dy)
            if dist < ARRIVAL_EPS:
                drone.x = BASE_LNG
                drone.y = BASE_LAT
                drone.z = 0.0
                drone.status = "Landed - Charging"
                self.log_alert("sys", f"{drone.id} landed at Base Station helipad. Rapid recharge sequence started.")
            else:
                step_size = 0.015 / wf
                drone.x += (dx / dist) * step_size
                drone.y += (dy / dist) * step_size
                drone.z = max(0.0, drone.z - 2.5)

        elif drone.status == "Landed - Charging":
            drone.battery = min(100.0, drone.battery + 4.0)
            if drone.battery >= 100.0:
                drone.status = "Redeploying"
                drone.sweep_dir = 1
                drone.scan_tick = 0
                self.log_alert("ai", f"{drone.id} battery replenished (100%). Redeploying to sector scan pattern.")

        elif drone.status == "Redeploying":
            drone.z = min(drone.operating_z, drone.z + 5.0)
            target_x = drone.strip_min_lng
            target_y = ZONE_LAT_MAX

            dx = target_x - drone.x
            dy = target_y - drone.y
            target_distance = math.hypot(dx, dy)
            step_size = 0.02 / wf
            if target_distance > 0:
                movement = min(target_distance, step_size)
                drone.x += (dx / target_distance) * movement
                drone.y += (dy / target_distance) * movement

            if target_distance <= step_size and drone.z >= drone.operating_z:
                drone.status = "Scanning"
                drone.scan_tick = 0
                drone.sweep_dir = 1
                self.log_alert("sys", f"{drone.id} restored station. Resuming boustrophedon sweep.")

    def _update_supplier(self, drone: Drone, wf: float):
        if drone.status == "Delivering Payload" and drone.target:
            drone.battery = max(0.0, drone.battery - (drone.base_drain * wf))
            dx = drone.target["x"] - drone.x
            dy = drone.target["y"] - drone.y
            dist = math.hypot(dx, dy)

            if dist < ARRIVAL_EPS:
                drone.status = "Returning to Base"
                drone.target = {"x": BASE_LNG, "y": BASE_LAT}
                if drone.target_incident_id:
                    for inc in self.incidents:
                        if inc["id"] == drone.target_incident_id:
                            inc["status"] = "Payload Delivered"
                self.log_alert("ai", f"{drone.id} delivered emergency payload to {drone.target_incident_id}. RTB initiated.")
                drone.target_incident_id = None
            else:
                step_size = 0.02 / wf
                drone.x += (dx / dist) * step_size
                drone.y += (dy / dist) * step_size

        elif drone.status == "Returning to Base":
            drone.battery = max(0.0, drone.battery - (drone.base_drain * wf * 0.4))
            dx = BASE_LNG - drone.x
            dy = BASE_LAT - drone.y
            dist = math.hypot(dx, dy)

            if dist < ARRIVAL_EPS:
                drone.x = BASE_LNG
                drone.y = BASE_LAT
                drone.z = 0.0
                drone.status = "Idle"
                drone.target = None
                self.log_alert("sys", f"{drone.id} returned to Base Helipad. Payload system restocked. Standing by.")
            else:
                step_size = 0.02 / wf
                drone.x += (dx / dist) * step_size
                drone.y += (dy / dist) * step_size

    def _apply_potential_field(self, drone: Drone, dx: float, dy: float) -> Tuple[float, float]:
        step_length = math.hypot(dx, dy)
        final_dx = dx
        final_dy = dy

        for obs in self.obstacles:
            dx_obs = drone.x - obs["lng"]
            dy_obs = drone.y - obs["lat"]
            dist = math.hypot(dx_obs, dy_obs)
            if 0.0 < dist < AVOIDANCE_RADIUS:
                push_strength = ((AVOIDANCE_RADIUS - dist) / AVOIDANCE_RADIUS) * step_length
                push_x = (dx_obs / dist) * push_strength
                push_y = (dy_obs / dist) * push_strength
                tangent_x = -push_y
                tangent_y = push_x
                final_dx += push_x + tangent_x
                final_dy += push_y + tangent_y

        final_length = math.hypot(final_dx, final_dy)
        if final_length > step_length > 0:
            scale = step_length / final_length
            final_dx *= scale
            final_dy *= scale

        return final_dx, final_dy

    def get_telemetry_payload(self) -> Dict[str, Any]:
        scanners = [d for d in self.drones.values() if d.type == "Scanner"]
        total_cov = sum(d.work_pct for d in scanners) / len(scanners) if scanners else 0.0
        wf = WEATHER_PRESETS[self.weather_preset]
        active_count = sum(
            d.type == "Scanner" and d.status in ["Scanning", "Redeploying"]
            for d in self.drones.values()
        )
        grid_lines = [
            ZONE_LNG_MIN + (ZONE_LNG_MAX - ZONE_LNG_MIN) * index / active_count
            for index in range(1, active_count)
        ] if active_count else []

        return {
            "time_step": self.time_step,
            "coverage": round(total_cov, 1),
            "base_station": {"x": BASE_LNG, "y": BASE_LAT},
            "zone_polygon": DISASTER_ZONE_POLYGON,
            "grid_lines": grid_lines,
            "obstacles": self.obstacles,
            "weather": {
                "preset": self.weather_preset,
                "wind_speed": wf["wind_speed"],
                "visibility": wf["visibility"],
                "rain_intensity": wf["rain_intensity"],
                "risk_level": wf["risk_level"],
                "factor": wf["factor"]
            },
            "incidents": self.incidents,
            "drones": [d.calculate_telemetry(wf["factor"]) for d in self.drones.values()],
            "alerts": self.alerts
        }
