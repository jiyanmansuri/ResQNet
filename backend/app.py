"""
app.py — ResQNet Backend Server
Flask + Flask-SocketIO (threading) + MQTT + SQLite + XGBoost inference
Supports both local (Mosquitto) and cloud (HiveMQ) MQTT brokers via env vars.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, Any, List

from dotenv import load_dotenv
load_dotenv()  # load .env file if present (local dev); Railway uses real env vars

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from flask import Flask, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO

from ml_model import predict

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_DIR, "resqnet.db")

# ──────────────────────────────────────────────
# Flask / SocketIO setup
# ──────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "resqnet-secret-2024")

CORS(app, resources={r"/*": {"origins": "*"}})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# ──────────────────────────────────────────────
# MQTT configuration — reads from environment
# Local:      MQTT_HOST=localhost, MQTT_PORT=1883, MQTT_TLS=false
# HiveMQ Cloud: MQTT_HOST=xxx.s1.eu.hivemq.cloud, MQTT_PORT=8883, MQTT_TLS=true
# ──────────────────────────────────────────────
MQTT_BROKER   = os.environ.get("MQTT_HOST",     "localhost")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TLS      = os.environ.get("MQTT_TLS",      "false").lower() == "true"
MQTT_TOPIC    = "resqnet/sensors"


# ══════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    """Return a new SQLite connection with Row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the incidents table if it doesn't already exist."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id       TEXT,
                lat             REAL,
                lon             REAL,
                severity        TEXT,
                severity_code   INTEGER,
                confidence      REAL,
                flood_level     REAL,
                air_quality     INTEGER,
                sos_active      INTEGER,
                timestamp       TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    print(f"[DB] Initialised -> {DB_PATH}")


