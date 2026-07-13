# 🚀 ResQNet — Quick Start Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | ≥ 3.9 | https://python.org |
| Node.js | ≥ 18 | https://nodejs.org |
| Mosquitto (MQTT broker) | any | https://mosquitto.org/download/ |

---

## One-time setup

### 1. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Train the ML model (only needed once — or after code changes)
```bash
cd backend
python ml_model.py
```
Expected output: accuracy report + `model.pkl` and `features.pkl` written to `backend/`.

### 3. Install frontend dependencies
```bash
cd frontend
npm install
```

---

## Running the full system (5 terminals)

Open **5 separate terminal windows** from the `ResQnet/` root folder.

---

### Terminal 1 — MQTT Broker (Mosquitto)

**Windows (if installed as a service — already running):**
```powershell
net start mosquitto
```

**Windows (manual start):**
```powershell
mosquitto -v
```

**Linux / macOS:**
```bash
mosquitto -v
```

> ✅ You should see: `mosquitto version X.X.X starting`  
> Default port: **1883**

---

### Terminal 2 — Train the Model *(skip if already done)*

```bash
cd backend
python ml_model.py
```

> ✅ You should see accuracy ~96–98% and `model.pkl` written to `backend/`

---

### Terminal 3 — Backend Server (Flask + SocketIO)

```bash
cd backend
python app.py
```

> ✅ You should see:
> ```
> [DB] Initialised → ...resqnet.db
> [MQTT] Network loop started in background thread.
> [SERVER] ResQNet backend starting on http://0.0.0.0:5000
> ```

Verify it's running: http://localhost:5000/health → `{"status": "ok"}`

---

### Terminal 4 — IoT Device Simulator

```bash
cd backend
python data_gen.py
```

> ✅ You should see 150 device threads printing sensor data every 2 seconds:
> ```
> [DEVICE_001]    OK  | flood= 1.2 m | AQI=143 | bat= 98% | ...
> [DEVICE_002] 🚨 SOS | flood= 2.4 m | AQI= 88 | bat=100% | ...
> ```

---

### Terminal 5 — React Dashboard

```bash
cd frontend
npm install
npm start
```

> ✅ Browser opens automatically at **http://localhost:3000**  
> If not, open it manually.

---

## ✅ Verification checklist

| Check | How |
|-------|-----|
| MQTT broker running | Terminal 1 shows no errors |
| model.pkl exists | `ls backend/model.pkl` (or `dir backend\model.pkl`) |
| Backend health | GET http://localhost:5000/health → `{"status":"ok"}` |
| Incidents flowing | GET http://localhost:5000/incidents → JSON array growing |
| Stats | GET http://localhost:5000/stats → counts updating |
| Dashboard live | http://localhost:3000 — map markers appear, feed scrolls |
| Socket.IO connected | Green dot in top-right of dashboard says "Connected" |

---

## 🔴 Known issues & fixes

### `pip install sqlite3` fails
**Cause:** `sqlite3` is part of Python's standard library — no pip install needed.  
**Fix:** Already removed from `requirements.txt`. ✅

### `use_label_encoder` deprecation warning (XGBoost ≥ 1.6)
**Cause:** Parameter removed in newer XGBoost.  
**Fix:** Warnings are suppressed via `warnings.filterwarnings("ignore")` in `ml_model.py`. Safe to ignore.

### `app.py` crashes with `model.pkl not found`
**Cause:** `ml_model.py` was never run.  
**Fix:** Run Terminal 2 (`python ml_model.py`) before starting the server.

### MQTT connection refused
**Cause:** Mosquitto broker is not running.  
**Fix:** Start Terminal 1 first. `app.py` and `data_gen.py` will auto-retry.

### React shows blank map / no markers
**Cause:** Backend not running or CORS blocked.  
**Fix:** Confirm `python app.py` is running on port 5000, then hard-refresh (`Ctrl+Shift+R`).

### Port 5000 already in use (macOS)
**Cause:** macOS AirPlay Receiver uses port 5000.  
**Fix:** Disable AirPlay Receiver in System Settings → General → AirDrop & Handover.

---

## Project structure

```
ResQnet/
  backend/
    app.py           ← Flask server (MQTT + SocketIO + REST + SQLite)
    ml_model.py      ← XGBoost training & inference engine
    data_gen.py      ← IoT device simulator (150 threads)
    mqtt_client.py   ← (reserved for future standalone MQTT utilities)
    requirements.txt ← Python dependencies
    model.pkl        ← generated after training
    features.pkl     ← generated after training
    resqnet.db       ← generated at server startup (SQLite)
  frontend/
    src/App.js       ← React dashboard (map + feed + stats)
    src/index.js     ← React entry point
    public/index.html← HTML shell
    package.json     ← Node dependencies
  README.md
  START.md           ← this file
```

---

*ResQNet v1.0 — 5G-AI Disaster Response System*
