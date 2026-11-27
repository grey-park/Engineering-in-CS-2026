// Boîtier de table

#include <WiFi.h>
#include "net.h"

#ifndef TABLE_ID
#define TABLE_ID 1
#endif

#if CONFIG_IDF_TARGET_ESP32
// DevKitC (tests)
static const uint8_t BTN_PINS[3] = {32, 33, 25};
static const uint8_t LED_PINS[3] = {26, 27, 14};
static const int BAT_PIN = -1;
#else
// XIAO / SuperMini
static const uint8_t BTN_PINS[3] = {3, 4, 5};
static const uint8_t LED_PINS[3] = {6, 7, 10};
#ifdef BOARD_XIAO
static const int BAT_PIN = 2;
#else
static const int BAT_PIN = 1;
#endif
#endif

enum State { IDLE, SENDING, WAITING, CLAIMED, ERR };

struct Slot {
  State    st = IDLE;
  uint16_t seq = 0;
  uint32_t t0 = 0;
  uint32_t lastTx = 0;
  bool     raw = true;   // true = relâché
  uint32_t rawSince = 0;
  bool     stable = true;
  uint32_t lastPress = 0;
};

static const uint32_t DEBOUNCE_MS = 50;
static const uint32_t PRESS_LOCKOUT_MS = 300;

static Slot slots[3];
static uint16_t seqCounter;
static char tCall[40], tRepress[40], tState[40], tStatus[40];

static uint16_t readBatteryMv() {
  if (BAT_PIN < 0) return 0;
  return (uint16_t)(analogReadMilliVolts(BAT_PIN) * 2);  // pont diviseur
}

// réappui sur un appel en cours
static void sendRepress(int k) {
  JsonDocument d;
  d["kind"] = k;
  d["seq"] = slots[k].seq;
  ts_publish(tRepress, d);
}

static void sendCall(int k) {
  JsonDocument d;
  d["kind"] = k;
  d["seq"] = slots[k].seq;
  d["bat"] = readBatteryMv();
  ts_publish(tCall, d);
}

// réponse du Pi
static void onMessage(char *topic, uint8_t *payload, unsigned int len) {
  JsonDocument d;
  if (deserializeJson(d, payload, len)) return;
  int k = d["kind"] | -1;
  uint16_t seq = d["seq"] | 0;
  const char *st = d["st"] | "";
  if (k < 0 || k > 2) return;
  Slot &s = slots[k];
  if (seq != s.seq) return;
  if (!strcmp(st, "received") && s.st == SENDING) {
    s.st = WAITING;
  } else if (!strcmp(st, "claimed") && (s.st == SENDING || s.st == WAITING)) {
    s.st = CLAIMED;
    s.t0 = millis();
    Serial.printf("[box] pris en charge %d\n", k);
  }
}

static void onConnect() {
  ts_mqtt.subscribe(tState, 1);
}

static void onPress(int k) {
  Slot &s = slots[k];
  if (s.st == SENDING || s.st == WAITING) {
    if (ts_mqtt.connected()) sendRepress(k);
    Serial.printf("[box] appel %d déjà en cours, nouvel appui signalé\n", k);
    return;
  }
  s.seq = ++seqCounter;
  s.st = SENDING;
  s.t0 = millis();
  s.lastTx = 0;
  Serial.printf("[box] appel %d seq=%u\n", k, s.seq);
}

void setup() {
  Serial.begin(115200);
  for (int k = 0; k < 3; k++) {
    pinMode(BTN_PINS[k], INPUT_PULLUP);
    pinMode(LED_PINS[k], OUTPUT);
    digitalWrite(LED_PINS[k], LOW);
  }
  if (BAT_PIN >= 0) analogSetPinAttenuation(BAT_PIN, ADC_11db);
  seqCounter = (uint16_t)(esp_random() & 0xFFFF);

  snprintf(tCall, sizeof(tCall), "tapserve/box/%d/call", TABLE_ID);
  snprintf(tRepress, sizeof(tRepress), "tapserve/box/%d/repress", TABLE_ID);
  snprintf(tState, sizeof(tState), "tapserve/box/%d/state", TABLE_ID);
  snprintf(tStatus, sizeof(tStatus), "tapserve/box/%d/status", TABLE_ID);

  ts_net_status(tStatus);
  ts_net_begin("tapserve-box-" + String(TABLE_ID), onMessage, onConnect);
  Serial.printf("[box] TapServe table %d\n", TABLE_ID);
}

void loop() {
  uint32_t now = millis();
  bool online = ts_net_loop();

  // boutons
  for (int k = 0; k < 3; k++) {
    Slot &s = slots[k];
    bool b = digitalRead(BTN_PINS[k]);
    if (b != s.raw) {
      s.raw = b;
      s.rawSince = now;
    } else if (b != s.stable && now - s.rawSince >= DEBOUNCE_MS) {
      s.stable = b;
      if (!b && now - s.lastPress >= PRESS_LOCKOUT_MS) {
        s.lastPress = now;
        onPress(k);
      }
    }
  }

  // envoi + LEDs
  for (int k = 0; k < 3; k++) {
    Slot &s = slots[k];

    if (s.st == SENDING) {
      if (now - s.t0 > 8000) {  // le Pi ne répond pas
        s.st = ERR;
        s.t0 = now;
        Serial.println("[box] Pi injoignable");
      } else if (online && (s.lastTx == 0 || now - s.lastTx >= 1000)) {
        sendCall(k);
        s.lastTx = now;
      }
    }
    if (s.st == CLAIMED && now - s.t0 > 4000) s.st = IDLE;
    if (s.st == ERR && now - s.t0 > 3000) s.st = IDLE;

    bool on = false;
    switch (s.st) {
      case SENDING: on = (now / 100) % 2; break;
      case WAITING: on = true; break;
      case CLAIMED: on = (now / 400) % 2; break;
      case ERR:     on = (now / 50) % 2; break;
      default:      on = false;
    }
    digitalWrite(LED_PINS[k], on ? HIGH : LOW);
  }

  delay(5);
}
