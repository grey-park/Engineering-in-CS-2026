import csv, io, json, os, sqlite3, threading, time, uuid
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string, Response, request
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
PORT = 1883
WEB_HOST = "127.0.0.1"   # mettre "0.0.0.0" pour accéder depuis la tablette sur le réseau (sans authentification !)
WEB_PORT = 5000
ALERTE_MIN = 10          # alerte si une demande attend plus de 10 minutes
EN_LIGNE_S = 120         # boîtier considéré en ligne s'il a parlé il y a moins de 2 minutes
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demandes.db")

PRODUITS = ["Café", "Thé", "Chocolat chaud", "Eau", "Jus d'orange"]

app = Flask(__name__)
verrou = threading.Lock()
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


def sql(requete, params=()):
    with verrou:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        try:
            lignes = conn.execute(requete, params).fetchall()
            conn.commit()
            return lignes
        finally:
            conn.close()


sql("""CREATE TABLE IF NOT EXISTS demandes (
    id TEXT PRIMARY KEY,
    device TEXT NOT NULL,
    type TEXT,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    done_at REAL)""")


def publier_statut(device, id_, status):
    mqtt_client.publish(f"boitier/{device}/statut",
                        json.dumps({"id": id_, "status": status}), qos=1)


def enregistrer(device, id_, type_):
    existe = sql("SELECT status FROM demandes WHERE id=?", (id_,))
    if existe:  # doublon (renvoi du boîtier) : on redonne le statut actuel
        publier_statut(device, id_, existe[0]["status"])
        return
    sql("INSERT INTO demandes (id, device, type, status, created_at) VALUES (?,?,?,?,?)",
        (id_, device, type_, "received", time.time()))
    publier_statut(device, id_, "received")


def marquer_fait(id_):
    ligne = sql("SELECT device, status FROM demandes WHERE id=?", (id_,))
    if not ligne or ligne[0]["status"] == "done":
        return False
    sql("UPDATE demandes SET status='done', done_at=? WHERE id=?", (time.time(), id_))
    publier_statut(ligne[0]["device"], id_, "done")
    return True


def on_connect(client, userdata, flags, reason_code, properties):
    print("MQTT connecté :", reason_code)
    client.subscribe("boitier/+/demande", qos=1)
    client.subscribe("serveur/done", qos=1)


def on_message(client, userdata, msg):
    if msg.topic == "serveur/done":
        marquer_fait(msg.payload.decode().strip())
        return
    try:
        data = json.loads(msg.payload)
        enregistrer(msg.topic.split("/")[1], data["id"], data.get("type", "appel"))
    except (ValueError, KeyError):
        print("Message ignoré :", msg.payload)


@app.route("/")
def index():
    return render_template_string(HTML, seuil=ALERTE_MIN)


@app.route("/tablette")
def page_tablette():
    return render_template_string(TABLETTE_HTML)


@app.route("/commande")
def page_commande():
    return render_template_string(COMMANDE_HTML, produits=PRODUITS)


@app.route("/api/stats")
def api_stats():
    lignes = sql("SELECT * FROM demandes")
    maintenant = datetime.now()
    aujourdhui = maintenant.date()
    now = time.time()

    heures = [maintenant.replace(minute=0, second=0, microsecond=0) - timedelta(hours=i)
              for i in range(23, -1, -1)]
    cle_h = {h.strftime("%Y%m%d%H"): i for i, h in enumerate(heures)}
    par_heure = [0] * 24

    jours = [aujourdhui - timedelta(days=i) for i in range(13, -1, -1)]
    cle_j = {j.isoformat(): i for i, j in enumerate(jours)}
    par_jour = [0] * 14
    delais_jour = [[] for _ in range(14)]

    par_device, vus, delais = {}, {}, []
    today_count = 0

    for l in lignes:
        dt = datetime.fromtimestamp(l["created_at"])
        if dt.date() == aujourdhui:
            today_count += 1
        i = cle_h.get(dt.strftime("%Y%m%d%H"))
        if i is not None:
            par_heure[i] += 1
        j = cle_j.get(dt.date().isoformat())
        if j is not None:
            par_jour[j] += 1
        par_device[l["device"]] = par_device.get(l["device"], 0) + 1
        vus[l["device"]] = max(vus.get(l["device"], 0), l["created_at"], l["done_at"] or 0)
        if l["status"] == "done" and l["done_at"]:
            d = l["done_at"] - l["created_at"]
            delais.append(d)
            if j is not None:
                delais_jour[j].append(d)

    en_attente = sorted(
        [{"id": l["id"], "device": l["device"], "type": l["type"],
          "depuis_s": int(now - l["created_at"])}
         for l in lignes if l["status"] != "done"],
        key=lambda x: -x["depuis_s"])

    return jsonify({
        "kpis": {
            "total": len(lignes),
            "aujourdhui": today_count,
            "en_attente": len(en_attente),
            "terminees": sum(1 for l in lignes if l["status"] == "done"),
            "delai_moyen_s": round(sum(delais) / len(delais)) if delais else None,
            "en_retard": sum(1 for a in en_attente if a["depuis_s"] > ALERTE_MIN * 60),
        },
        "par_heure": {"labels": [h.strftime("%H:00") for h in heures], "valeurs": par_heure},
        "par_jour": {
            "labels": [j.strftime("%d/%m") for j in jours],
            "valeurs": par_jour,
            "delai_moyen_min": [round(sum(x) / len(x) / 60, 1) if x else None for x in delais_jour],
        },
        "par_device": par_device,
        "en_attente": en_attente,
        "boitiers": [{"device": d, "vu_il_y_a_s": int(now - t), "en_ligne": now - t < EN_LIGNE_S}
                     for d, t in vus.items()],
    })


