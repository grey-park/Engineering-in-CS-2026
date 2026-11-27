#!/usr/bin/env python3
"""Serveur TapServe. Idées du tableau de bord reprises du prototype de Dina."""
import argparse
import csv
import io
import json
import queue
import random
import sqlite3
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

BASE = Path(__file__).parent
KINDS = ["appel", "addition", "encore"]
TOPIC_PENDING = "tapserve/pending"
TOPIC_CLAIM = "tapserve/claim"
TEST_TABLE = 99

app = Flask(__name__)
db_lock = threading.Lock()
clients: list[queue.Queue] = []
# écrans qui ont le tableau de bord ouvert
viewers: dict[int, dict] = {}
LEASES = Path("/var/lib/misc/dnsmasq.leases")
state = {"mqtt_online": False, "alert_s": 120}
# appareils en ligne
devices: dict[str, dict] = {}
mqttc = None
DB: sqlite3.Connection


# Base de données

def init_db(path: Path):
    global DB
    DB = sqlite3.connect(path, check_same_thread=False)
    DB.row_factory = sqlite3.Row
    DB.executescript(
        """
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_no INTEGER NOT NULL,
            kind TEXT NOT NULL,
            seq INTEGER NOT NULL,
            battery_mv INTEGER,
            t_call REAL NOT NULL,
            t_claim REAL,
            t_cancel REAL,
            status TEXT NOT NULL DEFAULT 'pending',
            press_count INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_calls_open ON calls(table_no, kind, seq, status);
        """
    )
    # anciennes bases
    cols = [r["name"] for r in DB.execute("PRAGMA table_info(calls)")]
    if "press_count" not in cols:
        DB.execute("ALTER TABLE calls ADD COLUMN press_count INTEGER NOT NULL DEFAULT 1")
        DB.commit()
        print("[base] colonne press_count ajoutée")
    # un seul appel en attente par bouton
    cur = DB.execute(
        "UPDATE calls SET status='cancelled', t_cancel=? "
        "WHERE status='pending' AND id NOT IN "
        "(SELECT MAX(id) FROM calls WHERE status='pending' GROUP BY table_no, kind)",
        (time.time(),),
    )
    DB.commit()
    if cur.rowcount:
        print(f"[base] {cur.rowcount} ancien(s) appel(s) en attente annulé(s)")


def find_call(table: int, kind: str, seq: int):
    # dernière heure seulement
    return DB.execute(
        "SELECT * FROM calls WHERE table_no=? AND kind=? AND seq=? AND t_call > ? ORDER BY id DESC LIMIT 1",
        (table, kind, seq, time.time() - 3600),
    ).fetchone()


# Logique des appels

def on_call(table: int, kind: int, seq: int, bat: int | None):
    kname = KINDS[kind]
    with db_lock:
        row = find_call(table, kname, seq)
        if row is None:
            now = time.time()
            # remplace l'ancien appel
            old = DB.execute(
                "UPDATE calls SET status='cancelled', t_cancel=? "
                "WHERE table_no=? AND kind=? AND status='pending'",
                (now, table, kname),
            ).rowcount
            DB.execute(
                "INSERT INTO calls(table_no, kind, seq, battery_mv, t_call) VALUES (?,?,?,?,?)",
                (table, kname, seq, bat or None, now),
            )
            DB.commit()
            status, new = "pending", True
            if old:
                print(f"[annulé] table {table} {kname} : {old} ancien(s) appel(s) remplacé(s)")
        else:
            status, new = row["status"], False
    if status == "cancelled":
        return
    # on répond à chaque répétition
    mqtt_pub(f"tapserve/box/{table}/state",
             {"kind": kind, "seq": seq, "st": "claimed" if status == "claimed" else "received"})
    if new:
        print(f"[appel] table {table} {kname} seq={seq}")
        changed()


def on_cancel(table: int, kind: int, seq: int):
    with db_lock:
        cur = DB.execute(
            "UPDATE calls SET status='cancelled', t_cancel=? "
            "WHERE table_no=? AND kind=? AND seq=? AND status='pending'",
            (time.time(), table, KINDS[kind], seq),
        )
        DB.commit()
    if cur.rowcount:
        print(f"[annulé] table {table} {KINDS[kind]}")
        changed()


