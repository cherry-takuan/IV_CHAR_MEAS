import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import csv
from pathlib import Path

import serial
from serial.tools import list_ports

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
wire_mode = "2wire"  # 2-wire / 4-wire
data_buffer = []
csv_file = Path("measurement.csv")
ser = None
max_voltage = 20

@app.post("/init")
async def init_2400():
    global running, ser
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
    myser = None
    myser = serial.Serial()
    myser.baudrate = 9600
    myser.timeout = 1       # タイムアウトの時間
    ports = list_ports.comports()
    devices = [info.device for info in ports]
    if len(devices) == 0:
        print("Error: Port not found")
        return None
    else:
        myser.port = devices[0]
    try:
        myser.open()
        print("serial open")
    except:
        print("Error：The port could not be opened.")
        exit(1)
    if myser is None:
        raise HTTPException(status_code=400, detail="シリアルポートが初期化されていません。")
    ser = myser
    ser.reset_input_buffer()
    ser.write("*IDN?\n".encode('ascii'))
    await asyncio.sleep(0.05)
    idn = ser.readline().strip().decode('UTF-8')
    print(idn)
    ser.write("*RST\n".encode('ascii'))
    await asyncio.sleep(0.05)

    ser.write(":SOUR:FUNC:MODE VOLT\n".encode('ascii'))
    await asyncio.sleep(0.05)

    ser.write(":SYST:RSEN OFF\n".encode('ascii'))
    await asyncio.sleep(0.05)

    ser.write(":SOUR:VOLT:PROT 20\n".encode('ascii'))
    await asyncio.sleep(0.05)
    ser.write(":SENS:VOLT:PROT 20\n".encode('ascii'))
    await asyncio.sleep(0.05)
    ser.write(":SENS:CURR:PROT 10e-3\n".encode('ascii'))
    await asyncio.sleep(0.05)
    return {"status": "standby","idn":idn}

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
    global running, step
    if running:
        raise HTTPException(status_code=400, detail="測定中です。")
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

# ★ 追加: 2-wire / 4-wire 切り替え
@app.post("/set_wire_mode/{mode}")
async def set_wire_mode(mode: str):
    global wire_mode, running
    if running:
        raise HTTPException(status_code=400, detail="測定中は切り替えできません。")
    if mode not in ["2wire", "4wire"]:
        raise HTTPException(status_code=400, detail="モードは '2wire' または '4wire' です。")
    wire_mode = mode
    print(f"Wire mode set to: {mode}")
    if wire_mode == "4wire":
        ser.write(":SYST:RSEN ON\n".encode('ascii'))
    else:
        ser.write(":SYST:RSEN OFF\n".encode('ascii'))
    await asyncio.sleep(0.05)
    return {"wire_mode": wire_mode}

# 電圧制限値設定
@app.post("/set_voltage_limit/{value}")
async def set_voltage_limit(value: float):
    global running, max_voltage
    if running:
        raise HTTPException(status_code=400, detail="測定中は変更できません。")
    print(f"Voltage limit set to: {value}")
    try:
        voltage = float(value)
    except Exception as e:
        raise HTTPException(status_code=400, detail="不正な値です。")
    else:
        max_voltage = voltage
        command = ":SENS:VOLT:PROT "+str(f"{voltage:e}")+"\n"
        ser.write(command.encode('ascii'))
        await asyncio.sleep(0.05)
    return {"voltage_limit": value}

# 電流制限値設定
@app.post("/set_current_limit/{value}")
async def set_current_limit(value: float):
    global running
    if running:
        raise HTTPException(status_code=400, detail="測定中は変更できません。")
    print(f"Current limit set to: {value}")
    try:
        current = float(value)
    except Exception as e:
        raise HTTPException(status_code=400, detail="不正な値です。")
    else:
        command = ":SENS:CURR:PROT "+str(f"{current:e}")+"\n"
        ser.write(command.encode('ascii'))
    return {"current_limit": value}

# 平均回数設定
@app.post("/set_average_count/{count}")
async def set_average_count(count: int):
    global running
    if running:
        raise HTTPException(status_code=400, detail="測定中は変更できません。")
    if count not in [1, 3, 5, 10]:
        raise HTTPException(status_code=400, detail="平均回数は1, 3, 5, 10から選択してください。")
    print(f"Average count set to: {count}")
    ser.write(":SENS:AVER:TCON REP\n".encode('ascii'))
    command = ":SENS:AVER:COUN "+str(count)+"\n"
    ser.write(command.encode('ascii'))
    return {"average_count": count}

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
    global running, step, x_start, x_end, save_mode, data_buffer, ser
    await ws.accept()
    
    while True:
        if running:
            if ser is None:
                await ws.send_json({"status": "error", "message": "シリアルポートが初期化されていません。"})
                running = False
                continue
                
            total_steps = int((x_end - x_start) / step) + 1
            x = x_start
            for i in range(total_steps):
                if not running:
                    break
                timestamp = datetime.now().isoformat()
                output_voltage = x
                if x > max_voltage:
                    output_voltage = max_voltage
                
                command = ":SOUR:VOLT "+str(output_voltage)+"\n"
                ser.write(command.encode('ascii'))
                await asyncio.sleep(0.5)

                ser.reset_input_buffer()
                ser.write(":MEAS:CURR?\n".encode('ascii'))
                await asyncio.sleep(0.5)
                data = ser.readline().strip().decode('UTF-8')

                x_meas = data.split(",")[0]
                y_meas = data.split(",")[1]

                xs = x_meas
                ys = y_meas
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
                        "save_mode": save_mode,
                        "wire_mode": wire_mode
                    }
                })
                x += step
                #await asyncio.sleep(0.05)
            running = False
            if ser is not None:
                ser.write(":OUTP:STATE 0\n".encode('ascii'))
            if save_mode == "batch" and data_buffer:
                save_csv(data_buffer)
            await ws.send_json({"status": "done"})
        else:
            await asyncio.sleep(0.1)

if __name__ == "__main__":
    uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)