@app.route("/api/done/<id_>", methods=["POST"])
def api_done(id_):
    return jsonify({"ok": marquer_fait(id_)})


@app.route("/api/test", methods=["POST"])
def api_test():
    id_ = f"test-{uuid.uuid4().hex[:6]}"
    # Passe par le broker, comme un vrai boîtier
    mqtt_client.publish("boitier/test/demande", json.dumps({"id": id_, "type": "test"}), qos=1)
    return jsonify({"id": id_})


@app.route("/api/commande", methods=["POST"])
def api_commande():
    data = request.get_json(silent=True) or {}
    produit = data.get("produit")
    device = data.get("device", "esp32-01")
    if produit not in PRODUITS:
        return jsonify({"ok": False, "erreur": "produit inconnu"}), 400
    id_ = f"{device}-{uuid.uuid4().hex[:6]}"
    mqtt_client.publish(f"boitier/{device}/demande",
                        json.dumps({"id": id_, "type": produit}), qos=1)
    return jsonify({"ok": True, "id": id_})


@app.route("/api/mes-demandes")
def api_mes_demandes():
    device = request.args.get("device", "esp32-01")
    lignes = sql("SELECT id, type, status FROM demandes WHERE device=? "
                 "ORDER BY created_at DESC LIMIT 10", (device,))
    return jsonify([dict(l) for l in lignes])


