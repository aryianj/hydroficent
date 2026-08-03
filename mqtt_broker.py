import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime, timezone
import threading

class WaterSensorMQTT:
    """
    A water sensor that publishes readings to MQTT.
    """

    def __init__(self, device_id, location, broker="localhost", port=1883):
        self.device_id = device_id
        self.location = location
        self.counter = 0

        # MQTT setup
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.connect(broker, port)
        self.client.loop_start()

        # Topic for this sensor
        self.topic = f"hydroficient/grandmarina/sensors/{self.location}/readings"

        # Base values for realistic variation
        self.base_pressure_up = 82
        self.base_pressure_down = 76
        self.base_flow = 40

    def get_reading(self):
        """Generate a sensor reading with realistic variation."""
        self.counter += 1
        return {
            "device_id": self.device_id,  # identity
            "location": self.location,    # context (optional but recommended)
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "counter": self.counter,
            "pressure_upstream": round(self.base_pressure_up + random.uniform(-2, 2), 1),
            "pressure_downstream": round(self.base_pressure_down + random.uniform(-2, 2), 1),
            "flow_rate": round(self.base_flow + random.uniform(-3, 3), 1),
        }

    def publish_reading(self):
        """Generate a reading and publish it to MQTT."""
        reading = self.get_reading()
        self.client.publish(self.topic, json.dumps(reading))
        return reading

    def run_continuous(self, interval=2):
        """Publish readings continuously at the specified interval."""
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

def run_sensor(device_id, location, interval):
    sensor = WaterSensorMQTT(device_id=device_id, location=location)
    sensor.run_continuous(interval)

def on_message(client, userdata, msg):
    topic = msg.topic

    if "/sensors/" in topic:
        handle_sensor_reading(msg)
    elif "/alerts/" in topic:
        handle_alert(msg)
    elif "/commands/" in topic:
        handle_command(msg)
    elif "/status/" in topic:
        handle_status(msg)
    else:
        print(f"Unknown topic: {topic}")

def handle_sensor_reading(msg):
    try:
        data = json.loads(msg.payload.decode())
        display_reading(data)  # Uses your existing display_reading() function
    except json.JSONDecodeError:
        print(f"\n[RAW SENSOR MESSAGE] {msg.topic}")
        print(f"      {msg.payload.decode()}")

def handle_alert(msg):
    print(f"\n*** ALERT ***")
    print(f"Topic: {msg.topic}")
    print(f"Message: {msg.payload.decode()}")

def handle_command(msg):
    print(f"\n[COMMAND] {msg.topic}: {msg.payload.decode()}")

def handle_status(msg):
    # Could update a "last seen" tracker
    print(f"\n[STATUS] {msg.topic}: {msg.payload.decode()}")

devices = [
    {"device_id": "GM-HYDROLOGIC-01", "location": "main-building"},
    {"device_id": "GM-HYDROLOGIC-02", "location": "pool-wing"},
    {"device_id": "GM-HYDROLOGIC-03", "location": "kitchen"},
]

threads = []
for d in devices:
    t = threading.Thread(target=run_sensor, args=(d["device_id"], d["location"], 2), daemon=True)
    t.start()
    threads.append(t)

print("All sensors running. Press Ctrl+C to stop.")
