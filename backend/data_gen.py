"""
data_gen.py — ResQNet IoT Device Simulator
Simulates 5 field devices deployed in a disaster zone near Ahmedabad, India.
Supports both local (Mosquitto) and cloud (HiveMQ) MQTT brokers via env vars.
"""

import json
import os
import random
import threading
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()  # load .env file if present

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# ──────────────────────────────────────────────
# MQTT Configuration — reads from environment
# ──────────────────────────────────────────────
MQTT_BROKER   = os.environ.get("MQTT_HOST",     "localhost")
MQTT_PORT     = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_TLS      = os.environ.get("MQTT_TLS",      "false").lower() == "true"
MQTT_TOPIC    = "resqnet/sensors"

BASE_LAT = 23.0225   # Ahmedabad, India
BASE_LON = 72.5714

PUBLISH_INTERVAL      = 2    # seconds between each publish
SOS_GUARANTEED_EVERY  = 30   # seconds — DEVICE_002 & DEVICE_004 force SOS
SOS_RANDOM_PROB       = 0.10 # 10% random SOS chance for all devices

DEVICES = [
    "DEVICE_001",
    "DEVICE_002",
    "DEVICE_003",
    "DEVICE_004",
    "DEVICE_005",
]

GUARANTEED_SOS_DEVICES = {"DEVICE_002", "DEVICE_004"}


# ──────────────────────────────────────────────
# Per-device mutable state
# ──────────────────────────────────────────────
class DeviceState:
    """Holds slowly-evolving sensor state for one device."""

    def __init__(self, device_id: str) -> None:
        self.device_id   = device_id
        self.flood_level = round(random.uniform(0.0, 1.5), 2)
        self.battery     = random.randint(85, 100)
        self.start_time  = time.time()

    def next_flood_level(self) -> float:
        delta = random.uniform(0.0, 0.15)
        self.flood_level = min(10.0, round(self.flood_level + delta, 2))
        return self.flood_level

    def next_battery(self) -> int:
        if random.random() < 0.4:
            self.battery = max(0, self.battery - 1)
        return self.battery

    def next_air_quality(self) -> int:
        if random.random() < 0.08:
            return random.randint(301, 500)
        return random.randint(50, 200)

    def sos_active(self) -> bool:
        elapsed = time.time() - self.start_time
        if self.device_id in GUARANTEED_SOS_DEVICES:
            if int(elapsed) % SOS_GUARANTEED_EVERY < PUBLISH_INTERVAL:
                return True
        return random.random() < SOS_RANDOM_PROB

    def build_payload(self) -> dict:
        return {
            "device_id"   : self.device_id,
            "lat"         : round(BASE_LAT + random.uniform(-0.05, 0.05), 6),
            "lon"         : round(BASE_LON + random.uniform(-0.05, 0.05), 6),
            "sos_active"  : self.sos_active(),
            "flood_level" : self.next_flood_level(),
            "air_quality" : self.next_air_quality(),
            "battery"     : self.next_battery(),
            "timestamp"   : datetime.now(timezone.utc).isoformat(),
        }


# ──────────────────────────────────────────────
# MQTT helpers
# ──────────────────────────────────────────────
def on_connect(client: mqtt.Client, userdata, connect_flags, reason_code, properties) -> None:
    status = "connected" if not reason_code.is_failure else f"failed ({reason_code})"
    print(f"[MQTT] {userdata['device_id']} broker {status}")


def create_mqtt_client(device_id: str) -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, userdata={"device_id": device_id})
    client.on_connect = on_connect

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    if MQTT_TLS:
        client.tls_set()

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as exc:
        print(f"[MQTT][{device_id}] Could not connect to broker: {exc}")
    return client


# ──────────────────────────────────────────────
# Device thread worker
# ──────────────────────────────────────────────
def device_worker(device_id: str) -> None:
    """Runs forever: build payload -> publish -> sleep -> repeat."""
    state  = DeviceState(device_id)
    client = create_mqtt_client(device_id)

    while True:
        payload      = state.build_payload()
        payload_json = json.dumps(payload)

        result = client.publish(MQTT_TOPIC, payload_json, qos=1)

        sos_flag = "SOS" if payload["sos_active"] else " OK"
        print(
            f"[{device_id}] {sos_flag} | "
            f"flood={payload['flood_level']:>4} m | "
            f"AQI={payload['air_quality']:>3} | "
            f"bat={payload['battery']:>3}% | "
            f"mqtt_rc={result.rc}"
        )

        time.sleep(PUBLISH_INTERVAL)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("  ResQNet - IoT Device Simulator")
    print(f"  Broker : {MQTT_BROKER}:{MQTT_PORT}  TLS={MQTT_TLS}")
    print(f"  Topic  : {MQTT_TOPIC}")
    print(f"  Devices: {', '.join(DEVICES)}")
    print("=" * 60)

    threads = []
    for device_id in DEVICES:
        t = threading.Thread(
            target=device_worker,
            args=(device_id,),
            name=device_id,
            daemon=True,
        )
        threads.append(t)
        t.start()
        print(f"[MAIN] Started thread for {device_id}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down simulator. Goodbye.")


if __name__ == "__main__":
    main()
