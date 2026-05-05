import paho.mqtt.client as mqtt
import json
import time
import random

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
client.connect("127.0.0.1", 1883, 60)
def on_connect(client, userdata, flags, rc):
    print("Connecté MQTT, code:", rc)

client.on_connect = on_connect
try:
    while True:
        data = {
            "id": "casque_test",
            "temp": round(random.uniform(25, 45), 1),
            "humid": random.randint(30, 70),
            "pressure": 1012,
            "altitude": random.randint(100, 200),
            "co_ppm": random.randint(5, 80),
            "mq2": random.randint(50, 400),
            "mq135": random.randint(50, 300),
            "heart_rate": random.randint(60, 120),
            "spo2": random.randint(85, 100),
            "fall": random.choice([False, False, True]),
            "sos": False,
            "alert_level": random.choice([0, 1, 2])
        }

        client.publish("casque/data", json.dumps(data))
        print("Envoyé :", data)
        time.sleep(2)

except KeyboardInterrupt:
    print("Arrêt du programme")
    client.disconnect()