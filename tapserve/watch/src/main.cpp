// Montre du serveur

#include <Wire.h>
#include <WiFi.h>
#include <TFT_eSPI.h>
#define XPOWERS_CHIP_AXP2101
#include <XPowersLib.h>
#include <Adafruit_DRV2605.h>
#include "net.h"

// broches
#define PIN_SDA        10
#define PIN_SCL        11
#define PIN_TOUCH_SDA  39   // tactile
#define PIN_TOUCH_SCL  40
#define TOUCH_ADDR     0x38

#define SCREEN_INVERT  1
#define SCREEN_ROTATION 2

#define CLAIM_SHOW_MS  3000
#define SCREEN_IDLE_MS 15000
#define SCREEN_ALWAYS_ON true   // pour la démo
#define LIST_ROWS      4

TFT_eSPI tft;
TFT_eSprite spr(&tft);   // évite le scintillement
XPowersAXP2101 pmu;
Adafruit_DRV2605 haptic;

static const char *KIND_LABEL[3] = {"APPEL", "ADDITION", "ENCORE"};
static const uint16_t KIND_COLOR[3] = {TFT_ORANGE, TFT_SKYBLUE, TFT_GREENYELLOW};

struct Call {
  uint8_t  table, kind;
  uint16_t seq;
  uint32_t since;
};

#define MAX_CALLS 16
static Call calls[MAX_CALLS];
static int nCalls = 0;

// appel pris par cette montre
static struct {
  bool     active = false;
  uint8_t  table = 0, kind = 0;
  uint16_t seq = 0;
  uint32_t at = 0, lastTx = 0;
  uint8_t  left = 0;
} claim;

static bool dirty = true, online = false;
static uint32_t lastDraw = 0, lastBuzz = 0, lastTouch = 0;
static bool wasTouched = false;
static bool screenOn = true;
static uint32_t lastActivity = 0;

// Matériel

static void powerInit() {
  if (!pmu.begin(Wire, AXP2101_SLAVE_ADDRESS, PIN_SDA, PIN_SCL)) {
    Serial.println("[watch] AXP2101 introuvable");
    return;
  }
  pmu.disableTSPinMeasure();
  pmu.setALDO1Voltage(3300); pmu.enableALDO1();
  pmu.setALDO2Voltage(3300); pmu.enableALDO2();    // rétroéclairage
  pmu.setALDO3Voltage(3300); pmu.enableALDO3();    // écran et tactile
  pmu.setBLDO2Voltage(3300); pmu.enableBLDO2();    // vibreur
  pmu.disableALDO4();
  pmu.enableBattVoltageMeasure();
}

static void buzz(uint8_t effect = 47) {
  haptic.setWaveform(0, effect);
  haptic.setWaveform(1, 0);
  haptic.go();
}

static void screenWake() {
  lastActivity = millis();
  if (screenOn) return;
  tft.writecommand(0x11);   // réveil
  delay(120);
  digitalWrite(TFT_BL, HIGH);
  screenOn = true;
  dirty = true;
  Serial.println("[watch] écran allumé");
}

static void screenSleep() {
  if (!screenOn) return;
  digitalWrite(TFT_BL, LOW);
  tft.writecommand(0x10);   // veille
  screenOn = false;
  Serial.println("[watch] écran éteint");
}

static bool touchPressed() {
  Wire1.beginTransmission(TOUCH_ADDR);
  Wire1.write(0x02);  // nombre de doigts
  if (Wire1.endTransmission(false) != 0) return false;
  if (Wire1.requestFrom(TOUCH_ADDR, 1) != 1) return false;
  return (Wire1.read() & 0x0F) > 0;
}

// Appels

static bool isClaimed(uint8_t table, uint8_t kind, uint16_t seq) {
  return claim.active && claim.table == table && claim.kind == kind && claim.seq == seq;
}

// liste reçue du Pi
static void onPending(JsonArray arr) {
  uint32_t now = millis();
  Call next[MAX_CALLS];
  int n = 0;
  bool fresh = false, claimStillPending = false;

  for (JsonObject o : arr) {
    if (n >= MAX_CALLS) break;
    uint8_t table = o["table"] | 0, kind = o["kind"] | 0;
    uint16_t seq = o["seq"] | 0;
    uint32_t age = o["age"] | 0;
    if (kind > 2) continue;
    if (isClaimed(table, kind, seq)) { claimStillPending = true; continue; }

    bool known = false;
    for (int i = 0; i < nCalls; i++)
      if (calls[i].table == table && calls[i].kind == kind && calls[i].seq == seq) known = true;
    if (!known) fresh = true;

    next[n++] = {table, kind, seq, now - age * 1000};
  }

  if (!claimStillPending) claim.left = 0;  // le Pi a reçu notre "J'arrive"
  if (n != nCalls || fresh) {
    Serial.printf("[watch] en attente : %d appel(s)%s\n", n, fresh ? ", nouvel appel" : "");
  }
  memcpy(calls, next, sizeof(Call) * n);
  nCalls = n;
  if (fresh) {
    buzz();
    lastBuzz = now;
    screenWake();
  }
  dirty = true;
}

