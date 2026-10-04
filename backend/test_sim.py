from planning import (BASE_POS, CLEARANCE, _dist_point_segment, a_star_route,
                      boustrophedon_path, get_distance)
from scenario import Scenario
from simulation import Simulation

ZONES = Scenario().get_initial_state()
POS = {z["id"]: (z["lat"], z["lng"]) for z in ZONES}


def run(sim, ticks, auto_approve=False):
    for _ in range(ticks):
        sim.update()
        if auto_approve:
            for p in list(sim.coord.pending):
                sim.handle_command({"type": "approve", "id": p["id"]})


def has_log(sim, text):
    return any(text in line for line in sim.log)


# ---------- planning ----------
def test_boustrophedon_is_a_lawnmower_sweep():
    assert boustrophedon_path(ZONES) == ["Z1", "Z2", "Z3", "Z6", "Z5", "Z4", "Z7", "Z8", "Z9", "Z10"]


def test_astar_detours_around_a_blocked_zone():
    route = a_star_route(POS["Z4"], "Z6", ["Z5"], ZONES)
    assert route[-1] == POS["Z6"]
    assert POS["Z5"] not in route
    length, prev = 0.0, POS["Z4"]
    for w in route:
        length += get_distance(prev, w)
        assert _dist_point_segment(POS["Z5"], prev, w) >= CLEARANCE   # never flies over it
        prev = w
    assert length > get_distance(POS["Z4"], POS["Z6"]) + 0.001        # a real detour


def test_astar_refuses_a_blocked_target():
    assert a_star_route(BASE_POS, "Z5", ["Z5"], ZONES) is None


def test_astar_does_not_detour_via_base():
    route = a_star_route(POS["Z5"], "Z10", [], ZONES)
    assert BASE_POS not in route
    assert route[-1] == POS["Z10"]


# ---------- coordinator ----------
def test_nearest_idle_supplier_is_chosen():
    sim = Simulation()
    u2 = sim.drone("U2")
    u2.lat, u2.lng = POS["Z8"]
    assert sim.coord.pick_supplier(sim.drones, POS["Z9"]).id == "U2"
    u2.status = "delivering"                       # busy suppliers are skipped
    assert sim.coord.pick_supplier(sim.drones, POS["Z9"]).id == "U1"


def test_proposal_ids_are_never_reused():
    sim = Simulation()
    sim.coord.propose(1, "U1", "deliver", "Z3", "t")
    sim.handle_command({"type": "approve", "id": "P1"})
    sim.coord.propose(2, "U1", "deliver", "Z9", "t")
    assert sim.coord.pending[0]["id"] == "P2"


# ---------- commands ----------
def test_approve_sends_the_supplier():
    sim = Simulation()
    sim.coord.propose(1, "U1", "deliver", "Z3", "t")
    sim.handle_command({"type": "approve", "id": "P1"})
    assert sim.coord.pending == []
    sim.update()
    u1 = sim.drone("U1")
    assert u1.target == "Z3" and u1.status == "delivering"


def test_override_changes_the_target_zone():
    sim = Simulation()
    sim.coord.propose(1, "U1", "deliver", "Z3", "t")
    sim.handle_command({"type": "override", "id": "P1", "target_zone": "Z8"})
    sim.update()
    assert sim.drone("U1").target == "Z8"
    assert has_log(sim, "OVERRIDDEN to Z8")


def test_bad_commands_are_ignored_not_fatal():
    sim = Simulation()
    sim.coord.propose(1, "U1", "deliver", "Z3", "t")
    sim.handle_command({"type": "override", "id": "P1", "target_zone": "Z99"})
    sim.handle_command({"type": "approve", "id": "P42"})
    sim.handle_command({"type": "nonsense"})
    assert len(sim.coord.pending) == 1


# ---------- scenario ----------
def test_zone_blocking_reroutes_a_drone_mid_route():
    sim = Simulation()
    run(sim, 7)
    s2 = sim.drone("S2")
    assert POS["Z4"] in s2.waypoints
    run(sim, 1)                                    # tick 8: Z4 becomes blocked
    assert POS["Z4"] not in s2.waypoints
    assert has_log(sim, "S2 rerouted, Z4 blocked")


def test_blackout_holds_commands_then_recovers():
    sim = Simulation()
    run(sim, 45)
    assert sim.comms == "blackout"
    sim.coord.propose(sim.tick, "U1", "deliver", "Z8", "t")
    pid = sim.coord.pending[-1]["id"]
    sim.handle_command({"type": "approve", "id": pid})
    assert any(p["id"] == pid for p in sim.coord.pending)      # held, not executed
    run(sim, 20)                                               # tick 65
    assert sim.comms == "normal"
    assert all(p["id"] != pid for p in sim.coord.pending)      # executed after recovery


def test_manual_blackout_trigger():
    sim = Simulation()
    sim.handle_command({"type": "trigger", "event": "blackout"})
    assert sim.comms == "blackout"


def test_full_scenario_plays_out():
    sim = Simulation()
    run(sim, 140, auto_approve=True)
    for expected in ["Z4 became BLOCKED", "S2 rerouted, Z4 blocked", "S1 low battery",
                     "S2 takes over", "(queued during blackout)", "COMMS restored",
                     "delivered aid to Z3", "delivered aid to Z9", "Sweep complete"]:
        assert has_log(sim, expected), expected
    assert sim.drone("S1").status == "grounded"
    assert sim.zmap["Z4"]["status"] == "blocked"
