import asyncio
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Forge Warehouse", version="1.0.0")
inventory: list[dict] = []
lock = asyncio.Lock()
INSTANCE = os.getenv("HOSTNAME", socket.gethostname())


class Batch(BaseModel):
    model_config = ConfigDict(extra="allow")
    batch_id: str = Field(min_length=1, max_length=128)
    material: str = Field(min_length=1, max_length=128)
    weight_kg: float = Field(gt=0, allow_inf_nan=False)
    shape: str = Field(default="Barren", max_length=128)
    quality: str = Field(pattern="^(PASSED|REJECTED)$")


@app.get("/", include_in_schema=False)
async def frontend():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "instance": INSTANCE, "storage": "memory"}


@app.get("/inventory")
async def get_inventory():
    async with lock:
        return list(inventory)


@app.post("/store", status_code=201)
@app.post("/inventory", status_code=201)
async def store_batch(batch: Batch):
    async with lock:
        if any(item["batch_id"] == batch.batch_id for item in inventory):
            raise HTTPException(409, "Batch-ID bereits eingelagert")
        item = batch.model_dump()
        item["received_at"] = datetime.now(timezone.utc).isoformat()
        item["warehouse_instance"] = INSTANCE
        inventory.append(item)
        return item


@app.post("/demo", status_code=201)
async def demo():
    if os.getenv("ENABLE_DEMO", "false").lower() != "true":
        raise HTTPException(404, "Demo deaktiviert")
    import random
    return await store_batch(Batch(batch_id=f"MET-{uuid4().hex[:8].upper()}",
        material=random.choice(["Eisen", "Stahl", "Kupfer", "Aluminium"]),
        weight_kg=random.choice([250, 500, 750, 1000]),
        quality="PASSED" if random.random() < 0.9 else "REJECTED"))