static void onMessage(char *topic, uint8_t *payload, unsigned int len) {
  if (strcmp(topic, TOPIC_PENDING) != 0) return;
  JsonDocument d;
  if (deserializeJson(d, payload, len)) return;
  onPending(d.as<JsonArray>());
}

static void onConnect() {
  ts_mqtt.subscribe(TOPIC_PENDING, 1);
  dirty = true;
}

static void sendClaim() {
  JsonDocument d;
  d["table"] = claim.table;
  d["kind"] = claim.kind;
  d["seq"] = claim.seq;
  ts_publish(TOPIC_CLAIM, d);
  Serial.printf("[watch] J'arrive : table %u %s seq=%u\n", claim.table, KIND_LABEL[claim.kind], claim.seq);
}

static void onTap() {
  if (nCalls == 0) return;
  Call &c = calls[0];   // le plus ancien
  claim.active = true;
  claim.table = c.table;
  claim.kind = c.kind;
  claim.seq = c.seq;
  claim.at = millis();
  claim.lastTx = 0;
  claim.left = 5;
  memmove(&calls[0], &calls[1], sizeof(Call) * (nCalls - 1));
  nCalls--;
  buzz(1);  // petit clic
  dirty = true;
}

// Affichage

static void drawStatusBar() {
  bool wifi = WiFi.status() == WL_CONNECTED;
  spr.setTextDatum(TL_DATUM);
  spr.fillCircle(8, 10, 5, wifi ? TFT_GREEN : TFT_RED);
  spr.setTextColor(wifi ? TFT_LIGHTGREY : TFT_RED, TFT_BLACK);
  spr.drawString("Wi-Fi", 17, 3, 2);
  spr.fillCircle(68, 10, 5, online ? TFT_GREEN : TFT_RED);
  spr.setTextColor(online ? TFT_LIGHTGREY : TFT_RED, TFT_BLACK);
  spr.drawString("MQTT", 77, 3, 2);

  // batterie
  int pct = pmu.isBatteryConnect() ? pmu.getBatteryPercent() : -1;
  uint16_t bcol = pct < 0 ? TFT_DARKGREY : pct <= 15 ? TFT_RED : pct <= 40 ? TFT_YELLOW : TFT_GREEN;
  spr.drawRect(206, 4, 26, 13, TFT_LIGHTGREY);
  spr.fillRect(232, 8, 3, 5, TFT_LIGHTGREY);
  if (pct > 0) spr.fillRect(208, 6, (22 * pct) / 100, 9, bcol);
  spr.setTextDatum(TR_DATUM);
  spr.setTextColor(bcol, TFT_BLACK);
  String txt = pct < 0 ? String("--") : String(pct) + "%";
  if (pmu.isCharging()) txt = "+" + txt;
  spr.drawString(txt, 201, 3, 2);

  spr.drawFastHLine(0, 23, 240, TFT_DARKGREY);
}

