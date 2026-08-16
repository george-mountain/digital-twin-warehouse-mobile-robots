
import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .simulation import WarehouseSimulation


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "dist"
simulation = WarehouseSimulation()


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(simulation.run(), name="warehouse-simulation")
    yield
    simulation.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="Warehouse AMR Digital Twin", version="1.0.0", lifespan=lifespan)


class ScaleRequest(BaseModel):
    robots: int = Field(ge=10, le=100)


@app.get("/api/health")
async def health():
    return {"status": "healthy", "tick": simulation.tick_number}


@app.get("/api/state")
async def state():
    return simulation.snapshot()


@app.put("/api/simulation/scale")
async def scale(payload: ScaleRequest):
    if payload.robots not in (10, 25, 50, 100):
        raise HTTPException(422, "robots must be one of 10, 25, 50, or 100")
    async with simulation._lock:
        simulation.set_robot_count(payload.robots)
    return simulation.snapshot()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    queue = simulation.subscribe()
    try:
        await websocket.send_json(simulation.snapshot())
        while True:
            await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        simulation.unsubscribe(queue)


if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        candidate = (FRONTEND / path).resolve()
        if path and candidate.is_relative_to(FRONTEND) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND / "index.html")