def on_repress(table: int, kind: int, seq: int):
    with db_lock:
        cur = DB.execute(
            "UPDATE calls SET press_count = press_count + 1 "
            "WHERE table_no=? AND kind=? AND seq=? AND status='pending' AND t_call > ?",
            (table, KINDS[kind], seq, time.time() - 3600),
        )
        DB.commit()
        row = find_call(table, KINDS[kind], seq) if cur.rowcount else None
    if row is not None:
        print(f"[appui] table {table} {KINDS[kind]} : {row['press_count']} appuis")
        changed()
        return
    # appel perdu (ex. réinitialisation) : on le rouvre
    with db_lock:
        old = find_call(table, KINDS[kind], seq)
        if old is not None and old["status"] == "cancelled":
            DB.execute("UPDATE calls SET status='pending', t_cancel=NULL, press_count=press_count+1 WHERE id=?",
                       (old["id"],))
            DB.commit()
    print(f"[appui] table {table} {KINDS[kind]} : appel inconnu du serveur, rouvert")
    on_call(table, kind, seq, None)
    changed()


def on_claim(table: int, kind: int, seq: int):
    with db_lock:
        cur = DB.execute(
            "UPDATE calls SET status='claimed', t_claim=? "
            "WHERE table_no=? AND kind=? AND seq=? AND status='pending'",
            (time.time(), table, KINDS[kind], seq),
        )
        DB.commit()
        row = find_call(table, KINDS[kind], seq)
    if row is not None and row["status"] == "claimed":
        mqtt_pub(f"tapserve/box/{table}/state", {"kind": kind, "seq": seq, "st": "claimed"})
    if cur.rowcount:
        print(f"[pris] table {table} {KINDS[kind]}")
        changed()


def changed():
    publish_pending()
    broadcast()


# MQTT

def mqtt_pub(topic: str, obj, retain: bool = False):
    if mqttc is not None and state["mqtt_online"]:
        mqttc.publish(topic, json.dumps(obj, separators=(",", ":")), qos=1, retain=retain)


def publish_pending():
    now = time.time()
    with db_lock:
        rows = DB.execute(
            "SELECT table_no, kind, seq, t_call, press_count FROM calls WHERE status='pending' ORDER BY t_call LIMIT 16"
        ).fetchall()
    mqtt_pub(TOPIC_PENDING, [
        {"table": r["table_no"], "kind": KINDS.index(r["kind"]), "seq": r["seq"], "age": int(now - r["t_call"]),
         "press_count": r["press_count"]}
        for r in rows
    ], retain=True)


def on_status(topic: str, payload: bytes):
    parts = topic.split("/")
    if len(parts) != 4:
        return
    kind, ident = parts[1], parts[2]
    if kind not in ("box", "watch") or not ident:
        return
    name = f"Table {ident}" if kind == "box" else f"Montre {ident}"
    online = payload.decode("utf-8", "ignore").strip() == "online"
    prev = devices.get(name)
    if prev is None or prev["online"] != online:
        devices[name] = {"kind": kind, "online": online, "since": time.time()}
        print(f"[appareil] {name} {'en ligne' if online else 'hors ligne'}")
        broadcast()


def handle_mqtt(topic: str, payload: bytes):
    if topic.endswith("/status"):
        on_status(topic, payload)
        return
    try:
        msg = json.loads(payload)
        parts = topic.split("/")
        if topic == TOPIC_CLAIM:
            table = int(msg["table"])
        elif len(parts) == 4 and parts[0] == "tapserve" and parts[1] == "box":
            table = int(parts[2])
        else:
            return
        kind, seq = int(msg["kind"]), int(msg["seq"])
        if not (1 <= table <= 99 and 0 <= kind < len(KINDS)):
            return
    except (ValueError, KeyError, TypeError) as e:
        print(f"[mqtt] message ignoré ({e}) sur {topic}: {payload[:100]!r}")
        return

    if topic == TOPIC_CLAIM:
        on_claim(table, kind, seq)
    elif parts[3] == "call":
        bat = msg.get("bat")
        on_call(table, kind, seq, int(bat) if isinstance(bat, (int, float)) else None)
    elif parts[3] == "cancel":
        on_cancel(table, kind, seq)
    elif parts[3] == "repress":
        on_repress(table, kind, seq)


def mqtt_start(host: str, port: int):
    global mqttc
    import paho.mqtt.client as mqtt

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tapserve-server")

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[mqtt] connexion refusée : {reason_code}")
            return
        print(f"[mqtt] connecté à {host}:{port}")
        state["mqtt_online"] = True
        client.subscribe([("tapserve/box/+/call", 1), ("tapserve/box/+/cancel", 1),
                          ("tapserve/box/+/repress", 1), (TOPIC_CLAIM, 1),
                          ("tapserve/box/+/status", 1), ("tapserve/watch/+/status", 1)])
        changed()

    def on_disconnect(client, userdata, flags, reason_code, properties):
        print(f"[mqtt] déconnecté ({reason_code}), reconnexion...")
        state["mqtt_online"] = False
        broadcast()

    c.on_connect = on_connect
    c.on_disconnect = on_disconnect
    c.on_message = lambda client, userdata, m: handle_mqtt(m.topic, m.payload)
    c.reconnect_delay_set(1, 10)
    mqttc = c
    c.connect_async(host, port, keepalive=15)
    c.loop_start()

    def refresher():
        while True:
            time.sleep(10)
            publish_pending()

    threading.Thread(target=refresher, daemon=True).start()


