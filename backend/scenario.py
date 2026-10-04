"""The scripted disaster. Everything the demo does on its own is defined here."""
import copy


class Scenario:
    def __init__(self):
        # 3 columns x 4 rows around Bengaluru, 0.005 degrees apart (Z10 sits alone in row 4).
        # (id, row, col, priority) - priority 5 marks a zone with a survivor.
        grid = [
            ("Z1", 0, 0, 1), ("Z2", 0, 1, 2), ("Z3", 0, 2, 5),
            ("Z4", 1, 0, 1), ("Z5", 1, 1, 3), ("Z6", 1, 2, 1),
            ("Z7", 2, 0, 2), ("Z8", 2, 1, 2), ("Z9", 2, 2, 5),
            ("Z10", 3, 1, 2),
        ]
        self._zones = [
            {
                "id": zid,
                "lat": round(12.970 + 0.005 * row, 6),
                "lng": round(77.590 + 0.005 * col, 6),
                "status": "unscanned",
                "priority": prio,
            }
            for zid, row, col, prio in grid
        ]
        self.survivor_zones = {"Z3", "Z9"}

        # Scripted events (tick numbers; 1 tick = 1 second)
        self.block_tick = 8          # a zone on S2's route becomes blocked
        self.block_zone_id = "Z4"
        self.battery_tick = 33       # a scanner's battery drops to critical
        self.battery_drone = "S1"
        self.blackout_tick = 45      # comms go down...
        self.blackout_len = 20       # ...for this many ticks, then recover

    def get_initial_state(self):
        return copy.deepcopy(self._zones)
