import copy
COLS, ROWS = 14, 4
class Scenario:
    def __init__(self):
        self.survivor_zones = {"Z44", "Z45"}
        self._zones = [{"id": f"Z{r*COLS+c+1}", "lat": round(12.970+0.0025*r, 6), "lng": round(77.590+0.0025*c, 6),
                        "status": "unscanned", "priority": 5 if f"Z{r*COLS+c+1}" in self.survivor_zones else 1}
                       for r in range(ROWS) for c in range(COLS)]
        self.block_tick = 8; self.block_zone_id = "Z4"
        self.battery_tick = 33; self.battery_drone = "S1"
        self.blackout_tick = 45; self.blackout_len = 20
    def get_initial_state(self): return copy.deepcopy(self._zones)
