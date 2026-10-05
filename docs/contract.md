# DroneX data contract

The backend and the dashboard only talk through this JSON. Change it only by editing this file in a pull request that both teammates approve.

Websocket: `/ws` on the backend (locally `ws://localhost:8000/ws`). Extra HTTP endpoint: `POST /reset` restarts the scenario.

## Server -> dashboard (every tick, 1 per second)

```json
{"tick": 12, "comms": "normal",
 "drones": [{"id":"S1","type":"scanner","lat":12.97,"lng":77.59,"battery":87,"status":"scanning","target":"Z3"}],
 "zones": [{"id":"Z1","lat":12.98,"lng":77.60,"status":"unscanned","priority":3}],
 "pending": [{"id":"P1","drone_id":"U1","action":"deliver","target_zone":"Z2","reason":"Survivor found"}],
 "log": ["Tick 12: S1 rerouted, Z3 blocked"]}
```

- `comms`: `normal` or `blackout`
- zone `status`: `unscanned`, `scanned`, `blocked`, `survivor_found`
- drone `type`: `scanner` or `supplier`
- drone `status`: `idle`, `scanning`, `delivering`, `returning`, `grounded`
- `target`: a zone id, or null
- `log`: the last 15 lines only. The dashboard keeps its own history.
- Not in the contract: the base position, fixed at 12.9675, 77.5875 (`BASE_POS` in `backend/planning.py` and `BASE` in `frontend/app.js`).

## Dashboard -> server

```json
{"type":"approve","id":"P1"}
{"type":"override","id":"P1","target_zone":"Z4"}
{"type":"trigger","event":"blackout"}
```

During a blackout `approve` and `override` are held and run when comms return.