static void drawFrame() {
  uint32_t now = millis();
  spr.fillScreen(TFT_BLACK);
  drawStatusBar();
  spr.setTextDatum(TC_DATUM);

  if (claim.active && now - claim.at < CLAIM_SHOW_MS) {
    spr.setTextColor(TFT_GREEN, TFT_BLACK);
    spr.drawString("J'ARRIVE", 120, 80, 4);
    spr.drawString("Table " + String(claim.table), 120, 120, 4);
    return;
  }

  if (!online) {
    spr.setTextColor(TFT_RED, TFT_BLACK);
    spr.drawString(WiFi.status() == WL_CONNECTED ? "Pi injoignable" : "Pas de Wi-Fi", 120, 34, 2);
  }

  if (nCalls == 0) {
    spr.setTextColor(TFT_DARKGREY, TFT_BLACK);
    spr.drawString("TapServe", 120, 90, 4);
    spr.drawString("Aucun appel", 120, 130, 2);
    return;
  }

  // le plus ancien en haut
  int rows = nCalls < LIST_ROWS ? nCalls : LIST_ROWS;
  for (int i = 0; i < rows; i++) {
    Call &c = calls[i];
    int y = 28 + i * 44;
    uint32_t secs = (now - c.since) / 1000;
    uint16_t col = KIND_COLOR[c.kind];
    uint16_t bg = i == 0 ? 0x2104 : TFT_BLACK;   // gris foncé

    if (i == 0) spr.fillRoundRect(0, y, 240, 40, 6, bg);
    spr.fillRect(2, y + 4, 6, 32, col);

    spr.setTextDatum(ML_DATUM);
    spr.setTextColor(TFT_WHITE, bg);
    spr.drawString("T" + String(c.table), 14, y + 21, 4);
    spr.setTextColor(col, bg);
    spr.drawString(KIND_LABEL[c.kind], 72, y + 21, 2);

    char buf[12];
    snprintf(buf, sizeof(buf), "%lu:%02lu", (unsigned long)(secs / 60), (unsigned long)(secs % 60));
    spr.setTextDatum(MR_DATUM);
    spr.setTextColor(secs >= 60 ? TFT_RED : TFT_LIGHTGREY, bg);
    spr.drawString(buf, 234, y + 21, 4);
  }

  spr.setTextDatum(TC_DATUM);
  if (nCalls > LIST_ROWS) {
    spr.setTextColor(TFT_YELLOW, TFT_BLACK);
    spr.drawString("+" + String(nCalls - LIST_ROWS) + " autre(s)", 120, 205, 2);
  }

  uint16_t col = KIND_COLOR[calls[0].kind];
  spr.fillRoundRect(20, 222, 200, 18, 6, col);
  spr.setTextColor(TFT_BLACK, col);
  spr.drawString("Toucher = J'arrive T" + String(calls[0].table), 120, 223, 2);
}

static void draw() {
  drawFrame();
  spr.pushSprite(0, 0);
}

// Programme

void setup() {
  Serial.begin(115200);
  Wire.begin(PIN_SDA, PIN_SCL);
  powerInit();
  Wire1.begin(PIN_TOUCH_SDA, PIN_TOUCH_SCL);

  tft.init();
  tft.setRotation(SCREEN_ROTATION);
  tft.invertDisplay(SCREEN_INVERT);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);
  spr.setColorDepth(8);
  if (!spr.createSprite(240, 240)) Serial.println("[watch] sprite: memoire insuffisante");

  if (haptic.begin(&Wire)) {
    haptic.selectLibrary(1);
    haptic.setMode(DRV2605_MODE_INTTRIG);
  } else {
    Serial.println("[watch] DRV2605 introuvable");
  }

  static char tStatus[48];
  snprintf(tStatus, sizeof(tStatus), "tapserve/watch/%08lx/status", (unsigned long)(uint32_t)ESP.getEfuseMac());
  ts_net_status(tStatus);
  ts_net_begin("tapserve-watch-" + String((uint32_t)ESP.getEfuseMac(), HEX), onMessage, onConnect);
  Serial.println("[watch] TapServe montre");
  Serial.printf("[watch] batterie : %d %% (%u mV)%s\n",
                pmu.isBatteryConnect() ? pmu.getBatteryPercent() : -1,
                pmu.getBattVoltage(), pmu.isCharging() ? ", en charge" : "");
  lastActivity = millis();
  buzz();
}

void loop() {
  uint32_t now = millis();

  bool on = ts_net_loop();
  if (on != online) { online = on; dirty = true; }

  // écran éteint : on le rallume seulement
  bool t = touchPressed();
  if (t && !wasTouched && now - lastTouch > 400) {
    lastTouch = now;
    if (screenOn) onTap();
    screenWake();
  }
  wasTouched = t;

  // renvoyer jusqu'à réception
  if (claim.left && online && (claim.lastTx == 0 || now - claim.lastTx >= 1000)) {
    sendClaim();
    claim.lastTx = now;
    claim.left--;
  }
  if (claim.active && now - claim.at >= CLAIM_SHOW_MS && claim.left == 0) {
    claim.active = false;
    dirty = true;
  }

  // rappel
  if (nCalls > 0 && now - lastBuzz > 20000) {
    buzz();
    lastBuzz = now;
    screenWake();
  }

  // veille écran
  bool showingClaim = claim.active && now - claim.at < CLAIM_SHOW_MS;
  if (SCREEN_ALWAYS_ON || nCalls > 0 || showingClaim) {
    if (!screenOn) screenWake();
    lastActivity = now;
  } else if (screenOn && now - lastActivity > SCREEN_IDLE_MS) {
    screenSleep();
  }

  if (screenOn && (dirty || now - lastDraw >= 1000)) {
    draw();
    dirty = false;
    lastDraw = now;
  }
  delay(10);
}
