# DroneX

**Coordinated multi-drone disaster response simulation: search, detect, and deliver aid, with a human commander in the loop.**

VIDEO LINK : https://drive.google.com/file/d/1zDEpt0o_G6etDWH3tuMKIT65bKh7yFcx/view?usp=sharing

## Problem

Floods, earthquakes and landslides destroy roads and communication links. Responders lose their live view of affected areas, manual search is slow, and survival odds fall sharply in the first 72 hours. Aid delivery to cut-off locations depends on scarce helicopters or ground teams. Scanning and delivery are usually coordinated manually and separately.

## Solution

DroneX simulates a coordinated fleet of two drone types:

- **Scanner drones (S1, S2)** sweep a zoned area in boustrophedon (lawnmower) order and flag zones where survivors are found.
- **Supplier drones (U1, U2)** deliver aid to flagged zones.
- **Coordinator** proposes a delivery and picks the nearest available supplier. It never acts on its own: a human commander must approve or override.

State streams to a dashboard in real time over WebSockets.

## Key Features

- A* route planning with obstacle clearance around blocked zones
- Dynamic rerouting when a zone is blocked mid-mission
- Low-battery return to base (below 20%), with the remaining zones handed to the other scanner
- Communication blackout handling: commands are held, then replayed on recovery
- Human-in-the-loop approve/override of delivery proposals
- Functional test suite (pytest)

## Demo Scenario

The simulation runs a scripted disaster (1 tick = 1 second) over 10 zones (Z1 to Z10):

| Tick | Event |
|------|-------|
| 8 | Zone Z4 becomes blocked; affected routes are replanned |
| 33 | Scanner S1 battery drops to 15%; it returns to base and S2 takes over its zones |
| 45 | A 20-tick communications blackout begins |

Zones Z3 and Z9 contain survivors, which triggers delivery proposals.

## Architecture

```
backend/
  main.py        FastAPI app, WebSocket /ws, POST /reset, simulation loop
  simulation.py  Simulation engine: scanner/supplier behaviour, events, commands
  agents.py      Drone and Coordinator classes
  planning.py    Boustrophedon ordering, A* routing, obstacle clearance
  scenario.py    Zone layout and scripted events
  test_sim.py    pytest tests
frontend/        [FILL: describe the dashboard files once finished]
```

Agents communicate through shared in-process state owned by `Simulation`. The only network communication is between the backend and the dashboard over WebSocket.

### WebSocket API (`/ws`)

Server to client: full state JSON (tick, comms status, drones, zones, pending proposals, last 15 log lines), sent on connect and every second.

Client to server:

```json
{"type": "approve", "id": "P1"}
{"type": "override", "id": "P1", "target_zone": "Z8"}
{"type": "trigger", "event": "blackout"}
```

`POST /reset` restarts the simulation from tick 0.

## Tech Stack

- Python, FastAPI, Uvicorn, WebSockets, pytest
- Frontend: JavaScript,CSS,HTML
- Algorithms: boustrophedon sweep ordering, A* path planning
- No external AI models or APIs are used by the system.
- AI-assisted development: Claude (Anthropic) and Gemini (Google) were used as coding assistants.

## Getting Started

```bash
git clone https://github.com/Mr46lite/DroneX_New.git
cd DroneX_New/backend
pip install -r requirements.txt
uvicorn main:app --reload
```



Run tests:

```bash
pytest
```



## Limitations

- This is a software simulation with virtual drones; real hardware is not integrated.
- The disaster scenario is scripted, not randomly generated.
- There is no machine-learning component; decisions are rule-based.
- No quantitative performance metrics yet.

## Future Work

Want to fix more bugs and refine the prototype

## Team

- N KRISHNA TEJ [TEAM LEADER]
- G THEERTHA REDDY [TEAM MEMBER]


- TEAM DroneX
