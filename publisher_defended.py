import paho.mqtt.client as mqtt
import ssl
import json
import time
import random
import hmac
import hashlib
from datetime import datetime, timezone

try:
    MQTT_CLIENT_ARGS = {"callback_api_version": mqtt.CallbackAPIVersion.VERSION1}
except AttributeError:
    MQTT_CLIENT_ARGS = {}

BROKER_HOST = "localhost"
BROKER_PORT = 8883
DEVICE_ID = "001"

CA_CERT = "certs/ca.pem"
CLIENT_CERT = f"certs/device-{DEVICE_ID}.pem"
CLIENT_KEY = f"certs/device-{DEVICE_ID}-key.pem"

TOPIC = f"hydroficient/grandmarina/device-{DEVICE_ID}/sensors"
CLIENT_NAME = f"HYDROLOGIC-Device-{DEVICE_ID}"

SHARED_SECRET = "grandmarina-hydroficient-2024-secret-key"

sequence_counter = 0

def compute_hmac(message_dict):
    msg_copy = {k: v for k, v in message_dict.items() if k != "hmac"}

    msg_string = json.dumps(msg_copy, sort_keys=True)

    signature = hmac.new(
        SHARED_SECRET.encode("utf-8"),
        msg_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return signature

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[SUCCESS] Connected to broker as {CLIENT_NAME}")
        print(f"[INFO] Replay defenses ACTIVE: timestamp + sequence + HMAC")
    else:
        print(f"[ERROR] Connection failed with code {rc}")


def on_disconnect(client, userdata, rc):
    if rc == 0:
        print("[INFO] Clean disconnect")
    else:
        print(f"[WARNING] Unexpected disconnect (rc={rc})")


def on_publish(client, userdata, mid):
    pass 

def generate_defended_reading():
    global sequence_counter
    sequence_counter += 1

    message = {
        "device_id": f"HYDROLOGIC-Device-{DEVICE_ID}",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sequence": sequence_counter,
        "readings": {
            "pressure_upstream": round(random.uniform(58, 62), 2),
            "pressure_downstream": round(random.uniform(54, 58), 2),
            "flow_rate": round(random.uniform(45, 55), 2),
            "gate_a_position": round(random.uniform(42, 48), 1),
            "gate_b_position": round(random.uniform(42, 48), 1)
        },
        "status": "operational"
    }
    message["hmac"] = compute_hmac(message)

    return message

def main():
    global sequence_counter

    print("=" * 60)
    print("HYDROLOGIC Sensor Publisher (Defended)")
    print("=" * 60)
    print(f"Device ID: {DEVICE_ID}")
    print(f"Topic: {TOPIC}")
    print(f"Certificate: {CLIENT_CERT}")
    print(f"Defenses: timestamp + sequence counter + HMAC-SHA256")
    print("=" * 60)

    client = mqtt.Client(client_id=CLIENT_NAME, **MQTT_CLIENT_ARGS)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    try:
        client.tls_set(
            ca_certs=CA_CERT,
            certfile=CLIENT_CERT,
            keyfile=CLIENT_KEY,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS
        )
    except FileNotFoundError as e:
        print(f"[ERROR] Certificate not found: {e}")
        print("[ERROR] Make sure your Project 5 certs/ directory is set up")
        return
    except Exception as e:
        print(f"[ERROR] TLS configuration failed: {e}")
        return

    print(f"\n[CONNECTING] {BROKER_HOST}:{BROKER_PORT}...")
    try:
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return

    client.loop_start()
    time.sleep(1)

    print("\n[PUBLISHING] Sending defended readings (Ctrl+C to stop)...\n")
    try:
        while True:
            reading = generate_defended_reading()
            payload = json.dumps(reading, indent=2)
            client.publish(TOPIC, payload, qos=1)

            flow = reading["readings"]["flow_rate"]
            seq = reading["sequence"]
            hmac_short = reading["hmac"][:12] + "..."
            print(f"[{seq}] Published: {flow} LPM | seq={seq} | hmac={hmac_short}")

            time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n\n[INFO] Stopping after {sequence_counter} messages...")

    client.loop_stop()
    client.disconnect()
    print("[INFO] Disconnected from broker")


if __name__ == "__main__":
    main()