# Simulation

def simulator():
    print("[sim] mode simulation : faux appels")
    state["mqtt_online"] = True
    for name, kind in (("Table 1", "box"), ("Table 2", "box"), ("Montre sim", "watch")):
        devices[name] = {"kind": kind, "online": True, "since": time.time()}
    seq = 0
    open_calls = []
    while True:
        if random.random() < 0.35:
            table, kind = random.randint(1, 2), random.randrange(3)
            if not any(o[:2] == (table, kind) for _, o in open_calls):
                seq += 1
                on_call(table, kind, seq, random.randint(3600, 4150))
                open_calls.append((time.time() + random.uniform(4, 40), (table, kind, seq)))
        for due, c in list(open_calls):
            if time.time() >= due:
                open_calls.remove((due, c))
                (on_cancel if random.random() < 0.1 else on_claim)(*c)
        broadcast()
        time.sleep(2)


# Tableau de bord

def snapshot() -> dict:
    day_start = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    with db_lock:
        pending = [dict(r) for r in DB.execute(
            "SELECT * FROM calls WHERE status='pending' ORDER BY t_call")]
        recent = [dict(r) for r in DB.execute(
            "SELECT * FROM calls ORDER BY id DESC LIMIT 15")]
        stats = dict(DB.execute(
            "SELECT COUNT(*) AS total, "
            "AVG(CASE WHEN status='claimed' THEN t_claim - t_call END) AS avg_resp, "
            "MAX(CASE WHEN status='claimed' THEN t_claim - t_call END) AS max_resp "
            "FROM calls WHERE t_call >= ?", (day_start,)).fetchone())
        per_table = [dict(r) for r in DB.execute(
            "SELECT table_no, COUNT(*) AS n, "
            "AVG(CASE WHEN status='claimed' THEN t_claim - t_call END) AS avg_resp "
            "FROM calls WHERE t_call >= ? GROUP BY table_no ORDER BY table_no", (day_start,))]
        batteries = [dict(r) for r in DB.execute(
            "SELECT table_no, battery_mv FROM calls WHERE id IN "
            "(SELECT MAX(id) FROM calls GROUP BY table_no) ORDER BY table_no")]
        hourly, daily = history()
    now = time.time()
    return {
        "now": now,
        "mqtt_online": state["mqtt_online"],
        "alert_s": state["alert_s"],
        "late": sum(1 for c in pending if now - c["t_call"] > state["alert_s"]),
        "pending": pending,
        "recent": recent,
        "stats": stats,
        "per_table": per_table,
        "batteries": batteries,
        "viewers": sorted(viewers.values(), key=lambda v: v["since"]),
        "devices": sorted(({"name": n, **d} for n, d in devices.items()),
                          key=lambda d: (d["kind"] != "box", d["name"])),
        "hourly": hourly,
        "daily": daily,
    }


