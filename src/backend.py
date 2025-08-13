import math
import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket, HTTPException
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

# グローバル変数
running = False
step = 0.1
x_start = 0.0
x_end = 10.0
save_mode = "batch"  # "batch" or "realtime"
data_buffer = []
csv_file = Path("measurement.csv")

@app.post("/start")
async def start():
    global running, data_buffer
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
    if x_start > x_end:
        raise HTTPException(status_code=400, detail="開始値は終了値以下でなければなりません。")
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
    global running
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
    global step
    if value <= 0:
        raise HTTPException(status_code=400, detail="ステップは正の値でなければなりません。")
    step = value
    return {"step": step}

@app.post("/set_range/{start}/{end}")
async def set_range(start: float, end: float):
    global x_start, x_end, running
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
    if start > end:
        raise HTTPException(status_code=400, detail="開始値は終了値以下でなければなりません。")
    x_start = start
    x_end = end
    return {"x_start": x_start, "x_end": x_end}

@app.post("/clear_data")
async def clear_data():
    global data_buffer, running
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
    data_buffer.clear()
    return {"status": "cleared"}

@app.post("/set_save_mode/{mode}")
async def set_save_mode(mode: str):
    global save_mode, running
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
    if mode not in ["batch", "realtime"]:
        raise HTTPException(status_code=400, detail="保存モードは batch または realtime です。")
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
    global running, step, x_start, x_end, save_mode, data_buffer  # ここでglobal宣言
    await ws.accept()
    while True:
        if running:
            total_steps = int((x_end - x_start) / step) + 1
            x = x_start
            for i in range(total_steps):
                if not running:
                    break
                timestamp = datetime.now().isoformat()
                y = math.sin(x)
                xs = f"{x:e}"
                ys = f"{y:e}"
                point = [timestamp, xs, ys]

                if save_mode == "batch":
                    data_buffer.append(point)
                elif save_mode == "realtime":
                    save_csv([point])

                progress = (i + 1) / total_steps
                await ws.send_json({
                    "time": timestamp,
                    "x": xs,
                    "y": ys,
                    "progress": progress,
                    "status": "running",
                    "conditions": {
                        "x_start": x_start,
                        "x_end": x_end,
                        "step": step,
                        "save_mode": save_mode
                    }
                })
                x += step
                await asyncio.sleep(0.5)

            # 計測終了通知
            running = False
            if save_mode == "batch" and data_buffer:
                save_csv(data_buffer)
            await ws.send_json({"status": "done"})
        else:
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)
