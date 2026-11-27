#!/usr/bin/env python3
"""Simulateur de boîtiers et de montre.

Commandes du mode interactif :
    1a   table 1 : bouton Appel (1b = Addition, 1e = Encore), réappuyer = impatience
    m    la montre prend l'appel le plus ancien
    l    afficher la liste des appels en attente reçue du serveur
    q    quitter
"""
import argparse
import json
import random
import threading
import time

import paho.mqtt.client as mqtt

KINDS = ["appel", "addition", "encore"]
KEYS = {"a": 0, "b": 1, "e": 2}
WATCH_STATUS = "tapserve/watch/sim/status"


class Boitier:

    def __init__(self, client: mqtt.Client, table: int):
        self.client, self.table = client, table
        self.slots = [{"st": "IDLE", "seq": 0, "t0": 0.0, "last_tx": 0.0} for _ in KINDS]
        self.seq = random.randint(0, 0xFFFF)
        client.subscribe(f"tapserve/box/{table}/state", qos=1)

    def appui(self, kind: int):
        s = self.slots[kind]
        if s["st"] in ("SENDING", "WAITING"):  # déjà en cours
            self.client.publish(f"tapserve/box/{self.table}/repress",
                                json.dumps({"kind": kind, "seq": s["seq"]}), qos=1)
            log(f"table {self.table} : nouvel appui {KINDS[kind]} (impatience)")
            return
        self.seq = (self.seq + 1) & 0xFFFF
        s.update(st="SENDING", seq=self.seq, t0=time.time(), last_tx=0.0)
        log(f"table {self.table} : appui {KINDS[kind]} (seq {self.seq})")

    def on_state(self, msg: dict):
        k, seq, st = msg.get("kind"), msg.get("seq"), msg.get("st")
        if not isinstance(k, int) or not 0 <= k < len(KINDS):
            return
        s = self.slots[k]
        if seq != s["seq"]:
            return
        if st == "received" and s["st"] == "SENDING":
            s["st"] = "WAITING"
            log(f"table {self.table} : {KINDS[k]} reçu par le serveur (LED fixe)")
        elif st == "claimed" and s["st"] in ("SENDING", "WAITING"):
            s["st"] = "IDLE"
            log(f"table {self.table} : {KINDS[k]} pris en charge (LED clignote lent)")

    def tick(self):
        # répète jusqu'à la réponse
        now = time.time()
        for k, s in enumerate(self.slots):
            if s["st"] != "SENDING":
                continue
            if now - s["t0"] > 8:
                s["st"] = "IDLE"
                log(f"table {self.table} : {KINDS[k]} sans réponse du serveur (LED d'erreur)")
            elif now - s["last_tx"] >= 1:
                self.client.publish(f"tapserve/box/{self.table}/call",
                                    json.dumps({"kind": k, "seq": s["seq"], "bat": random.randint(3700, 4150)}),
                                    qos=1)
                s["last_tx"] = now


class Montre:

    def __init__(self, client: mqtt.Client):
        self.client = client
        self.pending: list[dict] = []
        client.subscribe("tapserve/pending", qos=1)

    def on_pending(self, liste: list):
        nouveaux = [c for c in liste if c not in self.pending and
                    not any(c.get("seq") == p.get("seq") and c.get("table") == p.get("table") for p in self.pending)]
        self.pending = liste
        for c in nouveaux:
            log(f"montre : vibre, TABLE {c.get('table')} - {KINDS[c.get('kind', 0)].upper()}")

    def prendre(self):
        if not self.pending:
            log("montre : aucun appel en attente")
            return
        c = self.pending[0]  # le plus ancien
        self.client.publish("tapserve/claim",
                            json.dumps({"table": c["table"], "kind": c["kind"], "seq": c["seq"]}), qos=1)
        log(f"montre : \"J'arrive\" table {c['table']} ({KINDS[c['kind']]})")

    def afficher(self):
        if not self.pending:
            log("aucun appel en attente")
        for c in self.pending:
            log(f"  table {c['table']} - {KINDS[c['kind']]} - depuis {c.get('age', 0)} s")


def log(texte: str):
    print(f"{time.strftime('%H:%M:%S')}  {texte}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Simulateur de boîtiers et de montre TapServe")
    ap.add_argument("--broker", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--tables", type=int, default=2, help="nombre de boîtiers simulés (tables 1..N)")
    ap.add_argument("--auto", action="store_true", help="appels et prises en charge aléatoires")
    args = ap.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"tapserve-sim-{random.randint(0, 9999)}")
    boitiers: dict[int, Boitier] = {}
    montre: list[Montre] = []
    pret = threading.Event()

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log(f"broker refusé : {reason_code}")
            return
        boitiers.clear()
        for t in range(1, args.tables + 1):
            boitiers[t] = Boitier(c, t)
        montre[:] = [Montre(c)]
        for t in boitiers:
            c.publish(f"tapserve/box/{t}/status", "online", qos=1, retain=True)
        c.publish(WATCH_STATUS, "online", qos=1, retain=True)
        log(f"connecté au broker {args.broker}:{args.port}, {args.tables} boîtier(s) + 1 montre simulés")
        pret.set()

    def on_message(c, userdata, m):
        try:
            data = json.loads(m.payload)
        except ValueError:
            return
        if m.topic == "tapserve/pending" and montre:
            montre[0].on_pending(data)
        elif m.topic.startswith("tapserve/box/") and m.topic.endswith("/state"):
            b = boitiers.get(int(m.topic.split("/")[2]))
            if b:
                b.on_state(data)

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(args.broker, args.port, keepalive=15)
    except OSError as e:
        raise SystemExit(f"Broker injoignable sur {args.broker}:{args.port} ({e}). Mosquitto tourne ?")
    client.loop_start()
    if not pret.wait(5):
        raise SystemExit("Pas de réponse du broker.")

    def boucle():
        while True:
            for b in list(boitiers.values()):
                b.tick()
            time.sleep(0.2)

    threading.Thread(target=boucle, daemon=True).start()

    if args.auto:
        log("mode automatique (Ctrl+C pour arrêter)")
        try:
            while True:
                time.sleep(random.uniform(2, 6))
                if random.random() < 0.6:
                    random.choice(list(boitiers.values())).appui(random.randrange(len(KINDS)))
                elif montre:
                    montre[0].prendre()
        except KeyboardInterrupt:
            pass
    else:
        print(__doc__.split("Commandes du mode interactif :")[1])
        try:
            while True:
                cmd = input("> ").strip().lower()
                if cmd == "q":
                    break
                elif cmd == "m":
                    montre[0].prendre()
                elif cmd == "l":
                    montre[0].afficher()
                elif len(cmd) == 2 and cmd[0].isdigit() and cmd[1] in KEYS and int(cmd[0]) in boitiers:
                    boitiers[int(cmd[0])].appui(KEYS[cmd[1]])
                elif cmd:
                    log("commande inconnue (ex. 1a, 2b, m, l, q)")
        except (KeyboardInterrupt, EOFError):
            pass
    for t in boitiers:  # en quittant
        client.publish(f"tapserve/box/{t}/status", "offline", qos=1, retain=True)
    client.publish(WATCH_STATUS, "offline", qos=1, retain=True).wait_for_publish(3)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