@app.route("/export.csv")
def export_csv():
    lignes = sql("SELECT * FROM demandes ORDER BY created_at")
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["id", "boitier", "type", "statut", "creee", "terminee", "delai_s"])
    for l in lignes:
        creee = datetime.fromtimestamp(l["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
        fin = datetime.fromtimestamp(l["done_at"]).strftime("%Y-%m-%d %H:%M:%S") if l["done_at"] else ""
        delai = round(l["done_at"] - l["created_at"]) if l["done_at"] else ""
        w.writerow([l["id"], l["device"], l["type"], l["status"], creee, fin, delai])
    return Response(sortie.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=commandes.csv"})


HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Suivi des demandes boîtiers</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#f3f4f6;color:#111827}
 header{background:#1f2937;color:#fff;padding:14px 24px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
 header a,header button{color:#fff;background:#374151;border:0;border-radius:6px;padding:8px 12px;text-decoration:none;cursor:pointer;font-size:.9rem}
 main{padding:20px;max-width:1200px;margin:auto}
 .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
 .kpi{background:#fff;border-radius:10px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
 .kpi span{font-size:.8rem;color:#6b7280}
 .kpi strong{display:block;font-size:1.7rem;margin-top:4px}
 .grille{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;margin-bottom:16px}
 .carte{background:#fff;border-radius:10px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
 h2{font-size:1rem;margin:0 0 10px}
 table{width:100%;border-collapse:collapse;font-size:.9rem}
 td,th{text-align:left;padding:6px;border-bottom:1px solid #e5e7eb}
 tr.retard{background:#fee2e2}
 .alerte{display:none;background:#fef3c7;border:1px solid #f59e0b;padding:10px;border-radius:8px;margin-bottom:16px}
 .on{color:#059669}.off{color:#9ca3af}
 .btn{background:#2563eb;color:#fff;border:0;border-radius:6px;padding:5px 10px;cursor:pointer}
</style>
</head>
<body>
<header>
 <strong>Suivi des demandes boîtiers</strong>
 <div>
  <span id="maj" style="margin-right:10px;font-size:.85rem"></span>
  <button onclick="tester()">Simuler une demande</button>
  <a href="/tablette">Tablette</a>
  <a href="/commande">Commander</a>
  <a href="/export.csv">Export CSV</a>
 </div>
</header>
<main>
 <div id="alerte" class="alerte"></div>
 <div class="kpis">
  <div class="kpi"><span>Aujourd'hui</span><strong id="k-jour">–</strong></div>
  <div class="kpi"><span>En attente</span><strong id="k-attente">–</strong></div>
  <div class="kpi"><span>Terminées</span><strong id="k-done">–</strong></div>
  <div class="kpi"><span>Délai moyen</span><strong id="k-delai">–</strong></div>
  <div class="kpi"><span>Total</span><strong id="k-total">–</strong></div>
 </div>
 <div class="grille">
  <div class="carte"><h2>Demandes sur 24 h</h2><canvas id="c-heure"></canvas></div>
  <div class="carte"><h2>Par boîtier</h2><canvas id="c-device"></canvas></div>
  <div class="carte"><h2>14 derniers jours (et délai moyen en min)</h2><canvas id="c-jour"></canvas></div>
  <div class="carte"><h2>Boîtiers</h2><table><tbody id="boitiers"></tbody></table></div>
 </div>
 <div class="carte">
  <h2>Demandes en attente</h2>
  <table>
   <thead><tr><th>Boîtier</th><th>Id</th><th>Depuis</th><th></th></tr></thead>
   <tbody id="attente"></tbody>
  </table>
 </div>
</main>
<script>
const SEUIL = {{ seuil }};
let charts = {};

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function fmtDuree(s) {
  if (s == null) return "–";
  if (s < 60) return s + " s";
  if (s < 3600) return Math.round(s / 60) + " min";
  return (s / 3600).toFixed(1) + " h";
}

function creerGraphes() {
  charts.heure = new Chart(document.getElementById("c-heure"), {
    type: "bar",
    data: {labels: [], datasets: [{label: "Demandes", data: [], backgroundColor: "#3b82f6"}]},
    options: {plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true, ticks: {precision: 0}}}}
  });
  charts.device = new Chart(document.getElementById("c-device"), {
    type: "doughnut",
    data: {labels: [], datasets: [{data: [], backgroundColor: ["#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6","#14b8a6"]}]}
  });
  charts.jour = new Chart(document.getElementById("c-jour"), {
    type: "bar",
    data: {labels: [], datasets: [
      {label: "Demandes", data: [], backgroundColor: "#10b981", yAxisID: "y"},
      {type: "line", label: "Délai moyen (min)", data: [], borderColor: "#f59e0b", yAxisID: "y2", spanGaps: true}
    ]},
    options: {scales: {
      y: {beginAtZero: true, ticks: {precision: 0}},
      y2: {position: "right", beginAtZero: true, grid: {drawOnChartArea: false}}
    }}
  });
}

async function rafraichir() {
  const d = await (await fetch("/api/stats")).json();
  const k = d.kpis;
  document.getElementById("k-jour").textContent = k.aujourdhui;
  document.getElementById("k-attente").textContent = k.en_attente;
  document.getElementById("k-done").textContent = k.terminees;
  document.getElementById("k-delai").textContent = fmtDuree(k.delai_moyen_s);
  document.getElementById("k-total").textContent = k.total;

  const alerte = document.getElementById("alerte");
  alerte.style.display = k.en_retard ? "block" : "none";
  alerte.textContent = k.en_retard + " demande(s) en attente depuis plus de " + SEUIL + " min";

  charts.heure.data.labels = d.par_heure.labels;
  charts.heure.data.datasets[0].data = d.par_heure.valeurs;
  charts.heure.update();

  charts.device.data.labels = Object.keys(d.par_device);
  charts.device.data.datasets[0].data = Object.values(d.par_device);
  charts.device.update();

  charts.jour.data.labels = d.par_jour.labels;
  charts.jour.data.datasets[0].data = d.par_jour.valeurs;
  charts.jour.data.datasets[1].data = d.par_jour.delai_moyen_min;
  charts.jour.update();

  document.getElementById("boitiers").innerHTML = d.boitiers.map(b =>
    `<tr><td>${esc(b.device)}</td>
     <td class="${b.en_ligne ? 'on' : 'off'}">${b.en_ligne ? '● en ligne' : '○ hors ligne'}</td>
     <td>vu il y a ${fmtDuree(b.vu_il_y_a_s)}</td></tr>`
  ).join("") || `<tr><td>Aucun boîtier encore vu</td></tr>`;

  document.getElementById("attente").innerHTML = d.en_attente.map(a =>
    `<tr class="${a.depuis_s > SEUIL * 60 ? 'retard' : ''}">
     <td>${esc(a.device)}</td><td>${esc(a.id)}</td><td>${fmtDuree(a.depuis_s)}</td>
     <td><button class="btn" data-id="${esc(a.id)}" onclick="fait(this.dataset.id)">Marquer fait</button></td></tr>`
  ).join("") || `<tr><td colspan="4">Aucune demande en attente</td></tr>`;

  document.getElementById("maj").textContent = "Mis à jour " + new Date().toLocaleTimeString();
}

async function fait(id) {
  await fetch("/api/done/" + encodeURIComponent(id), {method: "POST"});
  rafraichir();
}

async function tester() {
  await fetch("/api/test", {method: "POST"});
  setTimeout(rafraichir, 800);
}

creerGraphes();
rafraichir();
setInterval(rafraichir, 5000);
</script>
</body>
</html>
"""


TABLETTE_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tablette - commandes</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#111827;color:#fff}
 header{padding:14px 18px;font-size:1.2rem;font-weight:bold;background:#1f2937}
 #liste{padding:12px;display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
 .carte{background:#1f2937;border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:10px}
 .carte.retard{background:#7f1d1d}
 .produit{font-size:1.6rem;font-weight:bold}
 .info{font-size:.95rem;opacity:.8}
 button{font-size:1.4rem;padding:18px;border:0;border-radius:12px;background:#10b981;color:#fff;font-weight:bold;cursor:pointer}
 button:active{transform:scale(.97)}
 .vide{padding:40px;text-align:center;font-size:1.3rem;opacity:.7}
</style>
</head>
<body>
<header>Commandes en attente <span id="compteur"></span></header>
<div id="liste"></div>
<script>
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function fmt(s){return s<60 ? s+" s" : Math.floor(s/60)+" min "+(s%60)+" s";}

async function charger(){
  const d = await (await fetch("/api/stats")).json();
  document.getElementById("compteur").textContent = "(" + d.en_attente.length + ")";
  const liste = document.getElementById("liste");
  if(!d.en_attente.length){
    liste.innerHTML = '<div class="vide">Aucune commande en attente</div>';
    return;
  }
  liste.innerHTML = d.en_attente.map(a => `
    <div class="carte ${a.depuis_s > 600 ? 'retard' : ''}">
      <div class="produit">${esc(a.type)}</div>
      <div class="info">${esc(a.device)} · attente ${fmt(a.depuis_s)}</div>
      <button data-id="${esc(a.id)}" onclick="fait(this.dataset.id, this)">FAIT</button>
    </div>`).join("");
}

async function fait(id, bouton){
  bouton.disabled = true;
  await fetch("/api/done/" + encodeURIComponent(id), {method: "POST"});
  charger();
}

charger();
setInterval(charger, 3000);
</script>
</body>
</html>
"""


COMMANDE_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Commander</title>
<style>
 body{font-family:system-ui,sans-serif;margin:0;background:#f3f4f6;color:#111827}
 header{background:#1f2937;color:#fff;padding:14px 18px;font-size:1.2rem;font-weight:bold}
 main{padding:16px;max-width:600px;margin:auto}
 #produits{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 #produits button{font-size:1.2rem;padding:24px 10px;border:0;border-radius:12px;background:#2563eb;color:#fff;font-weight:bold;cursor:pointer}
 #produits button:disabled{background:#9ca3af}
 #msg{margin:14px 0;min-height:1.4em;font-weight:bold;color:#059669}
 h2{font-size:1rem;margin:20px 0 8px}
 ul{list-style:none;padding:0;margin:0}
 li{background:#fff;padding:10px 12px;border-radius:8px;margin-bottom:8px;box-shadow:0 1px 2px rgba(0,0,0,.08)}
 .attente{color:#d97706}
 .ok{color:#059669}
</style>
</head>
<body>
<header>Commander</header>
<main>
 <div id="produits"></div>
 <div id="msg"></div>
 <h2>Mes dernières commandes</h2>
 <ul id="historique"></ul>
</main>
<script>
const PRODUITS = {{ produits|tojson }};

function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}

const grille = document.getElementById("produits");
grille.innerHTML = PRODUITS.map(p => `<button data-p="${esc(p)}">${esc(p)}</button>`).join("");

grille.onclick = e => {
  const b = e.target.closest("button");
  if (b) envoyer(b.dataset.p, b);
};

async function envoyer(produit, bouton){
  bouton.disabled = true;
  const r = await fetch("/api/commande", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({produit: produit, device: "esp32-01"})
  });
  const d = await r.json();
  document.getElementById("msg").textContent = d.ok ? "Commande envoyée : " + produit : "Erreur d'envoi";
  setTimeout(() => { bouton.disabled = false; }, 1500);
  historique();
}

async function historique(){
  const l = await (await fetch("/api/mes-demandes?device=esp32-01")).json();
  document.getElementById("historique").innerHTML = l.map(x =>
    `<li><strong>${esc(x.type)}</strong> : <span class="${x.status === 'done' ? 'ok' : 'attente'}">${x.status === 'done' ? 'Terminée' : 'En attente'}</span></li>`
  ).join("") || "<li>Aucune commande</li>";
}

historique();
setInterval(historique, 3000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(BROKER, PORT)
    mqtt_client.loop_start()
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)