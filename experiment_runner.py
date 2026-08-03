import paho.mqtt.client as mqtt
import argparse
import json
import time
from datetime import datetime, timezone, timedelta
import random
import ssl
from pathlib import Path
import statistics
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

TLS_CONFIG = {
    "ca_certs": "certs/ca.pem",      # Path to CA certificate
    "wrong_ca_certs": "certs/wrong-ca.pem",
    "broker_host": "localhost",
    "broker_port": 8883,              # TLS port (not 1883!)
}

def generate_wrong_ca_certificate(output_path=TLS_CONFIG["wrong_ca_certs"]):
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True)

    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_name = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Grand Marina Hotel"),
        x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Untrusted Test CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Grand Marina Wrong CA"),
    ])

    wrong_cert = (
        x509.CertificateBuilder()
        .subject_name(wrong_name)
        .issuer_name(wrong_name)
        .public_key(wrong_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(wrong_key, hashes.SHA256())
    )

    with open(output_path, "wb") as file_handle:
        file_handle.write(wrong_cert.public_bytes(serialization.Encoding.PEM))

    print(f"Saved: {output_path}")
    return output_path

class WaterSensorMQTT:
    def __init__(self, device_id, location, tls_enabled=True, auto_connect=True):
        self.device_id = device_id
        self.location = location
        self.counter = 0
        self.tls_enabled = tls_enabled
        self.auto_connect = auto_connect

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        self.topic = f"grandmarina/sensors/{self.location}/readings"

        self.base_pressure_up = 82
        self.base_pressure_down = 76
        self.base_flow = 40

        if self.auto_connect:
            self.connect()

    def connect(self, ca_path=None, verify=True, insecure=False):
        broker_port = TLS_CONFIG["broker_port"] if self.tls_enabled else 1883

        if self.tls_enabled:
            tls_ca_path = Path(ca_path or TLS_CONFIG["ca_certs"])
            if verify and not tls_ca_path.exists():
                raise FileNotFoundError(
                    f"CA certificate not found: {tls_ca_path}. Run generate_certs.py first!"
                )

            if verify:
                self.client.tls_set(
                    ca_certs=str(tls_ca_path),
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS,
                )
            else:
                self.client.tls_set(
                    cert_reqs=ssl.CERT_NONE,
                    tls_version=ssl.PROTOCOL_TLS,
                )
                self.client.tls_insecure_set(True)

        self.client.connect(TLS_CONFIG["broker_host"], broker_port, keepalive=60)
        self.client.loop_start()

    def get_reading(self):
        self.counter += 1
        return {
            "device_id": self.device_id, 
            "location": self.location,    
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "counter": self.counter,
            "pressure_upstream": round(self.base_pressure_up + random.uniform(-2, 2), 1),
            "pressure_downstream": round(self.base_pressure_down + random.uniform(-2, 2), 1),
            "flow_rate": round(self.base_flow + random.uniform(-3, 3), 1),
        }

    def publish_reading(self):
        reading = self.get_reading()
        self.client.publish(self.topic, json.dumps(reading))
        return reading

    def run_continuous(self, interval=2):
        print(f"Starting device: {self.device_id}")
        print(f"Location: {self.location}")
        print(f"Publishing to: {self.topic}")
        print(f"Interval: {interval} seconds")
        print("-" * 40)

        try:
            while True:
                reading = self.publish_reading()
                print(f"[{reading['counter']}] Pressure: {reading['pressure_upstream']}/{reading['pressure_downstream']} PSI, Flow: {reading['flow_rate']} gal/min")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nSensor stopped.")
            self.client.loop_stop()
            self.client.disconnect()

    def run_latency_test(self, messages=1, tls=True):
        try:
            latency = []
            print("=" * 40)
            print("  Latency Test")
            print(f"  TLS: {'ON' if tls else 'OFF'}")
            print(f"  Messages: {messages}")
            print("=" * 40)

            print()
            for i in range(1, messages + 1):
                start = time.perf_counter()
                self.publish_reading()
                latency.append((time.perf_counter() - start) * 1000)

                if i % 10 == 0 or i == messages:
                    print(f"  Sent {i}/{messages} messages...")

            print()
            print("=" * 40)
            print(f"  Latency Results (TLS {'ON' if tls else 'OFF'})")
            print("=" * 40)
            print(f"  Messages sent: {messages}")
            print(f"  Average latency: {sum(latency) / len(latency):.2f} ms")
            print(f"  Min latency: {min(latency):.2f} ms")
            print(f"  Max latency: {max(latency):.2f} ms")
            print(f"  Std deviation: {statistics.stdev(latency):.2f} ms" if len(latency) > 1 else "  Std deviation: 0.00 ms")
            print("=" * 50)
        except KeyboardInterrupt:
            print("\nSensor stopped.")
            self.client.loop_stop()
            self.client.disconnect()

    def run_connection_test(self, tls=True, ca_path=None, verify=True, timeout=5):
        test_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        connected = False

        def on_connect(client, userdata, flags, reason_code, properties):
            nonlocal connected
            connected = True

        print("=" * 50)
        print("  Connection Test")
        print(f"  TLS: {'ON' if tls else 'OFF'}")
        if tls and verify:
            print(f"  CA Certificate: {ca_path or TLS_CONFIG['ca_certs']}")
        elif tls and not verify:
            print("  CA Certificate: NONE")
        else:
            print("  CA Certificate: NONE")
        print("=" * 50)

        test_client.on_connect = on_connect

        if tls:
            if verify:
                tls_ca_path = Path(ca_path or TLS_CONFIG["ca_certs"])
                if not tls_ca_path.exists():
                    raise FileNotFoundError(
                        f"CA certificate not found: {tls_ca_path}. Run generate_certs.py first!"
                    )

                test_client.tls_set(
                    ca_certs=str(tls_ca_path),
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS,
                )
            else:
                test_client.tls_set(
                    cert_reqs=ssl.CERT_NONE,
                    tls_version=ssl.PROTOCOL_TLS,
                )
                test_client.tls_insecure_set(True)

        broker_port = TLS_CONFIG["broker_port"] if tls else 1883

        try:
            test_client.connect(TLS_CONFIG["broker_host"], broker_port, keepalive=60)
            test_client.loop_start()

            start_time = time.time()
            while not connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if connected:
                print()
                print("SUCCESS: Connected to broker!")
            else:
                print()
                print("FAILED: Connection test timed out before broker acknowledged the connection.")
        except Exception as error:
            print()
            print(f"FAILED: {error}")
        finally:
            test_client.loop_stop()
            test_client.disconnect()

    def run_stress_test(self, rate=10, duration=30, tls=True):
        try:
            self.connect()

            sent = 0
            errors = 0
            start_time = time.perf_counter()
            deadline = start_time + duration

            while time.perf_counter() < deadline:
                reading = self.get_reading()
                publish_info = self.client.publish(self.topic, json.dumps(reading), qos=1)

                if publish_info.rc != mqtt.MQTT_ERR_SUCCESS:
                    errors += 1
                else:
                    publish_info.wait_for_publish(timeout=1)

                    if publish_info.is_published():
                        sent += 1
                    else:
                        errors += 1
                time.sleep(1 / rate)


            elapsed = time.perf_counter() - start_time
            actual_rate = sent / elapsed if elapsed > 0 else 0
            total_attempts = sent + errors
            success_rate = (sent / total_attempts * 100) if total_attempts else 0
            status = "PASS" if errors == 0 else "DEGRADED"

            print("=" * 40)
            print(f"Stress Test Results TLS: {'ON' if tls else 'OFF'}")
            print(f"Target rate: {rate} msg/sec")
            print(f"Actual rate: {actual_rate:.2f} msg/sec")
            print(f"Messages sent: {sent}")
            print(f"Errors: {errors}")
            print(f"Success rate: {success_rate:.2f}%")
            print(f"Status: {status}")
            print("=" * 40)

        except KeyboardInterrupt:
            print("\nSensor stopped.")
            self.client.loop_stop()
            self.client.disconnect()

            
def run_sensor(device_id, location, messages, mode, duration, rate, tls_enabled=True, no_ca=False):
    sensor = WaterSensorMQTT(
        device_id=device_id,
        location=location,
        tls_enabled=tls_enabled,
        auto_connect=False,
    )

    if mode == 'publish':
        sensor.connect()
    elif mode == 'connect':
        sensor.run_connection_test(
            tls=tls_enabled,
            ca_path=None if no_ca else TLS_CONFIG["ca_certs"],
            verify=not no_ca,
        )
    elif mode == 'generate-wrong-ca':
        generate_wrong_ca_certificate()
    elif mode == 'test-wrong-ca':
        sensor.run_connection_test(
            tls=True,
            ca_path=TLS_CONFIG["wrong_ca_certs"],
            verify=True,
        )
    elif mode == 'latency':
        sensor.run_latency_test(messages, tls=tls_enabled,)
    elif mode == 'stress':
        sensor.run_stress_test(rate, duration, tls=tls_enabled)
    else:
        raise ValueError(f"Unsupported mode: {mode}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-id", default="GM-HYDROLOGIC-01")
    parser.add_argument("--location", default="main-building")
    parser.add_argument("--interval", type=int, default=2)
    parser.add_argument("--tls", choices=("on", "off"), default="on")
    parser.add_argument("--no-ca", action="store_true")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument(
        "--mode",
        choices=("publish", "connect", "generate-wrong-ca", "test-wrong-ca", "latency", "stress"),
        default="publish",
    )
    parser.add_argument("--duration", type=int, default= 30)
    parser.add_argument("--rate", type=int, default=10)


    args = parser.parse_args()

    run_sensor(
        device_id=args.device_id,
        location=args.location,
        messages=args.count,
        mode=args.mode,
        duration=args.duration,
        rate=args.rate,
        tls_enabled=(args.tls == "on"),
        no_ca=args.no_ca,
    )


if __name__ == "__main__":
    main()
