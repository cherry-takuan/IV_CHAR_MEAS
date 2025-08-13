import math
import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import csv
from pathlib import Path

app = FastAPI()

# CORS許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

running = False
step = 0.1
save_mode = "batch"  # "batch" or "realtime"
data_buffer = []
csv_file = Path("measurement.csv")

@app.post("/start")
async def start():
    global running, data_buffer
    data_buffer.clear()
    running = True
    return {"status": "started"}

@app.post("/stop")
async def stop():
    global running
    running = False
    if save_mode == "batch" and data_buffer:
        save_csv(data_buffer)
    return {"status": "stopped"}

@app.post("/set_step/{value}")
async def set_step(value: float):
    global step
    step = value
    return {"step": step}

@app.post("/clear_data")
async def clear_data():
    global data_buffer
    data_buffer.clear()
    return {"status": "cleared"}

@app.post("/set_save_mode/{mode}")
async def set_save_mode(mode: str):
    global save_mode
    if mode in ["batch", "realtime"]:
        save_mode = mode
    return {"save_mode": save_mode}

def save_csv(data_list):
    """<time>\t<x>\t<y>形式で保存"""
    new_file = not csv_file.exists()
    with open(csv_file, "a", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        if new_file:
            writer.writerow(["time", "x", "y"])
        writer.writerows(data_list)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    x = 0
    while True:
        if running:
            timestamp = datetime.now().isoformat()
            y = math.sin(x)
            xs = f"{x:e}"
            ys = f"{y:e}"
            point = [timestamp, xs, ys]

            if save_mode == "batch":
                data_buffer.append(point)
            elif save_mode == "realtime":
                save_csv([point])

            await ws.send_json({"time": timestamp, "x": xs, "y": ys})
            x += step
            await asyncio.sleep(0.5)
        else:
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)
