import paho.mqtt.client as mqtt
import ssl
import json
import hmac
import hashlib
import time
import threading
from datetime import datetime, timezone

from dashboard_server import DashboardServer

try:
    MQTT_CLIENT_ARGS = {"callback_api_version": mqtt.CallbackAPIVersion.VERSION1}
except AttributeError:
    MQTT_CLIENT_ARGS = {}


BROKER_HOST = "localhost"
BROKER_PORT = 8883
SUBSCRIBER_ID = "dashboard"

CA_CERT = "certs/ca.pem"
CLIENT_CERT = "certs/device-001.pem"
CLIENT_KEY = "certs/device-001-key.pem"

TOPIC = "hydroficient/grandmarina/#"
CLIENT_NAME = "GrandMarina-Dashboard-Live"

SHARED_SECRET = "grandmarina-hydroficient-2024-secret-key"

MAX_AGE_SECONDS = 30  

device_counters = {}

stats = {"accepted": 0, "rejected": 0}

dashboard = None


def verify_hmac(message_dict):
    received_hmac = message_dict.get("hmac")
    if received_hmac is None:
        return False, "No HMAC field in message"

    msg_copy = {k: v for k, v in message_dict.items() if k != "hmac"}
    msg_string = json.dumps(msg_copy, sort_keys=True)

    expected_hmac = hmac.new(
        SHARED_SECRET.encode("utf-8"),
        msg_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    if hmac.compare_digest(received_hmac, expected_hmac):
        return True, ""
    else:
        return False, "HMAC mismatch"


# =============================================================================
# Timestamp Validation (same as Project 6)
# =============================================================================
def check_timestamp(message_dict):
    """
    Check if the message timestamp is within the acceptable window.
    Returns (True, age_seconds) if fresh, (False, age_seconds) if stale.
    """
    timestamp_str = message_dict.get("timestamp")
    if timestamp_str is None:
        return False, -1

    try:
        msg_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age = (now - msg_time).total_seconds()

        if age <= MAX_AGE_SECONDS:
            return True, age
        else:
            return False, age
    except (ValueError, TypeError):
        return False, -1

def check_sequence(message_dict):
    device_id = message_dict.get("device_id", "unknown")
    sequence = message_dict.get("sequence")

    if sequence is None:
        return False, "No sequence field in message"

    last_seen = device_counters.get(device_id, 0)

    if sequence > last_seen:
        device_counters[device_id] = sequence
        return True, ""
    else:
        return False, f"Sequence {sequence} <= last seen {last_seen}"

def validate_message(message_dict):
    results = {
        "hmac": {"passed": False, "detail": ""},
        "timestamp": {"passed": False, "detail": ""},
        "sequence": {"passed": False, "detail": ""}
    }

    hmac_ok, hmac_reason = verify_hmac(message_dict)
    results["hmac"]["passed"] = hmac_ok
    results["hmac"]["detail"] = "Valid" if hmac_ok else hmac_reason
    if not hmac_ok:
        return False, results

    ts_ok, age = check_timestamp(message_dict)
    if age >= 0:
        results["timestamp"]["detail"] = f"Age: {age:.1f}s (max: {MAX_AGE_SECONDS}s)"
    else:
        results["timestamp"]["detail"] = "Missing or invalid timestamp"
    results["timestamp"]["passed"] = ts_ok
    if not ts_ok:
        return False, results

    seq_ok, seq_reason = check_sequence(message_dict)
    results["sequence"]["passed"] = seq_ok
    results["sequence"]["detail"] = "Valid (new sequence)" if seq_ok else seq_reason
    if not seq_ok:
        return False, results

    return True, results

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[SUCCESS] Connected to broker as {CLIENT_NAME}")
        print(f"[INFO] Replay defenses ACTIVE")
        print(f"[INFO]   HMAC verification: ON")
        print(f"[INFO]   Timestamp window: {MAX_AGE_SECONDS} seconds")
        print(f"[INFO]   Sequence tracking: ON")
        print(f"[INFO]   Live dashboard: ON")
        print(f"[INFO] Subscribing to: {TOPIC}")
        client.subscribe(TOPIC, qos=1)
    else:
        print(f"[ERROR] Connection failed with code {rc}")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())

        accepted, results = validate_message(data)

        device = data.get("device_id", "Unknown")
        flow = data.get("readings", {}).get("flow_rate", "N/A")
        seq = data.get("sequence", "N/A")

        if accepted:
            stats["accepted"] += 1

            print(f"\n[ACCEPTED] Device: {device} | Flow: {flow} LPM | Seq: {seq}")
            print(f"  HMAC: PASS | Timestamp: PASS ({results['timestamp']['detail']}) | Sequence: PASS")

            if dashboard:
                sensor_data = data.get("readings", {})
                dashboard.log_valid_message(device, sensor_data, msg.topic)

        else:
            stats["rejected"] += 1

            failed_check = "unknown"
            reason = "unknown"
            for check_name in ["hmac", "timestamp", "sequence"]:
                if not results[check_name]["passed"]:
                    failed_check = check_name.upper()
                    reason = results[check_name]["detail"]
                    break

            print(f"\n[REJECTED] Device: {device} | Flow: {flow} LPM | Seq: {seq}")
            print(f"  Failed check: {failed_check}")
            print(f"  Reason: {reason}")

            if dashboard:
                attack_types = {
                    "HMAC": "Message Tampering",
                    "TIMESTAMP": "Stale Message",
                    "SEQUENCE": "Replay Attack"
                }
                attack_type = attack_types.get(failed_check, "Security Violation")
                dashboard.log_rejected_message(
                    reason, attack_type, device, msg.topic
                )

        total = stats["accepted"] + stats["rejected"]
        print(f"  Stats: {stats['accepted']} accepted, {stats['rejected']} rejected ({total} total)")

    except json.JSONDecodeError:
        print(f"\n[REJECTED] Non-JSON message on {msg.topic}")
        stats["rejected"] += 1
        if dashboard:
            dashboard.log_rejected_message(
                "Invalid JSON", "Missing Fields", "unknown", msg.topic
            )


def on_subscribe(client, userdata, mid, granted_qos):
    print(f"[SUBSCRIBED] QoS granted: {granted_qos}")

def main():
    global dashboard

    print("=" * 60)
    print("Grand Marina Security Dashboard (Live)")
    print("=" * 60)
    print(f"Subscribing to: {TOPIC}")
    print(f"Certificate:    {CLIENT_CERT}")
    print(f"Max message age: {MAX_AGE_SECONDS} seconds")
    print(f"Dashboard:       http://localhost:8000")
    print("=" * 60)

    dashboard = DashboardServer()

    def run_dashboard():
        try:
            dashboard.start(open_browser=True)
        except Exception as e:
            print(f"[ERROR] Dashboard server failed: {e}")

    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    time.sleep(2) 

    client = mqtt.Client(client_id=CLIENT_NAME, **MQTT_CLIENT_ARGS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_subscribe = on_subscribe

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

    print("[LISTENING] Waiting for messages (Ctrl+C to stop)...\n")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n\n[INFO] Shutting down...")
        print(f"[STATS] Accepted: {stats['accepted']} | Rejected: {stats['rejected']}")

    client.disconnect()
    print("[INFO] Disconnected from broker")


if __name__ == "__main__":
    main()