def insert_incident(data: Dict[str, Any]) -> None:
    """
    Insert a single incident row into SQLite.
    Thread-safe (each call opens its own connection).
    """
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO incidents
                (device_id, lat, lon, severity, severity_code, confidence,
                 flood_level, air_quality, sos_active, timestamp)
            VALUES
                (:device_id, :lat, :lon, :severity, :severity_code, :confidence,
                 :flood_level, :air_quality, :sos_active, :timestamp)
            """,
            data,
        )
        conn.commit()


# ══════════════════════════════════════════════
# MQTT CALLBACKS
# ══════════════════════════════════════════════

def on_connect(client: mqtt.Client, userdata, connect_flags, reason_code, properties) -> None:
    if not reason_code.is_failure:
        print(f"[MQTT] Connected to broker at {MQTT_BROKER}:{MQTT_PORT}")
        client.subscribe(MQTT_TOPIC)
        print(f"[MQTT] Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"[MQTT] Connection failed ({reason_code})")


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    """
    Called on every sensor message:
      1. Parse JSON
      2. Run ML inference
      3. Persist to SQLite
      4. Emit Socket.IO event to all connected clients
    """
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[MQTT] Bad JSON payload: {exc}")
        return

    # ── ML inference ─────────────────────────────────────────────
    sensor_fields = {
        "flood_level"             : payload.get("flood_level", 0.0),
        "air_quality"             : payload.get("air_quality", 0),
        "sos_active"              : int(payload.get("sos_active", False)),
        "distance_from_epicenter" : payload.get("distance_from_epicenter", 0.0),
        "num_sos_nearby"          : payload.get("num_sos_nearby", 0),
        "battery"                 : payload.get("battery", 100),
    }

    try:
        prediction = predict(sensor_fields)
    except Exception as exc:
        print(f"[ML] Prediction error: {exc}")
        return

    # ── Build the incident record ─────────────────────────────────
    incident = {
        "device_id"    : payload.get("device_id", "UNKNOWN"),
        "lat"          : payload.get("lat", 0.0),
        "lon"          : payload.get("lon", 0.0),
        "severity"     : prediction["severity"],
        "severity_code": prediction["severity_code"],
        "confidence"   : prediction["confidence"],
        "flood_level"  : payload.get("flood_level", 0.0),
        "air_quality"  : payload.get("air_quality", 0),
        "sos_active"   : int(payload.get("sos_active", False)),
        "timestamp"    : payload.get(
            "timestamp",
            datetime.now(timezone.utc).isoformat()
        ),
    }

    # ── Persist ───────────────────────────────────────────────────
    try:
        insert_incident(incident)
    except Exception as exc:
        print(f"[DB] Insert error: {exc}")
        return

    # ── Emit Socket.IO event ─────────────────────────────────────
    socketio.emit("new_incident", incident)

    # Console log
    sos_flag = "SOS" if incident["sos_active"] else " OK"
    print(
        f"[{incident['device_id']}] {sos_flag} | "
        f"{incident['severity']:<8} (conf={incident['confidence']}) | "
        f"flood={incident['flood_level']} AQI={incident['air_quality']}"
    )


def on_disconnect(client: mqtt.Client, userdata, disconnect_flags, reason_code, properties) -> None:
    if reason_code.value != 0:
        print(f"[MQTT] Unexpected disconnect ({reason_code}). Reconnecting ...")


# ══════════════════════════════════════════════
# MQTT — start in background thread
# ══════════════════════════════════════════════

def start_mqtt() -> None:
    """Connect to the broker and start the blocking network loop in a daemon thread."""
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="resqnet-server")
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect

    # Credentials (required for HiveMQ Cloud, optional for local)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # TLS (required for HiveMQ Cloud port 8883)
    if MQTT_TLS:
        client.tls_set()

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    except Exception as exc:
        print(f"[MQTT] Could not connect: {exc}  (will retry via reconnect_delay_set)")

    client.reconnect_delay_set(min_delay=1, max_delay=30)

    thread = threading.Thread(
        target=client.loop_forever,
        name="mqtt-loop",
        daemon=True,
    )
    thread.start()
    print("[MQTT] Network loop started in background thread.")


# ══════════════════════════════════════════════
# REST ENDPOINTS
# ══════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    """Liveness probe."""
    return jsonify({"status": "ok"})


@app.route("/incidents", methods=["GET"])
def get_incidents():
    """Return the 50 most recent incidents, newest first."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT device_id, lat, lon, severity, severity_code, confidence,
                   flood_level, air_quality, sos_active, timestamp, created_at
            FROM   incidents
            ORDER  BY id DESC
            LIMIT  50
        """).fetchall()

    return jsonify([dict(row) for row in rows])


@app.route("/stats", methods=["GET"])
def get_stats():
    """Aggregate counts across all stored incidents."""
    with get_db() as conn:
        totals = conn.execute("""
            SELECT
                COUNT(*)               AS total,
                SUM(severity_code = 2) AS critical,
                SUM(severity_code = 1) AS serious,
                SUM(severity_code = 0) AS stable
            FROM incidents
        """).fetchone()

        active_sos = conn.execute("""
            SELECT COUNT(DISTINCT device_id)
            FROM   incidents
            WHERE  sos_active = 1
              AND  created_at >= datetime('now', '-60 seconds')
        """).fetchone()[0]

    return jsonify({
        "total"     : totals["total"]    or 0,
        "critical"  : totals["critical"] or 0,
        "serious"   : totals["serious"]  or 0,
        "stable"    : totals["stable"]   or 0,
        "active_sos": active_sos         or 0,
    })


# ══════════════════════════════════════════════
# Socket.IO events
# ══════════════════════════════════════════════

@socketio.on("connect")
def handle_connect():
    print("[WS] Client connected")


@socketio.on("disconnect")
def handle_disconnect():
    print("[WS] Client disconnected")


# ══════════════════════════════════════════════
# Application startup
# ══════════════════════════════════════════════

def create_app():
    """Initialise DB and MQTT, then return the app."""
    init_db()
    start_mqtt()
    return app


if __name__ == "__main__":
    create_app()
    port = int(os.environ.get("PORT", 5000))
    print(f"[SERVER] ResQNet backend starting on http://0.0.0.0:{port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False, allow_unsafe_werkzeug=True)
