#pragma once

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "common/secrets.h manquant : copier common/secrets.example.h en common/secrets.h et y mettre le mot de passe Wi-Fi"
#endif

// À la maison : votre Wi-Fi et l'IP du PC
#define WIFI_SSID  "TapServe"
#define MQTT_HOST  "10.42.0.1"
#define MQTT_PORT  1883
