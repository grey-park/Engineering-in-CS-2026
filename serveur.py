import json
import paho.mqtt.client as mqtt

demandes = {}  # id -> {"device": ..., "status": ..., "data": ...}

def publier_statut(client, device, id_, status):
    payload = json.dumps({"id": id_, "status": status})
    client.publish(f"boitier/{device}/statut", payload, qos=1)
    print(f"[{device}] {id_} -> {status}")

def on_connect(client, userdata, flags, reason_code, properties):
    print("Serveur connecté au broker :", reason_code)
    client.subscribe("boitier/+/demande", qos=1)
    client.subscribe("serveur/done", qos=1)

def on_message(client, userdata, msg):
    # Marquer une demande comme faite
    if msg.topic == "serveur/done":
        id_ = msg.payload.decode().strip()
        d = demandes.get(id_)
        if d:
            d["status"] = "done"
            publier_statut(client, d["device"], id_, "done")
        else:
            print(f"Id inconnu : {id_}")
        return

    # Nouvelle demande d'un boîtier
    device = msg.topic.split("/")[1]
    try:
        data = json.loads(msg.payload)
        id_ = data["id"]
    except (ValueError, KeyError):
        print("Message invalide :", msg.payload)
        return

    if id_ in demandes:  # doublon : on renvoie le statut actuel
        publier_statut(client, device, id_, demandes[id_]["status"])
        return

    demandes[id_] = {"device": device, "status": "received", "data": data}
    publier_statut(client, device, id_, "received")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("127.0.0.1", 1883)
client.loop_forever()
