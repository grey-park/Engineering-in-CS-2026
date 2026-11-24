import json, uuid
import paho.mqtt.client as mqtt

DEVICE_ID = "esp32-01"
TOPIC_DEMANDE = f"boitier/{DEVICE_ID}/demande"
TOPIC_STATUT = f"boitier/{DEVICE_ID}/statut"

def on_connect(client, userdata, flags, reason_code, properties):
    print("Boîtier simulé connecté (appuyez sur Entrée pour une demande)")
    client.subscribe(TOPIC_STATUT, qos=1)

def on_message(client, userdata, msg):
    print(f"Statut reçu : {msg.payload.decode()}")

def envoyer_demande(client):
    id_ = f"{DEVICE_ID}-{uuid.uuid4().hex[:6]}"
    payload = json.dumps({"id": id_, "type": "appel"})
    client.publish(TOPIC_DEMANDE, payload, qos=1)
    print(f"Demande envoyée : {payload}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("127.0.0.1", 1883)
client.loop_start()

try:
    while True:
        input()
        envoyer_demande(client)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()
