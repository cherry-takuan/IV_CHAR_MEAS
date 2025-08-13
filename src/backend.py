import math
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import sys

app = FastAPI()

# CORS許可（ローカル開発用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

running = False
step = 0.1

@app.post("/start")
async def start():
    global running
    running = True
    print("\033[32mINFO:\033[0m\tstart meas")
    return {"status": "started"}

@app.post("/stop")
async def stop():
    global running
    running = False
    print("\033[32mINFO:\033[0m\tstop meas")
    return {"status": "stopped"}

@app.post("/set_step/{value}")
async def set_step(value: float):
    global step
    step = value
    return {"step": step}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    x = 0
    while True:
        if running:
            y = math.sin(x)
            await ws.send_json({"x": x, "y": y})
            print("\033[32mINFO:\033[0m\tsend data")
            x += step
            await asyncio.sleep(0.5)  # 0.5秒ごと
        else:
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)