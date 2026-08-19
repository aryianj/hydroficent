import paho.mqtt.client as mqtt
import json
from datetime import datetime, timezone
import ssl
from pathlib import Path

TLS_CONFIG = {
    "ca_certs": "certs/ca.pem",      
    "broker_host": "localhost",
    "broker_port": 8883,            
}

def on_connect(client, userdata, flags, reason_code, properties):
    print('=' * 50)
    print('GRAND MARINA WATER MONITORING DASHBOARD')
    print(f"Connected at: {datetime.now(timezone.utc).strftime('%m-%d-%Y %T:%M')} ")
    print('=' * 50)
    print('\n')
    client.subscribe("hydroficient/grandmarina/#")

def on_message(client, userdata, msg):

    try:
        data = json.loads(msg.payload.decode())
        print("-" * 40)
        print(f"{'Location:':<12} {data['location']}")
        print(f"{'Device ID:':<12} {data['device_id']}")
        print(f"{'Time:':<12} {data['timestamp']}")
        print(f"{'Count:':<12} #{data['counter']}")
        print("-" * 40)
        print(f"{'Pressure:':<12} {data['pressure_upstream']} / {data['pressure_downstream']} PSI")
        print(f"{'Flow:':<12} {data['flow_rate']} gal/min")
    except json.JSONDecodeError:
        print(f"Raw message: {msg.payload.decode()}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.tls_set(
    ca_certs=TLS_CONFIG["ca_certs"],   
    certfile=None,                      
    keyfile=None,                        
    cert_reqs=ssl.CERT_REQUIRED,        
    tls_version=ssl.PROTOCOL_TLS,        
)

ca_path = Path(TLS_CONFIG["ca_certs"])
if not ca_path.exists():
    print(f"CA certificate not found: {ca_path}")
    print("Run generate_certs.py first!")
    exit(0)

client.connect(
    TLS_CONFIG["broker_host"],
    TLS_CONFIG["broker_port"],       # Port 8883, not 1883!
    keepalive=60
)
# Parses incoming JSON messages
client.loop_forever()
