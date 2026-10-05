import asyncio, json, logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from simulation import Simulation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dronex")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

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
    """Advances only while a dashboard is connected, so the demo always starts at tick 0."""
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
    if not clients:
        sim.reset()          # first viewer after an empty room always sees a fresh mission
    clients.add(websocket)
    try:
        await websocket.send_text(json.dumps(sim.get_state()))
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
    sim.reset()
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