def history():
    # par heure et par jour
    now = time.time()
    lt = time.localtime(now)
    hour0 = time.mktime(lt[:3] + (lt.tm_hour, 0, 0, 0, 0, -1)) - 23 * 3600
    day0 = time.mktime(lt[:3] + (0, 0, 0, 0, 0, -1))
    days = [time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - i, 0, 0, 0, 0, 0, -1)) for i in range(13, -1, -1)]
    hours = [0] * 24
    per_day = [[0, 0.0, 0] for _ in days]
    for r in DB.execute("SELECT t_call, t_claim, status FROM calls WHERE t_call >= ? AND table_no != ?",
                        (min(hour0, days[0]), TEST_TABLE)):
        t = r["t_call"]
        if t >= hour0:
            hours[min(23, int((t - hour0) // 3600))] += 1
        for i in range(len(days) - 1, -1, -1):
            if t >= days[i]:
                d = per_day[i]
                d[0] += 1
                if r["status"] == "claimed" and r["t_claim"]:
                    d[1] += r["t_claim"] - t
                    d[2] += 1
                break
    hourly = [{"label": time.strftime("%Hh", time.localtime(hour0 + i * 3600)), "n": n} for i, n in enumerate(hours)]
    daily = [{"label": time.strftime("%d.%m", time.localtime(d)), "n": v[0],
              "avg_resp": round(v[1] / v[2]) if v[2] else None, "today": d == day0}
             for d, v in zip(days, per_day)]
    return hourly, daily


def broadcast():
    data = json.dumps(snapshot())
    for q in list(clients):
        try:
            q.put_nowait(data)
        except queue.Full:
            pass


@app.route("/")
def index():
    return send_from_directory(BASE, "dashboard.html")


@app.route("/api/state")
def api_state():
    return jsonify(snapshot())


@app.route("/api/reset", methods=["POST"])
def api_reset():
    with db_lock:
        n = DB.execute("DELETE FROM calls").rowcount
        DB.commit()
    print(f"[reset] {n} appel(s) effacé(s)")
    changed()
    return jsonify({"ok": True, "deleted": n})


@app.route("/api/claim/<int:call_id>", methods=["POST"])
def api_claim(call_id: int):
    # bouton "Fait"
    with db_lock:
        row = DB.execute("SELECT table_no, kind, seq FROM calls WHERE id=? AND status='pending'",
                         (call_id,)).fetchone()
    if row is None:
        return jsonify({"ok": False, "error": "appel introuvable ou déjà traité"}), 404
    on_claim(row["table_no"], KINDS.index(row["kind"]), row["seq"])
    return jsonify({"ok": True})


@app.route("/api/test", methods=["POST"])
def api_test():
    seq = random.randint(1, 0xFFFF)
    if mqttc is not None and state["mqtt_online"]:
        mqtt_pub(f"tapserve/box/{TEST_TABLE}/call", {"kind": 0, "seq": seq, "bat": 0})
    else:
        on_call(TEST_TABLE, 0, seq, None)
    return jsonify({"ok": True, "table": TEST_TABLE, "seq": seq})


@app.route("/export.csv")
def export_csv():
    with db_lock:
        rows = DB.execute("SELECT * FROM calls ORDER BY t_call").fetchall()
    iso = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)) if t else ""
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")  # pour Excel en français
    w.writerow(["id", "table", "type", "statut", "appel", "pris_en_charge", "annule",
                "temps_reponse_s", "appuis", "batterie_mv"])
    for r in rows:
        resp = round(r["t_claim"] - r["t_call"]) if r["t_claim"] else ""
        w.writerow([r["id"], r["table_no"], r["kind"], r["status"], iso(r["t_call"]), iso(r["t_claim"]),
                    iso(r["t_cancel"]), resp, r["press_count"], r["battery_mv"] or ""])
    name = time.strftime("tapserve-%Y%m%d-%H%M.csv")
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",  # pour les accents dans Excel
                    headers={"Content-Disposition": f"attachment; filename={name}"})


def device_name(ip: str) -> str:
    # nom donné au DHCP du Pi (ex. Galaxy-Tab-S5e)
    try:
        for line in LEASES.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[2] == ip and parts[3] != "*":
                return parts[3]
    except OSError:
        pass
    return ""


@app.route("/events")
def events():
    q: queue.Queue = queue.Queue(maxsize=20)
    ip = request.headers.get("X-Forwarded-For", request.remote_addr).removeprefix("::ffff:")
    viewers[id(q)] = {"ip": ip, "name": device_name(ip), "since": time.time()}
    clients.append(q)
    broadcast()  # les autres écrans voient le nouveau venu

    def stream():
        try:
            yield f"data: {json.dumps(snapshot())}\n\n"
            while True:
                try:
                    yield f"data: {q.get(timeout=15)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            clients.remove(q)
            viewers.pop(id(q), None)
            broadcast()

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def listen_host() -> str:
    if sys.platform != "linux":
        return "0.0.0.0"
    import socket
    try:
        socket.socket(socket.AF_INET6, socket.SOCK_STREAM).close()
        return "::"
    except OSError:
        return "0.0.0.0"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="localhost", help="adresse du broker MQTT")
    ap.add_argument("--mqtt-port", type=int, default=1883)
    ap.add_argument("--simulate", action="store_true", help="faux appels, sans broker (base tapserve_sim.db)")
    ap.add_argument("--port", type=int, default=8000, help="port du tableau de bord")
    ap.add_argument("--alerte", type=int, default=120, help="secondes avant qu'un appel soit 'en retard'")
    args = ap.parse_args()
    state["alert_s"] = args.alerte

    init_db(BASE / ("tapserve_sim.db" if args.simulate else "tapserve.db"))
    if args.simulate:
        threading.Thread(target=simulator, daemon=True).start()
    else:
        mqtt_start(args.broker, args.mqtt_port)
    # "::" écoute aussi en IPv6 sur Linux (tapserve.local) ; repli IPv4 si la machine n'a pas d'IPv6
    app.run(host=listen_host(), port=args.port, threaded=True)
