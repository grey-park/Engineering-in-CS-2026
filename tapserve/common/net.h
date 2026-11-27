// Wi-Fi + MQTT
#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"
#include "protocol.h"

static WiFiClient   ts_wifi;
static PubSubClient ts_mqtt(ts_wifi);
static String       ts_clientId;
static uint32_t     ts_lastTry = 0;
static uint32_t     ts_lastWifiLog = 0;
static void (*ts_onConnect)() = nullptr;
static const char *ts_statusTopic = nullptr;

inline void ts_on_wifi_event(WiFiEvent_t event, WiFiEventInfo_t info) {
  if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
    Serial.printf("[net] Wi-Fi déconnecté, raison %d\n", info.wifi_sta_disconnected.reason);
  } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
    Serial.printf("[net] Wi-Fi connecté, IP %s\n", IPAddress(info.got_ip.ip_info.ip.addr).toString().c_str());
  }
}

// statut online / offline
inline void ts_net_status(const char *topic) { ts_statusTopic = topic; }

inline void ts_net_begin(const String &clientId,
                         void (*onMessage)(char *, uint8_t *, unsigned int),
                         void (*onConnect)()) {
  ts_clientId = clientId;
  ts_onConnect = onConnect;
  WiFi.onEvent(ts_on_wifi_event, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  WiFi.onEvent(ts_on_wifi_event, ARDUINO_EVENT_WIFI_STA_GOT_IP);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  ts_mqtt.setServer(MQTT_HOST, MQTT_PORT);
  ts_mqtt.setCallback(onMessage);
  ts_mqtt.setBufferSize(1024);  // la liste des appels peut être longue
  ts_mqtt.setKeepAlive(15);
  Serial.printf("[net] Wi-Fi \"%s\", broker %s:%d\n", WIFI_SSID, MQTT_HOST, MQTT_PORT);
}

// true si connecté
inline bool ts_net_loop() {
  if (WiFi.status() != WL_CONNECTED) {
    if (millis() - ts_lastWifiLog >= 5000) {
      ts_lastWifiLog = millis();
      Serial.printf("[net] Wi-Fi pas connecté, WiFi.status() = %d\n", WiFi.status());
    }
    return false;
  }
  if (!ts_mqtt.connected()) {
    if (millis() - ts_lastTry < 2000) return false;
    ts_lastTry = millis();
    bool ok = ts_statusTopic ? ts_mqtt.connect(ts_clientId.c_str(), ts_statusTopic, 1, true, "offline")
                             : ts_mqtt.connect(ts_clientId.c_str());
    if (!ok) {
      Serial.printf("[net] broker injoignable (code %d), IP %s\n", ts_mqtt.state(),
                    WiFi.localIP().toString().c_str());
      return false;
    }
    Serial.printf("[net] connecté au broker (IP %s)\n", WiFi.localIP().toString().c_str());
    if (ts_statusTopic) ts_mqtt.publish(ts_statusTopic, "online", true);
    if (ts_onConnect) ts_onConnect();
  }
  ts_mqtt.loop();
  return true;
}

inline bool ts_publish(const char *topic, const JsonDocument &doc) {
  char buf[256];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  return ts_mqtt.publish(topic, (const uint8_t *)buf, n, false);
}
