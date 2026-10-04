import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from simulation import Simulation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dronex")

sim = Simulation()
clients = set()


async def broadcast(message):
    for ws in list(clients):
        try:
            await ws.send_text(message)
        except Exception as e:
            logger.warning("Dropping client: %s", e)
            clients.discard(ws)


async def simulation_loop():
    """One shared loop. The simulation only advances while a dashboard is connected,
    so the disaster always starts when the demo starts."""
    while True:
        try:
            if clients:
                sim.update()
                await broadcast(json.dumps(sim.get_state()))
        except Exception:
            logger.exception("Simulation loop error")
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    try:
        await websocket.send_text(json.dumps(sim.get_state()))   # show something immediately
        while True:
            raw = await websocket.receive_text()
            try:
                sim.handle_command(json.loads(raw))
            except Exception:
                logger.exception("Bad command: %r", raw)
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)


@app.post("/reset")
async def reset():
    """Restart the scenario from tick 0 (handy between demo runs)."""
    sim.reset()
    return {"ok": True}
